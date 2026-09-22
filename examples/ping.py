"""Minimal command/response example.

Sends one 0x01 packet and prints the first response that starts with 0x01.
The meaning of the packets is application defined - adjust the command byte
and the expected reply for your firmware.

Usage:
    python examples/ping.py [--backend auto] [--vid 10c4] [--pid ea61]
"""

import argparse
import sys
from pathlib import Path

# allow running this file directly from a checkout without installing
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from usbxpress import UsbXpressDevice
from usbxpress.errors import UsbXpressError
from usbxpress.util import BACKENDS, hexdump

COMMAND = b"\x01"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=BACKENDS, default="auto")
    parser.add_argument("--vid", type=lambda text: int(text, 16), default=0x10C4)
    parser.add_argument("--pid", type=lambda text: int(text, 16), default=0xEA61)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=1.0)
    args = parser.parse_args(argv)

    try:
        with UsbXpressDevice(backend=args.backend, vid=args.vid, pid=args.pid,
                             index=args.index, timeout=args.timeout) as device:
            print("opened %04x:%04x via %s" % (args.vid, args.pid, device.backend_name))
            response = device.command(COMMAND)
            if response is None:
                print("no response to command %s" % COMMAND.hex(" "))
                return 1
            print("response (%d bytes):" % len(response))
            print(hexdump(response))
    except UsbXpressError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
