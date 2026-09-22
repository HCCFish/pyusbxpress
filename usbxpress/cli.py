"""Command line interface: ``usbxpress list|info|monitor|write``."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .device import UsbXpressDevice, list_devices
from .errors import UsbXpressError
from .util import BACKENDS, DEFAULT_PID, DEFAULT_VID, PACKET_SIZE, hexdump


def _hex_int(text):
    try:
        return int(text, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a hexadecimal number") from exc


def _hex_bytes(text):
    cleaned = text.replace(",", " ").replace("0x", " ").replace("0X", " ")
    try:
        return bytes(int(token, 16) for token in cleaned.split())
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected hex bytes such as "01 55 aa"') from exc


def _add_common_options(parser):
    parser.add_argument("--vid", type=_hex_int, default=DEFAULT_VID,
                        help="vendor ID (default: %04x)" % DEFAULT_VID)
    parser.add_argument("--pid", type=_hex_int, default=DEFAULT_PID,
                        help="product ID (default: %04x)" % DEFAULT_PID)
    parser.add_argument("--index", type=int, default=0,
                        help="device index when several are attached")
    parser.add_argument("--serial", help="select the device by serial string")
    parser.add_argument("--backend", choices=BACKENDS, default="auto",
                        help="transport backend (default: auto)")
    parser.add_argument("--dll", help="SiUSBXp.dll path (siusbxp backend only)")
    parser.add_argument("--timeout", type=float, default=1.0,
                        help="per transfer timeout in seconds (default: 1.0)")


def _make_device(args):
    return UsbXpressDevice(
        backend=args.backend, vid=args.vid, pid=args.pid, index=args.index,
        serial=args.serial, timeout=args.timeout, dll_path=args.dll,
    )


def _backend_kwargs(args):
    return dict(vid=args.vid, pid=args.pid, index=args.index, serial=args.serial,
                timeout=args.timeout, dll_path=args.dll)


def cmd_list(args):
    devices = list_devices(backend=args.backend, **_backend_kwargs(args))
    if not devices:
        print("no USBXpress device %04x:%04x found" % (args.vid, args.pid))
        return 1
    for position, device in enumerate(devices):
        if "bus" in device:
            where = "bus %s address %s" % (device.get("bus"), device.get("address"))
        else:
            where = "index %s" % device.get("index", position)
        print("[%d] %-7s %-24s %04x:%04x  serial=%s  product=%s"
              % (position, device.get("backend"), where, args.vid, args.pid,
                 device.get("serial"), device.get("product")))
    return 0


def cmd_info(args):
    with _make_device(args) as device:
        for key, value in device.info.items():
            if key in ("vid", "pid") and isinstance(value, int):
                value = "%04x" % value
            print("%s: %s" % (key, value))
        if args.send:
            print("send:", args.send.hex(" "))
            response = device.command(args.send)
            if response is None:
                print("no matching response")
                return 1
            print("response (%d bytes):" % len(response))
            print(hexdump(response))
    return 0


def cmd_monitor(args):
    with _make_device(args) as device:
        print("monitoring %04x:%04x via %s - press Ctrl+C to stop"
              % (args.vid, args.pid, device.backend_name))
        next_send = 0.0
        try:
            while True:
                if args.send and time.monotonic() >= next_send:
                    device.write(args.send)
                    next_send = time.monotonic() + max(args.interval, 0.001)
                packet = device.read(timeout=0.5)
                if packet is None:
                    continue
                print("%s  %s" % (time.strftime("%H:%M:%S"), packet.hex(" ")))
        except KeyboardInterrupt:
            print("stopped")
    return 0


def _read_payload_file(path):
    """Read a file that must fit into a single packet."""
    with open(path, "rb") as handle:
        payload = handle.read(PACKET_SIZE + 1)
    if len(payload) > PACKET_SIZE:
        raise UsbXpressError(
            "file is larger than one %d byte packet" % PACKET_SIZE)
    return payload


def cmd_write(args):
    payload = args.hex or (args.text.encode("utf-8") if args.text else None)
    if payload is None and args.file:
        payload = _read_payload_file(args.file)
    if not payload:
        print("nothing to send: use --hex, --text or --file", file=sys.stderr)
        return 2
    with _make_device(args) as device:
        if args.expect is not None:
            response = device.command(payload, match=args.expect)
            if response is None:
                print("no matching response")
                return 1
            print("response (%d bytes):" % len(response))
            print(hexdump(response))
        else:
            device.write(payload)
            print("sent %d byte(s)" % len(payload))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="usbxpress",
        description="Talk to Silicon Labs USBXpress devices without the vendor driver.",
    )
    parser.add_argument("--version", action="version",
                        version="pyusbxpress %s" % __version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list", help="list matching devices")
    _add_common_options(p_list)
    p_list.set_defaults(func=cmd_list)

    p_info = subparsers.add_parser("info", help="show device information")
    _add_common_options(p_info)
    p_info.add_argument("--send", type=_hex_bytes,
                        help='send one packet, e.g. --send "01"')
    p_info.set_defaults(func=cmd_info)

    p_monitor = subparsers.add_parser("monitor", help="print incoming packets")
    _add_common_options(p_monitor)
    p_monitor.add_argument("--send", type=_hex_bytes,
                           help="packet to send repeatedly")
    p_monitor.add_argument("--interval", type=float, default=1.0,
                           help="seconds between --send packets (default: 1.0)")
    p_monitor.set_defaults(func=cmd_monitor)

    p_write = subparsers.add_parser("write", help="send a single packet")
    _add_common_options(p_write)
    source = p_write.add_mutually_exclusive_group(required=True)
    source.add_argument("--hex", type=_hex_bytes, help='hex bytes, e.g. "01 55"')
    source.add_argument("--text", help="text to send as UTF-8 bytes")
    source.add_argument("--file", help="file to send (must fit one packet)")
    p_write.add_argument("--expect", type=_hex_int,
                         help="wait for a response whose first byte equals this value")
    p_write.set_defaults(func=cmd_write)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (UsbXpressError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
