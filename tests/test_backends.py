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
        self.resets = 0

    def ctrl_transfer(self, bm_request_type, request, value, index, data, timeout=None):
        self.requests.append((bm_request_type, request, value, index, data))
        return 0

    def clear_halt(self, endpoint):
        pass

    def reset(self):
        self.resets += 1


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

    def test_flush_sends_the_purge_request(self):
        backend = make_backend()
        backend.flush()
        self.assertEqual(backend._dev.requests,
                         [(0x40, 0x02, 0x0001, 0, None)])

    def test_flush_drains_pending_packets(self):
        backend = make_backend(incoming=[b"\x01" + bytes(63), b"\x02" + bytes(63)])
        backend.flush()
        self.assertEqual(backend._ep_in.incoming, [])

    def test_reset_reopens_the_device(self):
        backend = make_backend()
        device = backend._dev
        opened = []
        backend.open = lambda: opened.append(True)
        backend.reset(reopen_timeout=0.5)
        self.assertEqual(device.resets, 1)
        self.assertEqual(opened, [True])

    def test_reset_refuses_with_several_matching_devices(self):
        backend = make_backend()
        backend._find_all = lambda: [object(), object()]
        with self.assertRaises(UsbXpressError):
            backend.reset(reopen_timeout=0.2)

    def test_reset_raises_when_the_device_does_not_return(self):
        backend = make_backend()
        device = backend._dev
        backend._find = lambda: None
        with self.assertRaises(UsbXpressError):
            backend.reset(reopen_timeout=0.2)
        self.assertEqual(device.resets, 1)

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


class BrokenEndpoint:
    def write(self, data, timeout=None):
        raise NotImplementedError("Operation not supported")

    def read(self, size, timeout=None):
        raise NotImplementedError("Operation not supported")


class BrokenDevice:
    def ctrl_transfer(self, *args, **kwargs):
        raise NotImplementedError("Operation not supported")


@unittest.skipUnless(HAVE_PYUSB, "pyusb is not installed")
class ErrorMappingTests(unittest.TestCase):
    """pyusb raises NotImplementedError for libusb codes without a message."""

    def test_open_maps_unmapped_error(self):
        class BadDevice:
            def set_configuration(self):
                raise NotImplementedError("Operation not supported")

            def get_active_configuration(self):
                raise NotImplementedError("Operation not supported")

        backend = LibusbBackend()
        backend._find = lambda: BadDevice()
        with self.assertRaises(UsbXpressError):
            backend.open()

    def test_read_maps_unmapped_error(self):
        backend = make_backend()
        backend._ep_in = BrokenEndpoint()
        with self.assertRaises(UsbXpressError):
            backend.read_packet(timeout=0.05)

    def test_write_maps_unmapped_error(self):
        backend = make_backend()
        backend._ep_out = BrokenEndpoint()
        with self.assertRaises(UsbXpressError):
            backend.write_packet(b"\x01")

    def test_vendor_request_maps_unmapped_error(self):
        backend = make_backend()
        backend._dev = BrokenDevice()
        with self.assertRaises(UsbXpressError):
            backend._vendor_request(REQUEST_DEVICE_OPEN)


if __name__ == "__main__":
    unittest.main()
