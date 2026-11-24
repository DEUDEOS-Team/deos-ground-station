"""DEOS Framing Layer.

Provides:
1. Level 1: Media-Independent Universal DEOS Transport Frame (UniversalDeosFrame)
   - UNIVERSAL_9B: DOC-ICD-CORE-001 Section 9.1 (9-byte header + N-byte payload)
   - COMMON_8B:    DOC-ICD-TRP-LORA-007 / ETH-006 (8-byte header + N-byte payload)
2. Level 2: LoRa Transport Envelope (L2 Framing - Managed exclusively by Linker)
   - [0xAA 0x55] [Flag] [Length] [Payload / Saf DEOS Frame] [CRC16-CCITT (2B LE)]
"""

import logging
import os
import struct
from dataclasses import dataclass, field
from typing import List, Tuple, Union

from .c_bridge import (
    DEOS_MAX_PAYLOAD_LEN,
    c_class_name,
    c_command_name,
    c_decode_frame,
    c_encode_frame,
    c_node_name,
    c_service_name,
)
from .crc import crc16_ccitt
from .enums import DEOS_VERSION, LORA_MAGIC, LoraFlag

logger = logging.getLogger("deos.framing")


DEFAULT_FRAME_LAYOUT = os.getenv("DEOS_FRAME_LAYOUT", "UNIVERSAL_9B")


@dataclass
class UniversalDeosFrame:
    """Pure, media-independent Universal DEOS Transport Frame."""
    destination: int
    source: int
    priority: int
    version: int = DEOS_VERSION
    message_class: int = 0
    service: int = 0
    command: int = 0
    sequence: int = 0
    payload: bytes = field(default_factory=bytes)

    @property
    def destination_name(self) -> str:
        """Symbolic node name resolved via C `deos_node_name`."""
        return c_node_name(self.destination)

    @property
    def source_name(self) -> str:
        """Symbolic source node name resolved via C `deos_node_name`."""
        return c_node_name(self.source)

    @property
    def service_name(self) -> str:
        """Symbolic service name resolved via C `deos_service_name`."""
        return c_service_name(self.service)

    @property
    def class_name(self) -> str:
        """Symbolic message class name resolved via C `deos_class_name`."""
        return c_class_name(self.message_class)

    @property
    def command_name(self) -> str:
        """Symbolic command name resolved via C `deos_command_name`."""
        return c_command_name(self.service, self.command)

    def encode(self, layout: str = DEFAULT_FRAME_LAYOUT) -> bytes:
        """Encode the DEOS frame into pure media-independent binary bytes.

        Does NOT add 0xAA 0x55, Flag, Length, or CRC16.
        `UNIVERSAL_9B` executes directly through the C `deos_frame_encode` engine.
        """
        if layout == "UNIVERSAL_9B":
            return c_encode_frame(
                destination=self.destination,
                source=self.source,
                priority=self.priority,
                message_class=self.message_class,
                service=self.service,
                command=self.command,
                sequence=self.sequence,
                payload=self.payload,
                version=self.version,
            )

        elif layout == "COMMON_8B":
            # DOC-ICD-TRP-LORA-007:
            # 0: priority
            # 1: message_class
            # 2: service
            # 3: destination
            # 4: source
            # 5: version
            # 6: sequence
            # 7: command
            header = struct.pack(
                "<8B",
                self.priority & 0xFF,
                self.message_class & 0xFF,
                self.service & 0xFF,
                self.destination & 0xFF,
                self.source & 0xFF,
                self.version & 0xFF,
                self.sequence & 0xFF,
                self.command & 0xFF,
            )
            return header + self.payload

        else:
            raise ValueError(f"Unknown frame layout: {layout}")

    @classmethod
    def decode(cls, data: bytes, layout: str = DEFAULT_FRAME_LAYOUT) -> "UniversalDeosFrame":
        """Decode a pure media-independent binary frame into UniversalDeosFrame."""
        if layout == "UNIVERSAL_9B":
            decoded = c_decode_frame(data)
            return cls(
                destination=decoded.destination,
                source=decoded.source,
                priority=decoded.priority,
                version=decoded.version,
                message_class=decoded.message_class,
                service=decoded.service,
                command=decoded.command,
                sequence=decoded.sequence,
                payload=decoded.payload,
            )

        elif layout == "COMMON_8B":
            if len(data) < 8:
                raise ValueError(f"Frame data too short for COMMON_8B: {len(data)} < 8 bytes")
            (
                prio,
                msg_class,
                service,
                dest,
                src,
                ver,
                seq,
                cmd,
            ) = struct.unpack("<8B", data[:8])

            payload = data[8:]
            return cls(
                destination=dest,
                source=src,
                priority=prio,
                version=ver,
                message_class=msg_class,
                service=service,
                command=cmd,
                sequence=seq,
                payload=payload,
            )

        else:
            raise ValueError(f"Unknown frame layout: {layout}")


# ============================================================================
# Level 2: LoRa Physical L2 Wire Framing (Managed exclusively by Linker)
# ============================================================================

def wrap_lora_packet(flag: int, deos_frame: bytes) -> bytes:
    """Wrap a pure DEOS frame into a full LoRa L2 Wire Packet.

    Format:
    [0xAA 0x55] [Flag: 1B] [Length: 1B] [DEOS Frame: L Bytes] [CRC16: 2B LE]
    MAGIC bytes are NOT included in CRC16 calculation.
    """
    length = len(deos_frame)
    envelope_body = bytes([flag & 0xFF, length & 0xFF]) + deos_frame
    crc = crc16_ccitt(envelope_body)
    return LORA_MAGIC + envelope_body + crc.to_bytes(2, byteorder="little")


def create_lora_ack(acked_crc: int) -> bytes:
    """Create a LoRa ACK packet (Flag=0x02, Length=0x02).

    Format:
    [0xAA 0x55] [Flag: 0x02] [Length: 0x02] [Acked_CRC: 2B LE] [New_CRC16: 2B LE]
    """
    ack_payload = acked_crc.to_bytes(2, byteorder="little")
    ack_body = bytes([int(LoraFlag.IS_ACK), 0x02]) + ack_payload
    ack_crc = crc16_ccitt(ack_body)
    return LORA_MAGIC + ack_body + ack_crc.to_bytes(2, byteorder="little")


def unwrap_lora_stream(
    buffer: bytearray,
) -> List[Tuple[int, int, bytes, int]]:
    """Scan and unwrap valid LoRa frames from an incoming stream buffer.

    Mutates `buffer` in-place by removing consumed bytes.
    Returns a list of extracted tuples: `(flag, length, payload_bytes, rx_crc)`.
    """
    extracted = []

    while len(buffer) >= 6:
        # Search for synchronization magic 0xAA 0x55
        idx = buffer.find(LORA_MAGIC)
        if idx == -1:
            # If the last byte is 0xAA, keep it in case 0x55 arrives next
            if buffer.endswith(b"\xaa"):
                del buffer[:-1]
            else:
                buffer.clear()
            break

        if idx > 0:
            del buffer[:idx]

        # Ensure we have at least MAGIC (2B) + Flag (1B) + Length (1B)
        if len(buffer) < 4:
            break

        flag = buffer[2]
        length = buffer[3]
        total_len = 4 + length + 2  # AA 55 (2) + Flag (1) + Len (1) + Payload (L) + CRC (2)

        if len(buffer) < total_len:
            # Whole packet not received yet, wait for more bytes
            break

        raw_packet = bytes(buffer[:total_len])
        del buffer[:total_len]

        # Verify CRC16 (over Flag + Length + Payload)
        envelope_data = raw_packet[2:-2]
        calc_crc = crc16_ccitt(envelope_data)
        rx_crc = int.from_bytes(raw_packet[-2:], byteorder="little")

        if calc_crc != rx_crc:
            logger.warning(
                "Corrupted LoRa frame dropped! Flag=0x%02X Length=%d CalcCRC=0x%04X != RxCRC=0x%04X (Raw: %s)",
                flag, length, calc_crc, rx_crc, raw_packet.hex()
            )
            continue

        payload_bytes = raw_packet[4:-2]
        extracted.append((flag, length, payload_bytes, rx_crc))

    return extracted

