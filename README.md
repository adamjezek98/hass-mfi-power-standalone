# Ubiquiti mFi mPower for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/adamjezek98/hass-mfi-power-standalone/actions/workflows/validate.yml/badge.svg)](https://github.com/adamjezek98/hass-mfi-power-standalone/actions/workflows/validate.yml)

Local, push-based control of Ubiquiti **mFi mPower** power strips, with no mFi Controller and
no changes to the device.

The integration logs into the strip's own web interface and keeps the websocket the stock
web UI uses (port 7681) open. The strip pushes per-outlet readings over it, and switching
commands go back the same way.

## Features

- **Local push**: the strip sends readings at a configurable interval (default 2 s).
- **Fast switching**: the command is one websocket message. HA shows the new state
  immediately, and the device confirms it about 1 s later.
- **Per outlet**: switch, power (W), current (A), energy (kWh, `total_increasing`, works in the
  Energy dashboard), voltage (V) and power factor (both disabled by default).
- **Nothing installed or changed on the device.** It needs no SSH, no inform URL and no extra
  firewall rules towards Home Assistant.
- **Light on the device**: the websocket daemon uses about 1–1.5 % CPU on an mPower P3E. The
  slow CGI login runs only when (re)connecting.

## Supported devices

| Device | Status |
|---|---|
| mFi mPower P3E (3 outlets, EU), firmware MF 2.1.8 | ✅ tested |
| mPower mini (P1E/P1U), mPower Pro (P6E/P8U), US variants | ⚠️ should work: same web UI, outlet count is detected from the device |

Requires Home Assistant 2025.2 or newer.

## Requirements

- Home Assistant must reach the strip on **TCP 80** (login) and **TCP 7681** (websocket).
- The strip's web UI username and password (factory default `ubnt` / `ubnt`).

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/adamjezek98/hass-mfi-power-standalone`,
   category **Integration**.
2. Install **Ubiquiti mFi mPower** and restart Home Assistant.

### Manual

Copy `custom_components/mfi_mpower` into your `config/custom_components/` folder and restart.

## Setup

**Settings → Devices & services → Add integration → Ubiquiti mFi mPower**, then enter the host,
username and password. Under **Configure** you can change how often the device pushes
readings (0.5–60 s).

## Notes

- **Energy** is counted by the strip in pulses of 0.3125 Wh, so the sensor moves in small steps.
  The counter is kept in RAM and starts again at 0 after the strip reboots. The sensor is
  `total_increasing`, so the Energy dashboard handles that.
- The status LED is solid blue when no mFi Controller is configured, and blinks amber while
  Wi-Fi is connecting. LED control isn't included, because the websocket can't reach it (only SSH can).
  To turn it off permanently, SSH into the strip and run:
  `echo mgmt.led_enabled=false >> /var/etc/persistent/cfg/mgmt && /usr/etc/syswrapper.sh reload && cfgmtd -w -p /etc/`
- Keep these devices on an isolated network. The firmware is from 2015 and gets no more updates.

## How it works

1. `GET /` returns an `AIROS_SESSIONID` cookie, and `POST /login.cgi` (multipart: `uri`, `username`,
   `password`) authorises it.
2. Open `ws://<host>:7681/?c=<session id>` with subprotocol `mfi-protocol`.
3. Send `{"time": <ms>}` to set the push interval.
4. The device sends `{"v":1,"sensors":[{"port":1,"output":1,"power":…,"current":…,"voltage":…,"powerfactor":…,"energy":…}]}`,
   one message per outlet.
5. Switch an outlet with `{"sensors":[{"port":N,"output":0|1}]}`.


## License

GPL-3.0, see [LICENSE](LICENSE).
