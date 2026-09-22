import unittest

try:
    import usb.core

    HAVE_PYUSB = True
except ImportError:  # pragma: no cover - depends on environment
    HAVE_PYUSB = False

from usbxpress.backend_libusb import (REQUEST_DEVICE_CLOSE, REQUEST_DEVICE_OPEN,
                                      LibusbBackend)
from usbxpress.errors import UsbXpressError
from usbxpress.util import PACKET_SIZE


class FakeEndpoint:
    def __init__(self, incoming=None):
        self.written = []
        self.incoming = list(incoming or [])

    def write(self, data, timeout=None):
        self.written.append(bytes(data))

    def read(self, size, timeout=None):
        if self.incoming:
            return self.incoming.pop(0)
        raise usb.core.USBError("Operation timed out")


class FakeDevice:
    def __init__(self):
        self.requests = []

    def ctrl_transfer(self, bm_request_type, request, value, index, data, timeout=None):
        self.requests.append((bm_request_type, request, value, index, data))
        return 0

    def clear_halt(self, endpoint):
        pass


def make_backend(incoming=None):
    backend = LibusbBackend()
    backend._dev = FakeDevice()
    backend._ep_out = FakeEndpoint()
    backend._ep_in = FakeEndpoint(incoming)
    return backend


@unittest.skipUnless(HAVE_PYUSB, "pyusb is not installed")
class VendorRequestTests(unittest.TestCase):
    def test_open_request_values(self):
        backend = make_backend()
        backend._vendor_request(REQUEST_DEVICE_OPEN)
        self.assertEqual(backend._dev.requests,
                         [(0x40, 0x02, 0x0002, 0, None)])

    def test_close_request_values(self):
        backend = make_backend()
        backend._vendor_request(REQUEST_DEVICE_CLOSE)
        self.assertEqual(backend._dev.requests,
                         [(0x40, 0x02, 0x0004, 0, None)])

    def test_vendor_request_without_device_raises(self):
        backend = LibusbBackend()
        with self.assertRaises(UsbXpressError):
            backend._vendor_request(REQUEST_DEVICE_OPEN)


@unittest.skipUnless(HAVE_PYUSB, "pyusb is not installed")
class PacketTests(unittest.TestCase):
    def test_write_pads_to_one_packet(self):
        backend = make_backend()
        backend.write_packet(b"\x01")
        self.assertEqual(backend._ep_out.written,
                         [b"\x01" + bytes(PACKET_SIZE - 1)])

    def test_write_rejects_oversized_payload(self):
        backend = make_backend()
        with self.assertRaises(UsbXpressError):
            backend.write_packet(bytes(PACKET_SIZE + 1))

    def test_write_requires_an_open_device(self):
        backend = LibusbBackend()
        with self.assertRaises(UsbXpressError):
            backend.write_packet(b"\x01")

    def test_read_returns_a_packet(self):
        backend = make_backend(incoming=[b"\x01\x55"])
        self.assertEqual(backend.read_packet(timeout=0.05), b"\x01\x55")

    def test_read_returns_none_on_timeout(self):
        backend = make_backend()
        self.assertIsNone(backend.read_packet(timeout=0.05))


if __name__ == "__main__":
    unittest.main()
