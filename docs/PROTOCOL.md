# USBXpress wire protocol

This document describes the USB level behaviour of devices that use the
Silicon Labs **USBXpress** device firmware library (C8051F32x / F34x / F38x).
It is the protocol that the official host driver (`SiUSBXp.sys`) speaks; it
is not documented by the vendor and was derived by interoperability research
(see `INTERNALS.md`).

All statements below were verified against a live C8051F380 target running
firmware built with the vendor library.

## 1. Device level

| Property | Value |
|---|---|
| USB version | full speed (12 Mbit/s) |
| Device class | `0x00` (defined at interface level) |
| Interface class | `0xFF` vendor specific, subclass `0x00`, protocol `0x00` |
| Endpoints | one bulk OUT and one bulk IN, 64-byte max packet size |
| Typical VID/PID | `10C4:EA61` (Silicon Labs) |
| Configuration | single configuration, single interface |

Because the interface class is vendor specific, no operating system provides
a class driver; a vendor driver, WinUSB, or libusb is required.

The endpoint addresses are chosen by the firmware library (typically
`0x02` OUT and `0x82` IN).  Host software should discover them from the
interface descriptor instead of hard-coding them.

## 2. Vendor control requests

USBXpress uses one vendor request with several `wValue` selectors.  The
request has no data stage.

| Selector | `wValue` | Meaning |
|---|---|---|
| DEVICE_OPEN | `0x0002` | Enable the data path (see §3) |
| DEVICE_CLOSE | `0x0004` | Disable the data path |
| FIFO_PURGE | `0x0001` | Flush the device side USB buffers |

```text
bmRequestType = 0x40   (vendor, host to device, device recipient)
bRequest      = 0x02
wValue        = selector (see table)
wIndex        = 0
wLength       = 0
```

The device acknowledges these requests (no STALL) and they are idempotent.
Sending any other vendor request is answered with a protocol STALL, which is
why they can be discovered by scanning.

## 3. Data path gate (the important part)

The device firmware library keeps its data path **disabled** until it has
processed `DEVICE_OPEN`:

- While disabled, `Block_Read()` in the device firmware returns 0 bytes even
  when the host has written to the bulk OUT endpoint, and the device never
  transmits on the bulk IN endpoint.
- While disabled, the OUT FIFO accepts a small number of packets and then
  NAKs further writes, because nothing drains it.

This is the cause of the common "enumeration works, control transfers work,
but no data ever arrives" symptom.  Host software must send `DEVICE_OPEN`
after claiming the interface, and should send `DEVICE_CLOSE` before closing
the device.

## 4. Data transfers

| Direction | Endpoint | Notes |
|---|---|---|
| host → device | bulk OUT | one 64-byte packet per `Block_Read()` result |
| device → host | bulk IN | one 64-byte packet per `Block_Write()` call |

- Packets are fixed size (64 bytes); short payloads are zero padded by the
  host.  The device firmware sees the full packet and decides how much of it
  is meaningful.
- The device may send packets that were not requested by a host command (for
  example periodic status or debug output).  Host software should tolerate
  and skip such packets while waiting for a specific response.
- A host may write several packets back to back; the device firmware drains
  them through repeated `Block_Read()` calls.

## 5. Device side event bits

The firmware library reports events through `Get_Interrupt_Source()`.  These
bits are not visible to the host over USB, but they are useful when writing
firmware or when surfacing diagnostics to the host (see `usbxpress.events`).

| Bit | Name | Meaning |
|---|---|---|
| `0x01` | `USB_RESET` | USB reset seen |
| `0x02` | `TX_COMPLETE` | a `Block_Write()` finished |
| `0x04` | `RX_COMPLETE` | data received, `Block_Read()` will return bytes |
| `0x08` | `FIFO_PURGE` | a purge request was processed |
| `0x10` | `DEVICE_OPEN` | a host opened the device instance |
| `0x20` | `DEVICE_CLOSE` | a host closed the device instance |
| `0x40` | `DEV_CONFIGURED` | the device was configured by the host |
| `0x80` | `DEV_SUSPEND` | USB suspend |

## 6. Recommended host sequence

```text
1. open the device (WinUSB / libusb / vendor driver)
2. claim the interface
3. send DEVICE_OPEN            <- without this, no data will flow
4. exchange packets:           bulk OUT writes / bulk IN reads
5. send DEVICE_CLOSE
6. release the interface and close the device
```

With pyusbxpress this is exactly what `UsbXpressDevice.open()` and
`UsbXpressDevice.close()` do:

```python
from usbxpress import UsbXpressDevice

with UsbXpressDevice() as dev:
    reply = dev.command(b"\x01")     # send one packet, wait for 0x01 response
```

## 7. Verification status

| Item | Status |
|---|---|
| DEVICE_OPEN / CLOSE / PURGE acknowledgement | verified on hardware |
| Bulk OUT → device `Block_Read()` | verified (`RX_COMPLETE` observed on device) |
| Bulk IN ← device `Block_Write()` | verified |
| Behaviour before DEVICE_OPEN (no drain, no RX events) | verified |
| Other devices / firmware library versions | not verified - reports welcome |

## 8. Relationship to the official driver

The Silicon Labs host driver performs the `DEVICE_OPEN` handshake internally
when an application calls `SI_Open()`, which is why applications that use the
official DLL never have to care about it.  pyusbxpress implements the same
sequence over libusb so that the vendor driver is not required - in
particular on Linux and macOS, for which Silicon Labs does not provide a
driver.
