import unittest

from usbxpress.backend_siusbxp import SiUsbXpBackend
from usbxpress.errors import UsbXpressError


class FakeDll:
    def __init__(self):
        self.calls = []
        self.flush_result = 0
        self.reset_result = 0

    def SI_FlushBuffers(self, handle, flush_transmit, flush_receive):
        self.calls.append(("flush", flush_transmit, flush_receive))
        return self.flush_result

    def SI_ResetDevice(self, handle):
        self.calls.append(("reset",))
        return self.reset_result

    def SI_Close(self, handle):
        self.calls.append(("close",))
        return 0


def make_backend():
    # bypass __init__ (it is Windows-only and loads SiUSBXp.dll)
    backend = object.__new__(SiUsbXpBackend)
    backend._dll = FakeDll()
    backend._handle = 0x1234
    backend._open_index = 0
    backend.serial = None
    return backend


class SiUsbXpBackendTests(unittest.TestCase):
    def test_flush_calls_si_flush_buffers(self):
        backend = make_backend()
        backend.flush()
        self.assertEqual(backend._dll.calls, [("flush", 1, 1)])

    def test_flush_maps_error_status(self):
        backend = make_backend()
        backend._dll.flush_result = 0x01
        with self.assertRaises(UsbXpressError):
            backend.flush()

    def test_flush_requires_an_open_device(self):
        backend = make_backend()
        backend._handle = None
        with self.assertRaises(UsbXpressError):
            backend.flush()

    def test_reset_calls_si_reset_device_and_reopens(self):
        backend = make_backend()
        backend._num_devices = lambda: 1
        backend.close = lambda: backend._dll.calls.append(("closed",))
        backend.open = lambda: backend._dll.calls.append(("opened",))
        backend.reset()
        self.assertEqual(backend._dll.calls,
                         [("reset",), ("closed",), ("opened",)])

    def test_reset_maps_error_status(self):
        backend = make_backend()
        backend._num_devices = lambda: 1
        backend._dll.reset_result = 0x05
        with self.assertRaises(UsbXpressError):
            backend.reset()

    def test_reset_refuses_with_several_devices(self):
        backend = make_backend()
        backend._num_devices = lambda: 2
        with self.assertRaises(UsbXpressError):
            backend.reset()


if __name__ == "__main__":
    unittest.main()
