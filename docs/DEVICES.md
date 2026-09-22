# Verified devices

Reports are welcome - open an issue with the information listed at the
bottom of this page.

## Confirmed working

| Device | Firmware | Backend / OS | Notes |
|---|---|---|---|
| C8051F380 board | application firmware, VID `10c4` / PID `ea61`, product string `Interface Board` | libusb / Windows 11 (WinUSB) | `usbxpress info`, command/response exchange, `monitor` |
| C8051F380 board | bootloader firmware (same VID/PID, product string `Interface BL`) | libusb / Windows 11 (WinUSB) | full flashing cycle through the example bootloader protocol |

Both firmwares use the Silicon Labs USBXpress device firmware library and the
default full-speed configuration (bulk OUT `0x02`, bulk IN `0x82`,
64-byte packets).

## Not yet verified

| Platform | Status |
|---|---|
| Linux (native) | expected to work (libusb); see `LINUX.md` for setup |
| Linux (WSL2 + usbipd-win) | recipe documented, reports welcome |
| macOS | expected to work (libusb); no reports yet |
| Other USBXpress parts (C8051F32x / F34x) | same library family, not tested here |

## Reporting a new device

Please include:

1. MCU part number and the firmware library version, if known.
2. `lsusb -v -d <vid>:<pid>` output (or the equivalent on Windows:
   the device descriptor from `usbxpress info`).
3. The output of `usbxpress info` and `usbxpress monitor`.
4. Which backend and operating system you used.
