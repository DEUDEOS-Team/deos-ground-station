"""DEOS CRC16-CCITT Implementation.

Polynom: 0x1021
Seed / Initial Value: 0xFFFF
Transmission on wire: Little-Endian (LSB first, then MSB)
Matches C implementation in DOC-ICD-TRP-LORA-007.
"""

from typing import Union


def crc16_ccitt(data: Union[bytes, bytearray, memoryview], seed: int = 0xFFFF) -> int:
    """Compute 16-bit CRC-CCITT (polynomial 0x1021, seed 0xFFFF).

    Args:
        data: Buffer of bytes to calculate CRC over.
        seed: Initial CRC register value (default 0xFFFF).

    Returns:
        16-bit integer CRC value (0x0000 - 0xFFFF).
    """
    crc = seed & 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc16_ccitt_bytes(data: Union[bytes, bytearray, memoryview], seed: int = 0xFFFF) -> bytes:
    """Compute CRC16-CCITT and return 2 bytes encoded in Little-Endian."""
    crc = crc16_ccitt(data, seed)
    return crc.to_bytes(2, byteorder="little")

