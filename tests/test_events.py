import unittest

from usbxpress import events


class DescribeTests(unittest.TestCase):
    def test_single_bit(self):
        self.assertEqual(events.describe(events.RX_COMPLETE), "RX_COMPLETE")

    def test_combined_bits(self):
        mask = events.USB_RESET | events.DEV_CONFIGURED
        self.assertEqual(events.describe(mask), "USB_RESET|DEV_CONFIGURED")

    def test_zero(self):
        self.assertEqual(events.describe(0), "0x00")

    def test_all_bits_cover_one_byte(self):
        mask = 0
        for bit in (events.USB_RESET, events.TX_COMPLETE, events.RX_COMPLETE,
                    events.FIFO_PURGE, events.DEVICE_OPEN, events.DEVICE_CLOSE,
                    events.DEV_CONFIGURED, events.DEV_SUSPEND):
            mask |= bit
        self.assertEqual(mask, 0xFF)


if __name__ == "__main__":
    unittest.main()
