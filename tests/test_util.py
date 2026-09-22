import os
import tempfile
import unittest

from usbxpress.util import crc16_ccitt_false, hexdump, pad_packet, parse_ihex


class PadPacketTests(unittest.TestCase):
    def test_pads_short_payload(self):
        self.assertEqual(pad_packet(b"\x01\x02"), b"\x01\x02" + bytes(62))

    def test_full_packet_is_unchanged(self):
        packet = bytes(range(64))
        self.assertEqual(pad_packet(packet), packet)

    def test_rejects_oversized_payload(self):
        with self.assertRaises(ValueError):
            pad_packet(bytes(65))

    def test_custom_packet_size(self):
        self.assertEqual(pad_packet(b"\xaa", packet_size=4), b"\xaa\x00\x00\x00")


class Crc16Tests(unittest.TestCase):
    def test_check_value(self):
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_empty_input_returns_initial_value(self):
        self.assertEqual(crc16_ccitt_false(b""), 0xFFFF)


class HexdumpTests(unittest.TestCase):
    def test_shows_hex_and_ascii(self):
        text = hexdump(b"AB\x00")
        self.assertIn("41 42 00", text)
        self.assertIn("AB.", text)

    def test_empty_input(self):
        self.assertEqual(hexdump(b""), "")


class ParseIhexTests(unittest.TestCase):
    def _write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".hex", delete=False,
                                             encoding="ascii")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_reads_data_records(self):
        path = self._write(":0400000001020304F2\n:00000001FF\n")
        self.assertEqual(parse_ihex(path), {0: 1, 1: 2, 2: 3, 3: 4})

    def test_handles_linear_address_records(self):
        path = self._write(":020000040001F9\n:04000000AABBCCDDEE\n:00000001FF\n")
        memory = parse_ihex(path)
        self.assertEqual(memory[0x10000], 0xAA)
        self.assertEqual(memory[0x10003], 0xDD)

    def test_handles_segment_address_records(self):
        path = self._write(":020000021000EC\n:04000000AABBCCDDEE\n:00000001FF\n")
        memory = parse_ihex(path)
        self.assertEqual(memory[0x10000], 0xAA)
        self.assertEqual(memory[0x10003], 0xDD)

    def test_ignores_start_address_records(self):
        path = self._write(":0400000500002000D7\n:04000000AABBCCDDEE\n:00000001FF\n")
        self.assertEqual(parse_ihex(path)[0], 0xAA)

    def test_rejects_bad_checksum(self):
        path = self._write(":0400000001020304F3\n:00000001FF\n")
        with self.assertRaises(ValueError):
            parse_ihex(path)

    def test_rejects_unknown_record_type(self):
        path = self._write(":00000006FA\n:00000001FF\n")
        with self.assertRaises(ValueError):
            parse_ihex(path)


if __name__ == "__main__":
    unittest.main()
