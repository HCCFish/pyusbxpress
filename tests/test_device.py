import unittest

from usbxpress.device import UsbXpressDevice
from usbxpress.errors import UsbXpressError


class FakeBackend:
    """Minimal in-memory transport used to exercise the device logic."""

    name = "fake"

    def __init__(self, incoming=()):
        self.incoming = list(incoming)
        self.written = []
        self.is_open = False
        self.info = {"backend": "fake"}

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write_packet(self, data):
        self.written.append(bytes(data))

    def read_packet(self, timeout=None):
        if self.incoming:
            return self.incoming.pop(0)
        return None

    def purge(self):
        pass


class DeviceTests(unittest.TestCase):
    def make(self, incoming=()):
        backend = FakeBackend(incoming)
        return backend, UsbXpressDevice(backend=backend, timeout=0.05)

    def test_context_manager_opens_and_closes(self):
        backend, device = self.make()
        with device:
            self.assertTrue(backend.is_open)
        self.assertFalse(backend.is_open)

    def test_write_forwards_the_payload(self):
        backend, device = self.make()
        device.write(b"\x01\x02")
        self.assertEqual(backend.written, [b"\x01\x02"])

    def test_command_returns_the_matching_packet(self):
        backend, device = self.make([b"\x01\x55\xaa"])
        self.assertEqual(device.command(b"\x01"), b"\x01\x55\xaa")

    def test_command_skips_unrelated_packets(self):
        backend, device = self.make([b"\xee" + bytes(20), b"\x02\x55"])
        self.assertEqual(device.command(b"\x02", match=0x02), b"\x02\x55")

    def test_command_returns_none_on_timeout(self):
        backend, device = self.make([b"\xee" + bytes(20)])
        self.assertIsNone(device.command(b"\x01"))

    def test_command_rejects_empty_payload(self):
        backend, device = self.make()
        with self.assertRaises(UsbXpressError):
            device.command(b"")


if __name__ == "__main__":
    unittest.main()
