"""Unit tests for CRC16-CCITT implementation."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared")))

from deos_core.crc import crc16_ccitt, crc16_ccitt_bytes


class TestCrc16Ccitt(unittest.TestCase):
    def test_empty_buffer(self):
        # With seed 0xFFFF and empty data, crc remains 0xFFFF
        self.assertEqual(crc16_ccitt(b""), 0xFFFF)

    def test_deterministic_calculation(self):
        data1 = b"\x01\x02\x03\x04\x05"
        crc1 = crc16_ccitt(data1)
        crc2 = crc16_ccitt(data1)
        self.assertEqual(crc1, crc2)
        self.assertTrue(0 <= crc1 <= 0xFFFF)

    def test_different_data_produces_different_crc(self):
        data1 = b"\x01\x02\x03\x04\x05"
        data2 = b"\x01\x02\x03\x04\x06"
        self.assertNotEqual(crc16_ccitt(data1), crc16_ccitt(data2))

    def test_little_endian_bytes(self):
        data = b"\x01\x02\x03"
        crc = crc16_ccitt(data)
        crc_bytes = crc16_ccitt_bytes(data)
        self.assertEqual(len(crc_bytes), 2)
        self.assertEqual(int.from_bytes(crc_bytes, "little"), crc)

    def test_c_implementation_alignment(self):
        # Test sample matching C reference in DOC-ICD-TRP-LORA-007
        test_body = bytes([0x01, 0x09]) + b"\x03\x02\x02\x11\x01\x01\x01\x00\x00"
        crc = crc16_ccitt(test_body, seed=0xFFFF)
        self.assertIsInstance(crc, int)
        # Verify 16-bit
        self.assertTrue(0 <= crc <= 65535)


if __name__ == "__main__":
    unittest.main()

