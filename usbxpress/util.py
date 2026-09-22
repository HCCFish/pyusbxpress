"""Constants and small helpers shared across the package."""

DEFAULT_VID = 0x10C4
DEFAULT_PID = 0xEA61
PACKET_SIZE = 64

#: Valid values for the ``backend`` argument / ``--backend`` option.
BACKENDS = ("auto", "libusb", "siusbxp")


def pad_packet(data, packet_size=PACKET_SIZE):
    """Return ``data`` padded with zero bytes to one full USBXpress packet.

    USBXpress devices expect fixed size packets on the bulk endpoints; short
    packets are zero padded.  Raises ``ValueError`` when the payload does not
    fit into a single packet.
    """
    data = bytes(data)
    if len(data) > packet_size:
        raise ValueError("payload of %d bytes does not fit into a %d byte packet"
                         % (len(data), packet_size))
    if len(data) < packet_size:
        data += bytes(packet_size - len(data))
    return data


def crc16_ccitt_false(data, crc=0xFFFF):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, no xorout).

    Check value for ``b"123456789"`` is ``0x29B1``.
    """
    for byte in bytes(data):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def hexdump(data, width=16):
    """Return a hex/ASCII dump, one line per ``width`` bytes."""
    data = bytes(data)
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hex_part = " ".join("%02x" % b for b in chunk).ljust(width * 3 - 1)
        text_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append("%04x  %s  %s" % (offset, hex_part, text_part))
    return "\n".join(lines)
