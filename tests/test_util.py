import unittest

from usbxpress.util import crc16_ccitt_false, hexdump, pad_packet


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


if __name__ == "__main__":
    unittest.main()
