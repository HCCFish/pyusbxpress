"""Exception types raised by pyusbxpress.

Timeouts are not exceptions: :meth:`UsbXpressDevice.read` and
:meth:`UsbXpressDevice.command` return ``None`` when nothing arrived in time.
"""


class UsbXpressError(Exception):
    """Base class for all pyusbxpress errors."""


class UsbXpressNotFound(UsbXpressError):
    """No matching USBXpress device was found."""
