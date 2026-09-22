"""High level device object: one 64-byte packet per call."""

from __future__ import annotations

import sys
import time

from .errors import UsbXpressError
from .util import BACKENDS, DEFAULT_PID, DEFAULT_VID, PACKET_SIZE

_LIBUSB_KEYS = ("vid", "pid", "index", "serial", "packet_size", "timeout",
                "out_endpoint", "in_endpoint", "device_open")
_SIUSBXP_KEYS = ("vid", "pid", "index", "serial", "packet_size", "timeout", "dll_path")


def _select(keys, kwargs):
    return {key: kwargs[key] for key in keys if key in kwargs}


def make_backend(name="auto", **kwargs):
    """Create a transport backend.

    ``auto`` prefers libusb when it can see a device and falls back to the
    Silicon Labs driver on Windows when it cannot.
    """
    name = (name or "auto").lower()
    if name not in BACKENDS:
        raise UsbXpressError(
            "unknown backend %r (use one of %s)" % (name, ", ".join(BACKENDS)))

    def libusb_backend():
        from .backend_libusb import LibusbBackend

        return LibusbBackend(**_select(_LIBUSB_KEYS, kwargs))

    def siusbxp_backend():
        from .backend_siusbxp import SiUsbXpBackend

        return SiUsbXpBackend(**_select(_SIUSBXP_KEYS, kwargs))

    if name == "libusb":
        return libusb_backend()
    if name == "siusbxp":
        return siusbxp_backend()

    try:
        backend = libusb_backend()
        if backend.list_devices():
            return backend
    except Exception:
        pass  # pyusb or libusb unavailable, or no device visible
    if sys.platform.startswith("win"):
        try:
            return siusbxp_backend()
        except Exception:
            pass
    return libusb_backend()


def list_devices(backend="auto", **kwargs):
    """Return a list of dicts describing the attached devices."""
    if backend not in BACKENDS:
        raise UsbXpressError(
            "unknown backend %r (use one of %s)" % (backend, ", ".join(BACKENDS)))
    if backend == "libusb":
        return make_backend("libusb", **kwargs).list_devices()
    if backend == "siusbxp":
        return make_backend("siusbxp", **kwargs).list_devices()

    try:
        devices = make_backend("libusb", **kwargs).list_devices()
    except UsbXpressError:
        devices = []
    if devices:
        return devices
    if sys.platform.startswith("win"):
        try:
            return make_backend("siusbxp", **kwargs).list_devices()
        except UsbXpressError:
            return []
    return []


class UsbXpressDevice:
    """A USBXpress device.

    The class is intentionally thin: :meth:`write` sends one zero padded
    packet, :meth:`read` returns one packet, and :meth:`command` performs a
    send/receive exchange while skipping unsolicited packets.
    """

    def __init__(self, backend="auto", vid=DEFAULT_VID, pid=DEFAULT_PID, index=0,
                 serial=None, packet_size=PACKET_SIZE, timeout=1.0, dll_path=None,
                 out_endpoint=None, in_endpoint=None, device_open=True):
        self._timeout = timeout
        if isinstance(backend, str):
            backend = make_backend(
                backend, vid=vid, pid=pid, index=index, serial=serial,
                packet_size=packet_size, timeout=timeout, dll_path=dll_path,
                out_endpoint=out_endpoint, in_endpoint=in_endpoint,
                device_open=device_open,
            )
        # a backend instance may be passed directly (custom transports, tests)
        self._backend = backend

    # -- lifecycle ---------------------------------------------------------

    def open(self):
        """Open the device and enable its data path."""
        self._backend.open()
        return self

    def close(self):
        """Disable the data path and release the device."""
        self._backend.close()

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    # -- data --------------------------------------------------------------

    def write(self, data):
        """Send one packet (zero padded to the packet size)."""
        self._backend.write_packet(data)

    def read(self, timeout=None):
        """Return one packet, or None when nothing arrived within the timeout."""
        return self._backend.read_packet(timeout)

    def command(self, data, timeout=None, match=None):
        """Send ``data`` and return the first response starting with ``match``.

        ``match`` defaults to the first byte of ``data``.  Unsolicited packets
        (for example periodic heartbeats) are skipped.  Returns None when no
        matching response arrived within the timeout.
        """
        data = bytes(data)
        if not data:
            raise UsbXpressError("command must contain at least one byte")
        expected = data[0] if match is None else match
        self.write(data)
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            packet = self.read(timeout=remaining)
            if packet is None:
                return None
            if packet[0] == expected:
                return packet

    # -- properties --------------------------------------------------------

    @property
    def backend_name(self):
        return self._backend.name

    @property
    def is_open(self):
        return self._backend.is_open

    @property
    def info(self):
        """Device information as a dict (bus, address, ids, strings)."""
        return self._backend.info
