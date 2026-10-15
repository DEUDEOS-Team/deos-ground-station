"""Unit tests for Universal DEOS Transport Framing and LoRa L2 Packaging."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared")))

from deos_core import (
    UniversalDeosFrame,
    wrap_lora_packet,
    create_lora_ack,
    unwrap_lora_stream,
    LoraFlag,
    LORA_MAGIC,
    crc16_ccitt,
)


class TestFraming(unittest.TestCase):
    def test_universal_9b_symmetry(self):
        frame = UniversalDeosFrame(
            destination=0x10,
            source=0x02,
            priority=0x02,
            version=0x11,
            message_class=0x01,
            service=0x01,
            command=0x01,
            sequence=42,
            payload=b"\x01\x02\x03\x04",
        )
        encoded = frame.encode(layout="UNIVERSAL_9B")
        self.assertEqual(len(encoded), 9 + 4)
        # Check header fields
        self.assertEqual(encoded[0], 0x10)  # dest
        self.assertEqual(encoded[1], 0x02)  # src
        self.assertEqual(encoded[2], 0x02)  # prio
        self.assertEqual(encoded[3], 0x11)  # version
        self.assertEqual(encoded[4], 0x01)  # class
        self.assertEqual(encoded[5], 0x01)  # service
        self.assertEqual(encoded[6], 0x01)  # command
        self.assertEqual(encoded[7], 42)    # sequence
        self.assertEqual(encoded[8], 4)     # payload length
        self.assertEqual(encoded[9:], b"\x01\x02\x03\x04")

        # Decode back
        decoded = UniversalDeosFrame.decode(encoded, layout="UNIVERSAL_9B")
        self.assertEqual(decoded.destination, frame.destination)
        self.assertEqual(decoded.source, frame.source)
        self.assertEqual(decoded.priority, frame.priority)
        self.assertEqual(decoded.version, frame.version)
        self.assertEqual(decoded.message_class, frame.message_class)
        self.assertEqual(decoded.service, frame.service)
        self.assertEqual(decoded.command, frame.command)
        self.assertEqual(decoded.sequence, frame.sequence)
        self.assertEqual(decoded.payload, frame.payload)

    def test_common_8b_symmetry(self):
        frame = UniversalDeosFrame(
            destination=0x03,
            source=0x02,
            priority=0x05,
            version=0x11,
            message_class=0x07,
            service=0x00,
            command=0x08,
            sequence=10,
            payload=b"\xAA\xBB\xCC\xDD",
        )
        encoded = frame.encode(layout="COMMON_8B")
        self.assertEqual(len(encoded), 8 + 4)
        # Header order in 8B: prio, class, service, dest, src, ver, seq, cmd
        self.assertEqual(encoded[0], 0x05)
        self.assertEqual(encoded[1], 0x07)
        self.assertEqual(encoded[2], 0x00)
        self.assertEqual(encoded[3], 0x03)
        self.assertEqual(encoded[4], 0x02)
        self.assertEqual(encoded[5], 0x11)
        self.assertEqual(encoded[6], 10)
        self.assertEqual(encoded[7], 0x08)
        self.assertEqual(encoded[8:], b"\xAA\xBB\xCC\xDD")

        # Decode back
        decoded = UniversalDeosFrame.decode(encoded, layout="COMMON_8B")
        self.assertEqual(decoded.destination, frame.destination)
        self.assertEqual(decoded.source, frame.source)
        self.assertEqual(decoded.priority, frame.priority)
        self.assertEqual(decoded.command, frame.command)
        self.assertEqual(decoded.payload, frame.payload)

    def test_lora_l2_wrap_and_unwrap(self):
        deos_frame = b"\x10\x02\x02\x11\x01\x01\x01\x05\x02\xAA\xBB"
        wire_packet = wrap_lora_packet(LoraFlag.ACK_REQ, deos_frame)

        # Wire packet structure: AA 55 Flag Length Payload CRC16 (2B LE)
        self.assertTrue(wire_packet.startswith(LORA_MAGIC))
        self.assertEqual(wire_packet[2], LoraFlag.ACK_REQ)
        self.assertEqual(wire_packet[3], len(deos_frame))
        self.assertEqual(wire_packet[4 : 4 + len(deos_frame)], deos_frame)
        self.assertEqual(len(wire_packet), 2 + 1 + 1 + len(deos_frame) + 2)

        # Verify CRC calculation over Flag + Length + Payload
        expected_crc = crc16_ccitt(wire_packet[2:-2])
        wire_crc = int.from_bytes(wire_packet[-2:], "little")
        self.assertEqual(expected_crc, wire_crc)

        # Unwrap stream
        stream_buf = bytearray(b"\xFF\x00\x12" + wire_packet)  # with garbage prefix
        extracted = unwrap_lora_stream(stream_buf)
        self.assertEqual(len(extracted), 1)
        flag, length, payload, rx_crc = extracted[0]
        self.assertEqual(flag, LoraFlag.ACK_REQ)
        self.assertEqual(length, len(deos_frame))
        self.assertEqual(payload, deos_frame)
        self.assertEqual(rx_crc, expected_crc)
        self.assertEqual(len(stream_buf), 0)

    def test_lora_ack_packet(self):
        sample_crc = 0x54A3
        ack_packet = create_lora_ack(sample_crc)

        self.assertEqual(len(ack_packet), 8)
        self.assertTrue(ack_packet.startswith(LORA_MAGIC))
        self.assertEqual(ack_packet[2], LoraFlag.IS_ACK)  # 0x02
        self.assertEqual(ack_packet[3], 0x02)  # Length = 2
        acked_crc = int.from_bytes(ack_packet[4:6], "little")
        self.assertEqual(acked_crc, sample_crc)

        # Unwrap ACK packet
        buf = bytearray(ack_packet)
        extracted = unwrap_lora_stream(buf)
        self.assertEqual(len(extracted), 1)
        flag, length, payload, rx_crc = extracted[0]
        self.assertEqual(flag, LoraFlag.IS_ACK)
        self.assertEqual(length, 2)
        self.assertEqual(int.from_bytes(payload[:2], "little"), sample_crc)


if __name__ == "__main__":
    unittest.main()

