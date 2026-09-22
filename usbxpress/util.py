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


def parse_ihex(path):
    """Return a sparse ``address -> byte`` map from an Intel HEX file.

    Data records (type 00) and the extended address records (type 02 segment
    and type 04 linear) are handled; start address records (03/05) are
    ignored and anything else is rejected.  Every record is checksum
    verified.  Raises ``ValueError`` on malformed input.

    This is a tooling helper (used by the examples); it is not part of the
    USBXpress transport.
    """
    memory = {}
    base = 0
    with open(path, "r", encoding="ascii") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise ValueError("line %d: not an Intel HEX record" % number)
            try:
                raw = bytes.fromhex(line[1:])
            except ValueError as exc:
                raise ValueError("line %d: invalid hex data" % number) from exc
            if len(raw) < 5:
                raise ValueError("line %d: record too short" % number)
            count, address, record_type = raw[0], (raw[1] << 8) | raw[2], raw[3]
            data = raw[4:4 + count]
            if len(data) != count or len(raw) != count + 5:
                raise ValueError("line %d: record length mismatch" % number)
            if sum(raw) & 0xFF:
                raise ValueError("line %d: checksum mismatch" % number)

            if record_type == 0:
                for offset, value in enumerate(data):
                    memory[base + address + offset] = value
            elif record_type == 1:
                break
            elif record_type == 2:
                if count != 2:
                    raise ValueError("line %d: bad segment record" % number)
                base = ((data[0] << 8) | data[1]) << 4
            elif record_type == 4:
                if count != 2:
                    raise ValueError("line %d: bad linear address record" % number)
                base = ((data[0] << 8) | data[1]) << 16
            elif record_type in (3, 5):
                continue  # start address records are not needed here
            else:
                raise ValueError(
                    "line %d: unsupported record type %d" % (number, record_type))
    return memory
