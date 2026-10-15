"""Unit tests for Linker L2 transport wrapping, deframing, and ARQ mechanism."""

import unittest
import sys
import os
import time
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared")))

from deos_core import (
    LoraFlag,
    wrap_lora_packet,
    create_lora_ack,
    unwrap_lora_stream,
    crc16_ccitt,
)

def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

linker_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/linker/main.py"))
linker_mod = load_module_from_path("linker_service", linker_path)


class TestLinkerArq(unittest.TestCase):
    def setUp(self):
        self.linker = linker_mod.LinkerService()
        self.linker.is_mock = True
        self.sent_serial_bytes = []
        self.linker.write_to_serial = lambda data: self.sent_serial_bytes.append(data)
        self.published_mqtt = []
        self.linker.mqtt_client.publish = lambda topic, payload: self.published_mqtt.append((topic, payload))

    def test_tx_reliable_creates_arq_entry(self):
        sample_frame = b"\x03\x02\x05\x11\x07\x00\x08\x01\x04\x12\x34\x56\x78"

        class DummyMsg:
            topic = "lora/tx/reliable"
            payload = sample_frame

        self.linker.on_mqtt_message(None, None, DummyMsg())

        # Check serial transmission
        self.assertEqual(len(self.sent_serial_bytes), 1)
        wire = self.sent_serial_bytes[0]
        self.assertEqual(wire[:2], b"\xaa\x55")
        self.assertEqual(wire[2], LoraFlag.ACK_REQ)
        self.assertEqual(wire[3], len(sample_frame))

        crc = int.from_bytes(wire[-2:], "little")
        # ARQ should now be pending for this CRC
        self.assertIn(crc, self.linker.pending_arq)

        # Receive matching ACK from vehicle: Flag=0x02, Length=2, Payload=CRC_LE
        ack_wire = create_lora_ack(crc)
        ack_packets = unwrap_lora_stream(bytearray(ack_wire))
        self.assertEqual(len(ack_packets), 1)
        flag, length, payload_bytes, rx_crc = ack_packets[0]

        self.linker.handle_incoming_packet(flag, length, payload_bytes, rx_crc)

        # Pending ARQ should now be removed
        self.assertNotIn(crc, self.linker.pending_arq)
        # Should have published status "ACKED"
        statuses = [p[1] for p in self.published_mqtt if p[0] == "command/status"]
        self.assertTrue(any("ACKED" in s for s in statuses))

    def test_vehicle_flag_01_triggers_automatic_ack(self):
        # A critical packet from the vehicle (Flag=0x01)
        vehicle_pure_frame = b"\x02\x03\x01\x11\x00\x00\x05\x01\x01\x01"
        vehicle_wire_packet = wrap_lora_packet(LoraFlag.ACK_REQ, vehicle_pure_frame)
        vehicle_crc = int.from_bytes(vehicle_wire_packet[-2:], "little")

        packets = unwrap_lora_stream(bytearray(vehicle_wire_packet))
        self.assertEqual(len(packets), 1)
        flag, length, payload_bytes, rx_crc = packets[0]

        # Linker processes vehicle packet
        self.linker.handle_incoming_packet(flag, length, payload_bytes, rx_crc)

        # 1. Automatic ACK must have been written to serial immediately!
        self.assertEqual(len(self.sent_serial_bytes), 1)
        ack_sent = self.sent_serial_bytes[0]
        self.assertEqual(ack_sent[:2], b"\xaa\x55")
        self.assertEqual(ack_sent[2], LoraFlag.IS_ACK)  # Flag=0x02
        self.assertEqual(ack_sent[3], 0x02)  # Length=2
        acked_crc = int.from_bytes(ack_sent[4:6], "little")
        self.assertEqual(acked_crc, vehicle_crc)

        # 2. Pure DEOS frame (peeled) must have been published to lora/rx/frame
        rx_published = [p[1] for p in self.published_mqtt if p[0] == "lora/rx/frame"]
        self.assertEqual(len(rx_published), 1)
        self.assertEqual(rx_published[0], vehicle_pure_frame)


if __name__ == "__main__":
    unittest.main()

