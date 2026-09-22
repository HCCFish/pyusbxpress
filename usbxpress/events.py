"""USBXpress device event bits.

These are the bits returned by the device-side ``Get_Interrupt_Source()``
function of the USBXpress firmware library (``USB_API.h`` in the Silicon
Labs USBXpress SDK).  They are documented here because they are useful when
writing or debugging device firmware; a host cannot read them directly over
USB.  The bits can be surfaced to the host by firmware if needed (for
example, as part of a debug packet).
"""

USB_RESET = 0x01
TX_COMPLETE = 0x02
RX_COMPLETE = 0x04
FIFO_PURGE = 0x08
DEVICE_OPEN = 0x10
DEVICE_CLOSE = 0x20
DEV_CONFIGURED = 0x40
DEV_SUSPEND = 0x80

_NAMES = (
    (USB_RESET, "USB_RESET"),
    (TX_COMPLETE, "TX_COMPLETE"),
    (RX_COMPLETE, "RX_COMPLETE"),
    (FIFO_PURGE, "FIFO_PURGE"),
    (DEVICE_OPEN, "DEVICE_OPEN"),
    (DEVICE_CLOSE, "DEVICE_CLOSE"),
    (DEV_CONFIGURED, "DEV_CONFIGURED"),
    (DEV_SUSPEND, "DEV_SUSPEND"),
)


def describe(mask: int) -> str:
    """Return a human readable description of an event bit mask.

    >>> describe(0x41)
    'USB_RESET|DEV_CONFIGURED'
    >>> describe(0)
    '0x00'
    """
    names = [name for bit, name in _NAMES if mask & bit]
    return "|".join(names) if names else "0x00"
