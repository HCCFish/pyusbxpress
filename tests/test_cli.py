import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import usbxpress.cli as cli
from usbxpress.cli import _hex_bytes, build_parser
from usbxpress.util import PACKET_SIZE


class HexBytesTests(unittest.TestCase):
    def test_parses_space_separated_bytes(self):
        self.assertEqual(_hex_bytes("01 55 aa"), b"\x01\x55\xaa")

    def test_parses_commas_and_0x_prefixes(self):
        self.assertEqual(_hex_bytes("0x01,0x02"), b"\x01\x02")

    def test_rejects_garbage(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            _hex_bytes("zz")


class ParserTests(unittest.TestCase):
    def test_requires_a_subcommand(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_defaults(self):
        args = build_parser().parse_args(["info"])
        self.assertEqual(args.vid, 0x10C4)
        self.assertEqual(args.pid, 0xEA61)
        self.assertEqual(args.backend, "auto")
        self.assertEqual(args.timeout, 1.0)


class FakeDevice:
    """Stand-in for UsbXpressDevice that records what the CLI sends."""

    instances = []
    backend_name = "fake"
    info = {"backend": "fake", "vid": 0x10C4, "pid": 0xEA61}

    def __init__(self, *args, **kwargs):
        self.written = []
        FakeDevice.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, data):
        self.written.append(bytes(data))

    def command(self, data, match=None, timeout=None):
        return bytes([data[0], 0x55]) + bytes(8)


class MainTests(unittest.TestCase):
    def setUp(self):
        FakeDevice.instances = []
        self._original_device = cli.UsbXpressDevice
        self._original_list = cli.list_devices
        cli.UsbXpressDevice = FakeDevice

    def tearDown(self):
        cli.UsbXpressDevice = self._original_device
        cli.list_devices = self._original_list

    def test_list_prints_devices(self):
        cli.list_devices = lambda **kwargs: [
            {"backend": "libusb", "bus": 1, "address": 2, "serial": "S", "product": "P"}]
        with redirect_stdout(io.StringIO()) as output:
            code = cli.main(["list"])
        self.assertEqual(code, 0)
        self.assertIn("10c4:ea61", output.getvalue())

    def test_list_reports_when_no_device_is_found(self):
        cli.list_devices = lambda **kwargs: []
        with redirect_stdout(io.StringIO()) as output:
            code = cli.main(["list"])
        self.assertEqual(code, 1)
        self.assertIn("no USBXpress device", output.getvalue())

    def test_info_send_prints_the_response(self):
        with redirect_stdout(io.StringIO()) as output:
            code = cli.main(["info", "--send", "01"])
        self.assertEqual(code, 0)
        self.assertIn("response (10 bytes)", output.getvalue())

    def test_write_sends_one_packet(self):
        with redirect_stdout(io.StringIO()):
            code = cli.main(["write", "--hex", "01 55"])
        self.assertEqual(code, 0)
        self.assertEqual(FakeDevice.instances[-1].written, [b"\x01\x55"])

    def test_write_rejects_a_file_larger_than_one_packet(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(bytes(PACKET_SIZE + 1))
            path = handle.name
        try:
            with redirect_stderr(io.StringIO()) as errors:
                code = cli.main(["write", "--file", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 1)
        self.assertIn("larger than one", errors.getvalue())

    def test_write_rejects_an_empty_payload(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            path = handle.name
        try:
            with redirect_stderr(io.StringIO()) as errors:
                code = cli.main(["write", "--file", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 2)
        self.assertIn("nothing to send", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
