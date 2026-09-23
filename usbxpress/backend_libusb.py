"""libusb backend built on pyusb - Windows (WinUSB), Linux and macOS.

This backend talks to the device directly and therefore performs the
USBXpress ``DEVICE_OPEN`` handshake itself (see ``docs/PROTOCOL.md``).
"""

from __future__ import annotations

import sys
import time

from .errors import UsbXpressError, UsbXpressNotFound
from .util import DEFAULT_PID, DEFAULT_VID, PACKET_SIZE, pad_packet

#: USBXpress vendor control request (bmRequestType 0x40, bRequest 0x02).
VENDOR_REQUEST = 0x02
REQUEST_FIFO_PURGE = 0x0001
REQUEST_DEVICE_OPEN = 0x0002
REQUEST_DEVICE_CLOSE = 0x0004

_BULK = 0x02
_ENDPOINT_IN = 0x80


def _import_usb():
    """Import pyusb and prefer the libusb bundled by ``libusb-package``."""
    try:
        import usb.core
        import usb.util
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise UsbXpressError(
            "the libusb backend requires pyusb (pip install pyusb libusb-package)"
        ) from exc
    backend = None
    try:
        import libusb_package

        backend = libusb_package.get_libusb1_backend()
    except Exception:
        backend = None  # fall back to the system libusb
    return usb.core, usb.util, backend


def _is_timeout_error(exc) -> bool:
    if getattr(exc, "errno", None) in (110, 10060):  # ETIMEDOUT (POSIX / Winsock)
        return True
    return "timed out" in str(exc).lower()


def _usb_error_types(usb_core):
    """Exception types raised by pyusb for device I/O problems.

    Besides ``usb.core.USBError``, pyusb raises ``NotImplementedError`` for
    libusb error codes it has no message for (for example a transient
    ``LIBUSB_ERROR_NOT_SUPPORTED`` while a device re-enumerates).  Both must
    be mapped to ``UsbXpressError`` so callers see a stable contract.
    """
    return (usb_core.USBError, NotImplementedError)


def _platform_hint() -> str:
    if sys.platform.startswith("win"):
        return ("on Windows the device must be bound to WinUSB (for example with Zadig); "
                "alternatively use the siusbxp backend with the Silicon Labs driver installed")
    if sys.platform.startswith("linux"):
        return "on Linux see docs/LINUX.md (udev rule and permissions)"
    if sys.platform == "darwin":
        return "on macOS check 'system_profiler SPUSBDataType'"
    return "check that the device is connected and accessible"


class LibusbBackend:
    """Transport backend using libusb through pyusb."""

    name = "libusb"

    def __init__(self, vid=DEFAULT_VID, pid=DEFAULT_PID, index=0, serial=None,
                 packet_size=PACKET_SIZE, timeout=1.0, out_endpoint=None,
                 in_endpoint=None, device_open=True):
        self.vid = vid
        self.pid = pid
        self.index = index
        self.serial = serial
        self.packet_size = packet_size
        self.timeout = timeout
        self.out_endpoint = out_endpoint
        self.in_endpoint = in_endpoint
        self.device_open = device_open

        self._usb_core, self._usb_util, self._libusb_backend = _import_usb()
        self._usb_errors = _usb_error_types(self._usb_core)
        self._dev = None
        self._ep_out = None
        self._ep_in = None

    # -- discovery ---------------------------------------------------------

    def _find_all(self):
        return list(self._usb_core.find(
            find_all=True, idVendor=self.vid, idProduct=self.pid,
            backend=self._libusb_backend,
        ))

    def _find(self):
        devices = sorted(self._find_all(), key=lambda d: (d.bus or 0, d.address or 0))
        if self.serial is not None:
            devices = [d for d in devices
                       if self._read_string(d, d.iSerialNumber) == self.serial]
        if self.index >= len(devices):
            return None
        return devices[self.index]

    def _read_string(self, dev, index):
        if not index:
            return None
        try:
            return self._usb_util.get_string(dev, index)
        except Exception:
            return None

    def list_devices(self):
        """Return a list of dicts describing every matching device."""
        devices = []
        for dev in sorted(self._find_all(), key=lambda d: (d.bus or 0, d.address or 0)):
            devices.append({
                "backend": self.name,
                "bus": dev.bus,
                "address": dev.address,
                "vid": dev.idVendor,
                "pid": dev.idProduct,
                "serial": self._read_string(dev, dev.iSerialNumber),
                "product": self._read_string(dev, dev.iProduct),
            })
        return devices

    # -- lifecycle ---------------------------------------------------------

    def open(self):
        """Open the device and enable its data path (USBXpress DEVICE_OPEN)."""
        self.close()
        dev = self._find()
        if dev is None:
            raise UsbXpressNotFound(
                "no USBXpress device %04x:%04x found (%s)"
                % (self.vid, self.pid, _platform_hint()))
        self._dev = dev

        try:
            dev.set_configuration()
        except self._usb_errors:
            pass  # already configured
        try:
            cfg = dev.get_active_configuration()
            intf = cfg[(0, 0)]
            self._usb_util.claim_interface(dev, intf)
            self._ep_out = self._find_endpoint(intf, 0x00, self.out_endpoint)
            self._ep_in = self._find_endpoint(intf, _ENDPOINT_IN, self.in_endpoint)
            if self._ep_out is None or self._ep_in is None:
                raise UsbXpressError("bulk OUT/IN endpoints not found on interface 0")
            for endpoint in (self._ep_out, self._ep_in):
                try:
                    dev.clear_halt(endpoint)
                except self._usb_errors:
                    pass  # endpoint was not halted
            if self.device_open:
                self._vendor_request(REQUEST_DEVICE_OPEN)
        except UsbXpressError:
            self.close()
            raise
        except self._usb_errors as exc:
            self.close()
            raise UsbXpressError(
                "cannot open device: %s (%s)" % (exc, _platform_hint())) from exc

    def _find_endpoint(self, intf, direction, override):
        for endpoint in intf:
            if endpoint.bmAttributes != _BULK:
                continue
            if override is not None:
                if endpoint.bEndpointAddress == override:
                    return endpoint
                continue
            if (endpoint.bEndpointAddress & _ENDPOINT_IN) == direction:
                return endpoint
        return None

    def close(self):
        """Disable the data path (best effort) and release the device."""
        dev = self._dev
        self._dev = self._ep_out = self._ep_in = None
        if dev is None:
            return
        if self.device_open:
            try:
                self._vendor_request(REQUEST_DEVICE_CLOSE, dev=dev)
            except Exception:
                pass
        try:
            self._usb_util.release_interface(dev, 0)
        except Exception:
            pass
        try:
            self._usb_util.dispose_resources(dev)
        except Exception:
            pass

    def _vendor_request(self, value, dev=None):
        """Send one USBXpress vendor control request (no data stage)."""
        dev = dev or self._dev
        if dev is None:
            raise UsbXpressError("device is not open")
        timeout_ms = max(1, int(self.timeout * 1000))
        try:
            dev.ctrl_transfer(0x40, VENDOR_REQUEST, value, 0, None, timeout=timeout_ms)
        except self._usb_errors as exc:
            raise UsbXpressError(
                "vendor request 0x%04x failed: %s" % (value, exc)) from exc

    def flush(self):
        """Ask the device to purge its USB buffers and drop pending input.

        Sends the ``FIFO_PURGE`` vendor request and then drains any packets
        that were already in flight, so the next exchange starts clean.
        """
        self._vendor_request(REQUEST_FIFO_PURGE)
        deadline = time.monotonic() + 0.05
        while time.monotonic() < deadline:
            if self.read_packet(timeout=max(0.001, deadline - time.monotonic())) is None:
                return  # nothing pending

    def reset(self, reopen_timeout=5.0):
        """Reset the USB device (port reset) and reopen it.

        The device re-enumerates after the reset; this waits for it to come
        back and opens it again.  Refuses to run when several matching
        devices are attached and no serial was given, because the reopened
        device could be a different one.  Raises ``UsbXpressError`` when the
        device does not come back in time (the caller may retry :meth:`open`).
        """
        dev = self._dev
        if dev is None:
            raise UsbXpressError("device is not open")
        if self.serial is None and len(self._find_all()) > 1:
            raise UsbXpressError(
                "several matching devices are attached; pass serial= to reset "
                "a specific one")
        self._dev = self._ep_out = self._ep_in = None
        try:
            dev.reset()
        except self._usb_errors as exc:
            raise UsbXpressError("device reset failed: %s" % exc) from exc
        finally:
            try:
                self._usb_util.dispose_resources(dev)
            except Exception:
                pass

        deadline = time.monotonic() + reopen_timeout
        last_error = None
        while time.monotonic() < deadline:
            time.sleep(0.3)
            try:
                self.open()
                return
            except UsbXpressError as exc:
                last_error = exc
        raise UsbXpressError(
            "device did not re-appear after reset (%s)" % last_error)

    # -- data path ---------------------------------------------------------

    def write_packet(self, data):
        """Send one zero padded packet on the bulk OUT endpoint."""
        if self._dev is None:
            raise UsbXpressError("device is not open")
        try:
            packet = pad_packet(data, self.packet_size)
        except ValueError as exc:
            raise UsbXpressError(str(exc)) from exc
        timeout_ms = max(1, int(self.timeout * 1000))
        try:
            self._ep_out.write(packet, timeout=timeout_ms)
        except self._usb_errors as exc:
            raise UsbXpressError("bulk OUT write failed: %s" % exc) from exc

    def read_packet(self, timeout=None):
        """Return one packet from the bulk IN endpoint, or None on timeout."""
        if self._dev is None:
            raise UsbXpressError("device is not open")
        timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                data = bytes(self._ep_in.read(
                    self.packet_size, timeout=max(1, int(remaining * 1000))))
            except self._usb_errors as exc:
                if _is_timeout_error(exc):
                    continue  # keep polling until the deadline
                raise UsbXpressError("bulk IN read failed: %s" % exc) from exc
            if data:
                return data

    # -- info --------------------------------------------------------------

    @property
    def is_open(self):
        return self._dev is not None

    @property
    def info(self):
        dev = self._dev
        if dev is None:
            return {}
        return {
            "backend": self.name,
            "bus": dev.bus,
            "address": dev.address,
            "vid": dev.idVendor,
            "pid": dev.idProduct,
            "manufacturer": self._read_string(dev, dev.iManufacturer),
            "product": self._read_string(dev, dev.iProduct),
            "serial": self._read_string(dev, dev.iSerialNumber),
            "out_endpoint": hex(self._ep_out.bEndpointAddress) if self._ep_out else None,
            "in_endpoint": hex(self._ep_in.bEndpointAddress) if self._ep_in else None,
        }
