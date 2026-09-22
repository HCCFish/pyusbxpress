"""Flash an Intel HEX image through a USBXpress bootloader (example).

This example implements a *reference bootloader protocol* over 64-byte
USBXpress packets:

    host -> device
        0x01                    query (returns a descriptor starting with "BL")
        0x02 hi lo              erase the 512-byte page containing hi:lo
        0x03 hi lo len data..   write len bytes at hi:lo (max 58 per packet)
        0x04 hi lo len          read len bytes from hi:lo (max 60 per packet)
        0x05                    go: validate the application and start it

    device -> host
        0x01 55 "BL" ...        query response (checked before flashing)
        0x02 55 / 0x03 55 / 0x05 55   acknowledgement
        0x04 55 len data..      read response

The application image lives at ``APP_BASE``; the bootloader verifies an
8-byte record at ``RECORD_ADDR`` ('BL' + length + CRC-16/CCITT-FALSE over
the code area) before starting the application.

This is an example, not part of the pyusbxpress library - adjust the
constants below for your own bootloader.

Usage:
    python examples/flash_demo.py firmware.hex [--info-only] [--no-verify]
"""

import argparse
import sys
from pathlib import Path

# allow running this file directly from a checkout without installing
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from usbxpress import UsbXpressDevice
from usbxpress.errors import UsbXpressError
from usbxpress.util import BACKENDS, crc16_ccitt_false

CMD_QUERY = 0x01
CMD_ERASE = 0x02
CMD_WRITE = 0x03
CMD_READ = 0x04
CMD_GO = 0x05

APP_BASE = 0x2000        # application reset entry / vector table
CODE_BASE = 0x2200       # start of the relocatable application code
WRITE_LIMIT = 0xF000     # first address the bootloader refuses to write
RECORD_ADDR = 0x2100     # validity record location
PAGE_SIZE = 0x200        # flash page size
WRITE_CHUNK = 58         # payload bytes per write packet (4-byte header)
READ_CHUNK = 60          # payload bytes per read packet (3-byte header)


def parse_ihex(path):
    """Return a sparse address -> byte map from an Intel HEX file.

    Data records (type 00) and the extended address records (type 02 segment
    and type 04 linear) are handled; start address records (03/05) are
    ignored and anything else is rejected.  Every record is checksum
    verified.
    """
    memory = {}
    base = 0
    with open(path, "r", encoding="ascii") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise UsbXpressError("line %d: not an Intel HEX record" % number)
            try:
                raw = bytes.fromhex(line[1:])
            except ValueError as exc:
                raise UsbXpressError("line %d: invalid hex data" % number) from exc
            if len(raw) < 5:
                raise UsbXpressError("line %d: record too short" % number)
            count, address, record_type = raw[0], (raw[1] << 8) | raw[2], raw[3]
            data = raw[4:4 + count]
            if len(data) != count or len(raw) != count + 5:
                raise UsbXpressError("line %d: record length mismatch" % number)
            if sum(raw) & 0xFF:
                raise UsbXpressError("line %d: checksum mismatch" % number)

            if record_type == 0:
                for offset, value in enumerate(data):
                    memory[base + address + offset] = value
            elif record_type == 1:
                break
            elif record_type == 2:
                if count != 2:
                    raise UsbXpressError("line %d: bad segment record" % number)
                base = ((data[0] << 8) | data[1]) << 4
            elif record_type == 4:
                if count != 2:
                    raise UsbXpressError("line %d: bad linear address record" % number)
                base = ((data[0] << 8) | data[1]) << 16
            elif record_type in (3, 5):
                continue  # start address records are not needed here
            else:
                raise UsbXpressError(
                    "line %d: unsupported record type %d" % (number, record_type))
    return memory


def bl_command(device, packet, retries=1):
    """Send one command packet and return the matching response.

    A missing response is retried (packets can be lost), backend errors are
    re-raised.
    """
    response = None
    for _ in range(retries + 1):
        try:
            response = device.command(packet)
        except UsbXpressError:
            response = None
        if response is not None:
            break
    if response is None:
        raise UsbXpressError("no response to command 0x%02x" % packet[0])
    if response[1] != 0x55:
        raise UsbXpressError("command 0x%02x failed: %s" % (packet[0], response.hex(" ")))
    return response


def bl_read(device, address, length):
    """Read ``length`` bytes starting at ``address`` (up to READ_CHUNK per packet)."""
    data = bytearray()
    while length > 0:
        chunk = min(length, READ_CHUNK)
        response = bl_command(device, bytes([CMD_READ, (address >> 8) & 0xFF,
                                             address & 0xFF, chunk]))
        if len(response) < 3 + chunk:
            raise UsbXpressError("short read response: %s" % response.hex(" "))
        data += response[3:3 + chunk]
        address += chunk
        length -= chunk
    return bytes(data)


def flash(device, memory, verify=True):
    """Erase, write and verify the image, then write the record and start it."""
    below = sorted(address for address in memory if address < APP_BASE)
    if below:
        shown = " ".join("0x%04X" % address for address in below[:4])
        print("note: skipping %d record(s) below 0x%04X (%s%s)"
              % (len(below), APP_BASE, shown, " ..." if len(below) > 4 else ""))
        memory = {address: value for address, value in memory.items()
                  if address >= APP_BASE}

    if not memory:
        raise UsbXpressError("image contains no data at or above 0x%04X" % APP_BASE)
    low = min(memory)
    high = max(memory)
    if (high + 1) <= CODE_BASE:
        raise UsbXpressError(
            "image ends below 0x%04X, there is no code to verify" % CODE_BASE)
    if (high + 1) > WRITE_LIMIT:
        raise UsbXpressError("image ends above 0x%04X" % WRITE_LIMIT)

    pages = sorted({address & ~(PAGE_SIZE - 1) for address in memory})
    record_page = RECORD_ADDR & ~(PAGE_SIZE - 1)
    if record_page not in pages:
        raise UsbXpressError("image does not cover the record page 0x%04X" % record_page)

    code = bytes(memory.get(address, 0xFF)
                 for address in range(CODE_BASE, high + 1))
    crc = crc16_ccitt_false(code)
    length = high + 1 - CODE_BASE
    record = b"BL" + bytes([(length >> 8) & 0xFF, length & 0xFF,
                            (crc >> 8) & 0xFF, crc & 0xFF, 0xFF, 0xFF])
    if any(memory.get(RECORD_ADDR + offset, 0xFF) != 0xFF
           for offset in range(len(record))):
        raise UsbXpressError("image contains data at the record address")

    print("image 0x%04X-0x%04X, %d page(s), record crc=0x%04X"
          % (low, high, len(pages), crc))
    for index, page in enumerate(pages, start=1):
        bl_command(device, bytes([CMD_ERASE, (page >> 8) & 0xFF, page & 0xFF]))
        expected = bytes(memory.get(page + offset, 0xFF) for offset in range(PAGE_SIZE))
        for offset in range(0, PAGE_SIZE, WRITE_CHUNK):
            chunk = expected[offset:offset + WRITE_CHUNK]
            bl_command(device, bytes([CMD_WRITE, ((page + offset) >> 8) & 0xFF,
                                      (page + offset) & 0xFF, len(chunk)]) + chunk)
        if verify:
            got = bl_read(device, page, PAGE_SIZE)
            if got != expected:
                bad = next(i for i in range(PAGE_SIZE) if got[i] != expected[i])
                raise UsbXpressError("verify failed at 0x%04X" % (page + bad))
        print("page 0x%04X written%s (%d/%d)"
              % (page, " + verified" if verify else "", index, len(pages)))

    bl_command(device, bytes([CMD_WRITE, (RECORD_ADDR >> 8) & 0xFF,
                              RECORD_ADDR & 0xFF, len(record)]) + record)
    print("validity record written (length=%d, crc=0x%04X)" % (length, crc))
    print("sending GO ...")
    bl_command(device, bytes([CMD_GO]), retries=0)  # the device resets, no retry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("hexfile", nargs="?", help="Intel HEX image to flash")
    parser.add_argument("--backend", choices=BACKENDS, default="auto")
    parser.add_argument("--vid", type=lambda text: int(text, 16), default=0x10C4)
    parser.add_argument("--pid", type=lambda text: int(text, 16), default=0xEA61)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--info-only", action="store_true",
                        help="only query the bootloader descriptor")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip read-back verification")
    args = parser.parse_args(argv)

    try:
        with UsbXpressDevice(backend=args.backend, vid=args.vid, pid=args.pid,
                             index=args.index, timeout=args.timeout) as device:
            response = bl_command(device, bytes([CMD_QUERY]))
            if response[2:4] != b"BL":
                raise UsbXpressError(
                    "device is not in bootloader mode (query response: %s)"
                    % response.hex(" "))
            print("bootloader descriptor: %s" % response[2:].hex(" "))
            if args.info_only:
                return 0
            if not args.hexfile:
                parser.error("a HEX file is required unless --info-only is used")
            flash(device, parse_ihex(args.hexfile), verify=not args.no_verify)
    except UsbXpressError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
