# How the protocol was derived

The USBXpress wire protocol is not documented by Silicon Labs.  This page
describes the method used to recover it, so that the results can be
reproduced and extended to other firmware library versions.  No Silicon Labs
code or binaries are reproduced here or in this repository.

## 1. Make the device observable

Two things make the investigation tractable:

- The device firmware can report the library's **event bits** (see
  `PROTOCOL.md` §5) over any convenient side channel (a UART, a spare
  packet, ...).  Watching `RX_COMPLETE` / `TX_COMPLETE` / `DEVICE_OPEN`
  tells you whether the library accepted a request long before the host sees
  anything.
- A host can send **arbitrary vendor control requests** and observe whether
  the device acknowledges or STALLs them.  This turns "which request opens
  the data path" into a searchable question instead of a guess.

A practical setup is a small debug build that streams the event bit mask and
a few counters over a UART every few dozen milliseconds.

## 2. Locate the interesting library routines

The device library ships as a precompiled object library for the Keil C51
toolchain.  When it is linked into a project, the linker map file (`*.M51`)
lists every library function with its segment name, its `CODE` address and
its length, for example:

```text
?PR?USBXCORE_HANDLE_SETUP?USB_API      CODE    00FEH    0237H
?PR?USBXCORE_VENDOR_USB_API?USB_API    CODE    0C89H    0110H
?PR?_BLOCK_READ?BLOCK_READ             CODE    0B59H    0130H
```

The names are descriptive enough to identify:

- the control transfer dispatcher,
- the vendor request handler,
- the block read / block write routines.

## 3. Read the relevant code ranges

The linked image (Intel HEX) contains those routines at the addresses from
the map file, so a small script can extract exactly the byte ranges of
interest:

1. parse the Intel HEX file into a sparse address → byte map,
2. slice out `[address, address + length)` for each routine,
3. decode the 8051 instructions by hand or with any 8051 disassembler.

For this protocol, two patterns were enough to understand the behaviour:

- a **jump table** indexed by the setup packet's `bRequest` byte (three-byte
  entries: `LJMP`), which shows which request numbers reach which handler,
- comparisons of the stored `wValue` bytes against constants inside the
  vendor handler, which identify the `DEVICE_OPEN` / `DEVICE_CLOSE` /
  `FIFO_PURGE` selectors.

The block read routine starts with a check of an internal state byte that is
only set by the open selector - the direct explanation for "reads return
nothing until the host opens the device".

## 4. Verify against the device

Every conclusion was then checked on hardware:

1. scan `bmRequestType` x `bRequest` x `wValue` x `wLength` for requests the
   device acknowledges,
2. send the candidate open request and watch the device's event bits change
   (`DEVICE_OPEN` appears, then `RX_COMPLETE` starts firing),
3. write a packet to the bulk OUT endpoint and confirm the device's
   `Block_Read()` consumes it,
4. read the bulk IN endpoint and confirm device `Block_Write()` packets
   arrive.

Only after these four checks did the sequence go into `PROTOCOL.md`.

## 5. Tooling used

- Keil C51 linker map (`*.M51`) for symbol addresses and lengths.
- A ~40 line Python script to slice ranges out of an Intel HEX file.
- pyusb (libusb / WinUSB) for raw control and bulk transfers from the host.
- A device debug build that streams event bits over a UART.

## 6. Extending to other library versions

Different library builds will place the routines at different addresses, but
the method is unchanged: take the addresses from that project's map file and
re-run the checks.  If a future library version rejects the requests
documented here, the same scanning approach will find the new selectors.

## 7. Prior art and cross-checks

The protocol has been implemented in the open before; this project's results
were obtained independently (disassembly plus live device tests) and match:

- Craig Shelley's `SiUSBXp_Linux_Driver` (2010, GPL-2, libusb 0.1) — its
  `SI_Open` sends the same `DEVICE_OPEN` control request (`0x40 / 0x02 /
  wValue 0x0002`), `SI_Close` sends `0x0004`, and data moves over the bulk
  endpoints.
- `fMeow/silabs_usb_xpress` (2020, GPL-3, Rust) — a port of that driver,
  published on crates.io.

Those projects are shorter reads if you only need the request values; this
document describes the method, which also applies to other library versions
and other peripherals.  The agreement between an independent 2010
implementation and the behaviour observed here is a useful cross-check of
the findings.
