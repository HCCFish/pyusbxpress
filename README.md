# pyusbxpress

Cross-platform Python client for Silicon Labs **USBXpress** devices
(C8051F32x / C8051F34x / C8051F38x) — **without the vendor driver**.

Silicon Labs' USBXpress host driver (`SiUSBXp.sys` / `SiUSBXp.dll`) is
Windows-only and version-fragile, and Silicon Labs does not document the
wire protocol between the host driver and the device firmware library.  This
project documents that protocol — independently re-derived here and
consistent with earlier community implementations (see *Related projects*) —
and provides a small Python client that talks to USBXpress devices directly
over **libusb/WinUSB**, so the same code runs on Windows, Linux and macOS.

> **Disclaimer** — this is an *unofficial* project based on interoperability
> research.  It is not affiliated with or endorsed by Silicon Labs.  It
> contains no Silicon Labs code or binaries; the protocol description was
> derived from black-box observation and analysis of the behaviour of the
> device firmware library.  "USBXpress" and "Silicon Labs" are trademarks of
> Silicon Labs, used here only to describe compatibility.

## Status

Alpha (v0.1.x).  Verified on Windows 10/11 with a C8051F380 target (see
[`docs/DEVICES.md`](https://github.com/HCCFish/pyusbxpress/blob/main/docs/DEVICES.md));
Linux/macOS are supported by design (libusb backend) and reports are welcome.

## Install

```console
pip install pyusbxpress
```

or from a checkout:

```console
pip install -e .
```

The libusb backend needs a USB driver that lets user space claim the device:

| Platform | Requirement |
|---|---|
| Windows | Bind the device to **WinUSB** (e.g. with [Zadig](https://zadig.akeo.ie/)) — or keep the SiLabs driver and use `--backend siusbxp` |
| Linux | A udev rule so the device is accessible without root — see [`docs/LINUX.md`](https://github.com/HCCFish/pyusbxpress/blob/main/docs/LINUX.md) |
| macOS | Usually nothing: vendor-specific devices are not claimed by a kernel driver, libusb can use them directly |

## Quick start

```console
usbxpress list                       # list matching devices
usbxpress info                       # USB info + optional command exchange
usbxpress info --send "01"           # send one 64-byte packet, print the answer
usbxpress monitor                    # print every packet the device sends
usbxpress write --hex "01 55"        # send a single packet
```

As a library:

```python
from usbxpress import UsbXpressDevice

with UsbXpressDevice() as dev:               # VID 10C4 / PID EA61 by default
    reply = dev.command(b"\x01")             # send one packet, wait for a
    print(reply.hex(" "))                    # packet that starts with 0x01
```

`UsbXpressDevice` is deliberately thin: one 64-byte packet per call, plus a
`command()` helper that skips unsolicited packets (some firmwares emit
periodic heartbeats).  The meaning of the packets is up to your device
firmware — see
[`examples/`](https://github.com/HCCFish/pyusbxpress/tree/main/examples) for
a minimal ping and for a complete bootloader flashing example.

## How it works (short version)

USBXpress is a **vendor-specific** USB device (interface class `0xFF`) with
two bulk endpoints (64-byte packets) and a small set of vendor control
requests.  The data path stays disabled until the host sends the
`DEVICE_OPEN` control request — this handshake is the piece that Silicon
Labs' documentation does not describe, and the reason "enumeration works but
no data ever arrives" is a common complaint.

| Direction | Transport |
|---|---|
| host → device | bulk **OUT** endpoint, 64-byte packets |
| device → host | bulk **IN** endpoint, 64-byte packets |
| enable/disable data path | vendor control `bmRequestType=0x40, bRequest=0x02` with `wValue=0x0002` (open) / `0x0004` (close) |
| flush device buffers | same request with `wValue=0x0001` |

Full details, including the device-side event bits and the recommended host
sequence, are in
**[docs/PROTOCOL.md](https://github.com/HCCFish/pyusbxpress/blob/main/docs/PROTOCOL.md)**.
The method used to derive the protocol is described in
[docs/INTERNALS.md](https://github.com/HCCFish/pyusbxpress/blob/main/docs/INTERNALS.md).

## Backends

| Backend | Platforms | Driver needed | Notes |
|---|---|---|---|
| `libusb` (default) | Windows, Linux, macOS | WinUSB on Windows; udev rule on Linux | Uses [pyusb](https://github.com/pyusb/pyusb) + [libusb-package](https://pypi.org/project/libusb-package/); no vendor software |
| `siusbxp` | Windows only | SiLabs USBXpress driver | Uses `SiUSBXp.dll` through `ctypes`; the driver performs the open/close handshake itself |

`--backend auto` (the default) uses libusb when a WinUSB-bound device is
present, and falls back to the SiLabs driver on Windows when it is not.

## CLI reference

```
usbxpress [-h] [--version] {list,info,monitor,write} ...

common options:
  --vid HEX      vendor ID (default 10c4)
  --pid HEX      product ID (default ea61)
  --index N      device index when several are attached
  --serial S     select by serial string
  --backend      auto | libusb | siusbxp
  --dll PATH     SiUSBXp.dll location (siusbxp backend only)
  --timeout SEC  per-transfer timeout (default 1.0)

list      show matching devices and the backend that can see them
info      open the device, print USB info; --send HEX performs one exchange
monitor   print incoming packets with timestamps; --send HEX [--interval S] repeats a packet
write     send one packet: --hex "01 55" | --text "hello" | --file image.bin
```

## Documentation

| File | Contents |
|---|---|
| [`docs/PROTOCOL.md`](https://github.com/HCCFish/pyusbxpress/blob/main/docs/PROTOCOL.md) | The USBXpress wire protocol (requests, endpoints, events, host sequence) |
| [`docs/INTERNALS.md`](https://github.com/HCCFish/pyusbxpress/blob/main/docs/INTERNALS.md) | How the protocol was derived (reproducible method) |
| [`docs/LINUX.md`](https://github.com/HCCFish/pyusbxpress/blob/main/docs/LINUX.md) | udev rules, permissions, WSL2/usbipd testing recipe |
| [`docs/DEVICES.md`](https://github.com/HCCFish/pyusbxpress/blob/main/docs/DEVICES.md) | Devices verified so far, and how to report a new one |

## Examples

| File | Contents |
|---|---|
| [`examples/ping.py`](https://github.com/HCCFish/pyusbxpress/blob/main/examples/ping.py) | Minimal command/response exchange |
| [`examples/flash_demo.py`](https://github.com/HCCFish/pyusbxpress/blob/main/examples/flash_demo.py) | Complete example: flash an Intel HEX image through a bootloader that implements the reference command set (query/erase/write/read/go + validity record) |

## Tests

```console
python -m unittest discover -s tests -v
```

The tests cover the protocol helpers and the packet/response logic with a
fake backend; no hardware is required.

## Related projects

The USBXpress wire protocol has been implemented in the open before.  It was
re-derived independently for this project (device firmware library
disassembly plus live device tests) and the results match:

- [SiUSBXp_Linux_Driver](http://www.etheus.net/SiUSBXp_Linux_Driver) —
  Craig Shelley's open-source C implementation (2010, GPL-2, libusb 0.1);
  its `SI_Open` sends the same `DEVICE_OPEN` request and moves data over the
  bulk endpoints.
- [fMeow/silabs_usb_xpress](https://github.com/fMeow/silabs_usb_xpress) —
  a Rust port of that driver (2020, GPL-3, published on crates.io).

pyusbxpress differs by targeting modern libusb 1.0 from Python, being
maintained and documented, and shipping a CLI with tested examples.

## License

MIT — see [`LICENSE`](https://github.com/HCCFish/pyusbxpress/blob/main/LICENSE).
