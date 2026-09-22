"""Silicon Labs USBXpress driver backend (Windows only).

Uses ``SiUSBXp.dll`` (the user mode part of the Silicon Labs USBXpress host
driver) through ctypes.  The driver performs the open/close handshake itself,
so this backend never sends vendor control requests.

Signatures and status codes follow ``SiUSBXp.h`` from the Silicon Labs
USBXpress SDK.
"""

from __future__ import annotations

import ctypes
import os
import sys

from .errors import UsbXpressError, UsbXpressNotFound
from .util import DEFAULT_PID, DEFAULT_VID, PACKET_SIZE, pad_packet

SI_RETURN_SERIAL_NUMBER = 0
SI_RETURN_DESCRIPTION = 1

#: ``SI_Read`` returns this when the read timeout expires (no data available).
SI_READ_TIMED_OUT = 0x0D

DLL_ENV_VAR = "SIUSBXP_DLL"

_DLL_CANDIDATES = (
    r"C:\SiLabs\MCU\USBXpress\USBXpress_API\Host\x64\SiUSBXp.dll",
    r"C:\SiLabs\MCU\USBXpress\USBXpress_API\Host\x86\SiUSBXp.dll",
    r"C:\SiliconLabs\USBXpressHostSDK\USBXpress_API\Host\x64\SiUSBXp.dll",
    r"C:\SiliconLabs\USBXpressHostSDK\USBXpress_API\Host\x86\SiUSBXp.dll",
    r"C:\Program Files\Silicon Labs\USBXpress\SiUSBXp.dll",
    r"C:\Program Files (x86)\Silicon Labs\USBXpress\SiUSBXp.dll",
    "SiUSBXp.dll",
)


def find_dll(explicit=None):
    """Return the first existing SiUSBXp.dll path, or None."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    from_env = os.environ.get(DLL_ENV_VAR)
    if from_env and os.path.isfile(from_env):
        return from_env
    for candidate in _DLL_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


class SiUsbXpBackend:
    """Transport backend using the Silicon Labs USBXpress host driver."""

    name = "siusbxp"

    def __init__(self, vid=DEFAULT_VID, pid=DEFAULT_PID, index=0, serial=None,
                 packet_size=PACKET_SIZE, timeout=1.0, dll_path=None):
        if not sys.platform.startswith("win"):
            raise UsbXpressError(
                "the siusbxp backend is Windows-only; use the libusb backend")
        self.vid = vid
        self.pid = pid
        self.index = index
        self.serial = serial
        self.packet_size = packet_size
        self.timeout = timeout
        self.dll_path = find_dll(dll_path)
        if self.dll_path is None:
            raise UsbXpressError(
                "SiUSBXp.dll not found; install the Silicon Labs USBXpress driver, "
                "pass dll_path=... or set the %s environment variable" % DLL_ENV_VAR)
        self._dll = ctypes.WinDLL(self.dll_path)
        self._bind()
        self._handle = None
        self._open_index = None

    def _bind(self):
        dll = self._dll
        dll.SI_GetNumDevices.argtypes = [ctypes.POINTER(ctypes.c_ulong)]
        dll.SI_GetNumDevices.restype = ctypes.c_int
        dll.SI_GetProductString.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
        dll.SI_GetProductString.restype = ctypes.c_int
        dll.SI_Open.argtypes = [ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
        dll.SI_Open.restype = ctypes.c_int
        dll.SI_Close.argtypes = [ctypes.c_void_p]
        dll.SI_Close.restype = ctypes.c_int
        dll.SI_Read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        dll.SI_Read.restype = ctypes.c_int
        dll.SI_Write.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                 ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        dll.SI_Write.restype = ctypes.c_int
        dll.SI_SetTimeouts.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        dll.SI_SetTimeouts.restype = ctypes.c_int

    # -- discovery ---------------------------------------------------------

    def _num_devices(self):
        count = ctypes.c_ulong(0)
        if self._dll.SI_GetNumDevices(ctypes.byref(count)) != 0:
            raise UsbXpressError("SI_GetNumDevices failed")
        return count.value

    def _product_string(self, device_number, flag):
        buffer = ctypes.create_string_buffer(256)
        if self._dll.SI_GetProductString(device_number, buffer, flag) != 0:
            return None
        return buffer.value.decode("ascii", "replace")

    def list_devices(self):
        devices = []
        for number in range(self._num_devices()):
            devices.append({
                "backend": self.name,
                "index": number,
                "serial": self._product_string(number, SI_RETURN_SERIAL_NUMBER),
                "product": self._product_string(number, SI_RETURN_DESCRIPTION),
            })
        return devices

    # -- lifecycle ---------------------------------------------------------

    def open(self):
        self.close()
        count = self._num_devices()
        if count == 0:
            raise UsbXpressNotFound(
                "no USBXpress device found by the Silicon Labs driver")
        index = self.index
        if self.serial is not None:
            for number in range(count):
                if self._product_string(number, SI_RETURN_SERIAL_NUMBER) == self.serial:
                    index = number
                    break
            else:
                raise UsbXpressNotFound(
                    "no USBXpress device with serial %r" % self.serial)
        if index >= count:
            raise UsbXpressNotFound(
                "device index %d out of range (%d attached)" % (index, count))
        timeout_ms = max(1, int(self.timeout * 1000))
        self._dll.SI_SetTimeouts(timeout_ms, timeout_ms)
        handle = ctypes.c_void_p()
        result = self._dll.SI_Open(index, ctypes.byref(handle))
        if result != 0:
            raise UsbXpressError(
                "SI_Open failed with 0x%02x (is the device bound to the Silicon Labs "
                "USBXpress driver? check that the DLL and driver versions match)"
                % (result & 0xFF))
        self._handle = handle
        self._open_index = index

    def close(self):
        handle, self._handle = self._handle, None
        self._open_index = None
        if handle:
            try:
                self._dll.SI_Close(handle)
            except Exception:
                pass

    # -- data path ---------------------------------------------------------

    def write_packet(self, data):
        if not self._handle:
            raise UsbXpressError("device is not open")
        try:
            packet = pad_packet(data, self.packet_size)
        except ValueError as exc:
            raise UsbXpressError(str(exc)) from exc
        buffer = ctypes.create_string_buffer(packet, len(packet))
        written = ctypes.c_ulong(0)
        result = self._dll.SI_Write(self._handle, buffer, len(packet),
                                    ctypes.byref(written), None)
        if result != 0:
            raise UsbXpressError("SI_Write failed with 0x%02x" % (result & 0xFF))

    def read_packet(self, timeout=None):
        if not self._handle:
            raise UsbXpressError("device is not open")
        if timeout is not None:
            timeout_ms = max(1, int(timeout * 1000))
            self._dll.SI_SetTimeouts(timeout_ms, timeout_ms)
        buffer = ctypes.create_string_buffer(self.packet_size)
        received = ctypes.c_ulong(0)
        result = self._dll.SI_Read(self._handle, buffer, self.packet_size,
                                   ctypes.byref(received), None)
        if result == SI_READ_TIMED_OUT:
            return None
        if result != 0:
            raise UsbXpressError("SI_Read failed with 0x%02x" % (result & 0xFF))
        if received.value == 0:
            return None
        return bytes(buffer.raw[:received.value])

    # -- info --------------------------------------------------------------

    @property
    def is_open(self):
        return self._handle is not None

    @property
    def info(self):
        if not self._handle:
            return {}
        index = self._open_index if self._open_index is not None else self.index
        return {
            "backend": self.name,
            "dll": self.dll_path,
            "index": index,
            "serial": self._product_string(index, SI_RETURN_SERIAL_NUMBER),
            "product": self._product_string(index, SI_RETURN_DESCRIPTION),
        }
