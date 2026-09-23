"""pyusbxpress - cross-platform client for Silicon Labs USBXpress devices.

Unofficial, based on interoperability research; see README.md and
docs/PROTOCOL.md for details.
"""

from . import events
from .device import UsbXpressDevice, list_devices
from .errors import UsbXpressError, UsbXpressNotFound
from .util import BACKENDS, DEFAULT_PID, DEFAULT_VID, PACKET_SIZE

__version__ = "0.1.3"

__all__ = [
    "UsbXpressDevice",
    "UsbXpressError",
    "UsbXpressNotFound",
    "events",
    "list_devices",
    "BACKENDS",
    "DEFAULT_VID",
    "DEFAULT_PID",
    "PACKET_SIZE",
    "__version__",
]
