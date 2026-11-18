"""Client for the mFi mPower local web interface.

The stock firmware (MF 2.x) exposes a websocket on port 7681 that pushes
per-outlet readings and accepts output changes:

1. ``GET /`` hands out an ``AIROS_SESSIONID`` cookie.
2. ``POST /login.cgi`` (multipart: uri, username, password) authorises it.
3. ``ws://host:7681/?c=<sessionid>`` with subprotocol ``mfi-protocol``.
4. Send ``{"time": ms}`` to set the push interval.
5. Device pushes ``{"v":1,"sensors":[{"port":1,"output":1,"power":..}]}``,
   one message per outlet per interval.
6. Send ``{"sensors":[{"port":N,"output":0|1}]}`` to switch an outlet.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

WS_PORT = 7681
WS_PROTOCOL = "mfi-protocol"
SESSION_COOKIE = "AIROS_SESSIONID"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)


class MPowerError(Exception):
    """Generic communication error."""


class MPowerAuthError(MPowerError):
    """Credentials were rejected."""


class MPowerClient:
    """Keeps a websocket open to one mPower and dispatches its readings."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        interval: float,
    ) -> None:
        self._session = session
        self.host = host
        self._username = username
        self._password = password
        self._interval_ms = max(100, int(interval * 1000))
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._listeners: list[Callable[[], None]] = []
        self.ports: dict[int, dict[str, Any]] = {}
        self.connected = False
        self._first_data = asyncio.Event()

    # -- public API -------------------------------------------------------

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for data/connection changes."""
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    async def login(self) -> str:
        """Log in and return an authorised session id."""
        base = f"http://{self.host}"
        try:
            async with self._session.get(
                f"{base}/", allow_redirects=False, timeout=HTTP_TIMEOUT
            ) as resp:
                await resp.read()
                morsel = resp.cookies.get(SESSION_COOKIE)
            if morsel is None:
                raise MPowerError("device did not hand out a session cookie")
            sid = morsel.value

            form = aiohttp.FormData()
            form.add_field("uri", "/")
            form.add_field("username", self._username)
            form.add_field("password", self._password)
            async with self._session.post(
                f"{base}/login.cgi",
                data=form,
                headers={"Cookie": f"{SESSION_COOKIE}={sid}"},
                allow_redirects=False,
                timeout=HTTP_TIMEOUT,
            ) as resp:
                await resp.read()
                location = resp.headers.get("Location", "")
                # Success redirects to the requested uri; a failure renders
                # the login form again (200) or bounces back to login.cgi.
                if resp.status != 302 or "login" in location:
                    raise MPowerAuthError("invalid username or password")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise MPowerError(f"cannot reach {self.host}: {err}") from err
        return sid

    async def probe(self, timeout: float = 15) -> dict[int, dict[str, Any]]:
        """Connect once, collect a reading for every outlet, disconnect."""
        sid = await self.login()
        ports: dict[int, dict[str, Any]] = {}
        try:
            async with self._session.ws_connect(
                self._ws_url(sid), protocols=(WS_PROTOCOL,), timeout=aiohttp.ClientWSTimeout(ws_close=5)
            ) as ws:
                await ws.send_str(json.dumps({"time": 1000}))
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        new = self._parse(msg)
                        if new is None:
                            break
                        if ports and all(p in ports for p in new):
                            break  # second round: every outlet seen
                        ports.update(new)
        except (aiohttp.ClientError, TimeoutError) as err:
            if not ports:
                raise MPowerError(f"websocket failed: {err}") from err
        if not ports:
            raise MPowerError("device sent no readings")
        return ports

    def start(self) -> None:
        """Start the background connection loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"mpower {self.host}")

    async def stop(self) -> None:
        """Stop the connection loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def wait_for_data(self, timeout: float) -> bool:
        """Wait until the first full round of readings arrived."""
        try:
            async with asyncio.timeout(timeout):
                await self._first_data.wait()
        except TimeoutError:
            return False
        return True

    async def set_output(self, port: int, on: bool) -> None:
        """Switch an outlet on or off."""
        if self._ws is None or self._ws.closed:
            raise MPowerError("not connected")
        await self._ws.send_str(
            json.dumps({"sensors": [{"port": port, "output": 1 if on else 0}]})
        )
        # Optimistic update; the next push confirms (about 1 s later).
        if port in self.ports:
            self.ports[port]["output"] = 1 if on else 0
            self._notify()

    # -- internals --------------------------------------------------------

    def _ws_url(self, sid: str) -> str:
        return f"ws://{self.host}:{WS_PORT}/?c={sid}"

    @staticmethod
    def _parse(msg: aiohttp.WSMessage) -> dict[int, dict[str, Any]] | None:
        if msg.type != aiohttp.WSMsgType.TEXT:
            return None
        try:
            data = json.loads(msg.data)
        except ValueError:
            _LOGGER.debug("ignoring non-JSON message: %r", msg.data[:200])
            return {}
        out: dict[int, dict[str, Any]] = {}
        for item in data.get("sensors", []):
            port = item.get("port")
            if isinstance(port, int):
                out[port] = item
        return out

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self._notify()

    async def _run(self) -> None:
        backoff = 2
        while True:
            try:
                sid = await self.login()
                async with self._session.ws_connect(
                    self._ws_url(sid),
                    protocols=(WS_PROTOCOL,),
                    heartbeat=30,
                    timeout=aiohttp.ClientWSTimeout(ws_close=5),
                ) as ws:
                    self._ws = ws
                    await ws.send_str(json.dumps({"time": self._interval_ms}))
                    _LOGGER.debug("connected to %s", self.host)
                    seen: set[int] = set()
                    async with asyncio.timeout(None) as watchdog:
                        loop = asyncio.get_running_loop()
                        stale_after = max(30, self._interval_ms / 1000 * 10)
                        watchdog.reschedule(loop.time() + stale_after)
                        async for msg in ws:
                            new = self._parse(msg)
                            if new is None:
                                break
                            if not new:
                                continue
                            watchdog.reschedule(loop.time() + stale_after)
                            for port, values in new.items():
                                self.ports.setdefault(port, {}).update(values)
                                if port in seen:
                                    self._first_data.set()
                                seen.add(port)
                            backoff = 2
                            self._set_connected(True)
                            self._notify()
                    _LOGGER.debug("websocket to %s closed", self.host)
            except asyncio.CancelledError:
                raise
            except MPowerAuthError as err:
                _LOGGER.error("mPower %s: %s", self.host, err)
                backoff = 300
            except (MPowerError, aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("mPower %s connection error: %s", self.host, err)
            finally:
                self._ws = None
            self._set_connected(False)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
