import ctypes
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from deos_core import (  # noqa: E402
    CDecodedFrame,
    DeosCallbackRegistry,
    MessageClass,
    NodeId,
    Priority,
    ServiceId,
    SystemCommand,
    UniversalDeosFrame,
    c_class_name,
    c_command_name,
    c_decode_frame,
    c_encode_frame,
    c_fault_name,
    c_fault_severity_name,
    c_node_name,
    c_service_name,
    c_transport_name,
    get_i16_le,
    get_i32_le,
    get_u16_le,
    get_u32_le,
    put_i16_le,
    put_i32_le,
    put_u16_le,
    put_u32_le,
)
from deos_core.c_bridge import (  # noqa: E402
    CDeosMessage,
    CDeosRegistry,
    CDeosRegistryEntry,
    DEOS_MAX_PAYLOAD_LEN,
)


class TestCBridge(unittest.TestCase):
    def test_ctypes_abi_sizes_and_offsets_match_c_compiler(self):
        c_probe = r"""
#include <stdio.h>
#include <stddef.h>
#include <deos/deos_types.h>
#include <deos/deos_registry.h>

int main(void) {
    printf("%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu\n",
        sizeof(deos_message_t),
        offsetof(deos_message_t, version),
        offsetof(deos_message_t, payload),
        offsetof(deos_message_t, payload_len),
        sizeof(deos_registry_entry_t),
        offsetof(deos_registry_entry_t, handler),
        sizeof(deos_registry_t),
        offsetof(deos_registry_t, count));
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "abi_probe.c"
            exe = Path(tmpdir) / "abi_probe"
            src.write_text(c_probe, encoding="utf-8")
            subprocess.run(
                [
                    "gcc",
                    "-std=c99",
                    f"-I{ROOT / 'deos-protocol' / 'include'}",
                    str(src),
                    "-o",
                    str(exe),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.strip()

        vals = [int(v) for v in out.split(",")]
        c_msg_sz, c_ver_off, c_pay_off, c_plen_off, c_ent_sz, c_hnd_off, c_reg_sz, c_cnt_off = vals

        self.assertEqual(ctypes.sizeof(CDeosMessage), c_msg_sz)
        self.assertEqual(CDeosMessage.version.offset, c_ver_off)
        self.assertEqual(CDeosMessage.payload.offset, c_pay_off)
        self.assertEqual(CDeosMessage.payload_len.offset, c_plen_off)
        self.assertEqual(ctypes.sizeof(CDeosRegistryEntry), c_ent_sz)
        self.assertEqual(CDeosRegistryEntry.handler.offset, c_hnd_off)
        self.assertEqual(ctypes.sizeof(CDeosRegistry), c_reg_sz)
        self.assertEqual(CDeosRegistry.count.offset, c_cnt_off)

    def test_frame_encode_decode_parity_with_universal_9b(self):
        samples = [
            (NodeId.MAIN_STM32, NodeId.GROUND_CONTROL, Priority.STATUS, MessageClass.REQUEST, ServiceId.SYSTEM, SystemCommand.GET_STATE, 1, b""),
            (NodeId.MAIN_STM32, NodeId.GROUND_CONTROL, Priority.CRITICAL_CONTROL, MessageClass.COMMAND, ServiceId.SYSTEM, SystemCommand.SET_STATE, 7, b"\x05"),
            (NodeId.GROUND_CONTROL, NodeId.MAIN_STM32, Priority.NETWORK, MessageClass.RESPONSE, ServiceId.SYSTEM, SystemCommand.GET_NODE_INFO, 42, bytes(range(20))),
            (NodeId.TRACTION, NodeId.MAIN_STM32, Priority.CONTROL, MessageClass.STATUS, ServiceId.TRACTION, 0x02, 255, bytes([i & 0xFF for i in range(DEOS_MAX_PAYLOAD_LEN)])),
            (NodeId.BRAKE, NodeId.GROUND_CONTROL, Priority.CONTROL, MessageClass.COMMAND, ServiceId.BRAKE, 0x01, 13, b"\x00\xff\x00\xaa\x55\x00"),
        ]

        for dest, src, prio, mcls, srv, cmd, seq, payload in samples:
            c_raw = c_encode_frame(dest, src, prio, mcls, srv, cmd, seq, payload)
            py_raw = UniversalDeosFrame(
                destination=dest,
                source=src,
                priority=prio,
                message_class=mcls,
                service=srv,
                command=cmd,
                sequence=seq,
                payload=payload,
            ).encode(layout="UNIVERSAL_9B")
            self.assertEqual(c_raw, py_raw)

            decoded = c_decode_frame(c_raw)
            self.assertIsInstance(decoded, CDecodedFrame)
            self.assertEqual(decoded.destination, int(dest))
            self.assertEqual(decoded.source, int(src))
            self.assertEqual(decoded.priority, int(prio))
            self.assertEqual(decoded.version, 0x12)
            self.assertEqual(decoded.message_class, int(mcls))
            self.assertEqual(decoded.service, int(srv))
            self.assertEqual(decoded.command, int(cmd))
            self.assertEqual(decoded.sequence, seq)
            self.assertEqual(decoded.payload, payload)

    def test_frame_negative_validation(self):
        with self.assertRaises(ValueError):
            c_encode_frame(0x03, 0x02, 1, 1, 0, 2, 0, b"x" * (DEOS_MAX_PAYLOAD_LEN + 1))

        # Empty, short header, truncated payload, old v1.1 version, oversized payload len, and trailing bytes
        bad_frames = (
            b"",
            b"\x03\x02\x01\x12\x01\x00\x02\x00",
            b"\x03\x02\x01\x12\x01\x00\x02\x00\x05\x01\x02",
            b"\x03\x02\x01\x11\x01\x00\x02\x00\x01\x05",  # v1.1 rejected by v1.2 decoder
            b"\x03\x02\x01\x12\x01\x00\x02\x00\x01\x05\xAA",  # trailing byte rejected
        )
        for bad_buf in bad_frames:
            with self.assertRaises(ValueError):
                c_decode_frame(bad_buf)

    def test_c_symbolic_string_lookups(self):
        self.assertEqual(c_node_name(0x03), "MAIN_STM32")
        self.assertEqual(c_node_name(0x02), "GROUND_CONTROL")
        self.assertEqual(c_node_name(0x99), "UNKNOWN_NODE")

        self.assertEqual(c_class_name(0x01), "COMMAND")
        self.assertEqual(c_class_name(0x04), "REQUEST")
        self.assertEqual(c_class_name(0xEE), "UNKNOWN_CLS")

        self.assertEqual(c_service_name(0x00), "SYSTEM")
        self.assertEqual(c_service_name(0x08), "LIGHTING")
        self.assertEqual(c_service_name(0xEE), "UNKNOWN_SVC")

        self.assertEqual(c_command_name(0x00, 0x02), "SET_STATE")
        self.assertEqual(c_command_name(0x01, 0x01), "SET_TARGET_SPEED")
        self.assertEqual(c_command_name(0x07, 0x01), "IMU_DATA")
        self.assertEqual(c_command_name(0x02, 0xE1), "SET_PARAMETER")
        self.assertEqual(c_command_name(0x01, 0xE0), "GET_PARAMETER")
        self.assertEqual(c_command_name(0x00, 0xEE), "UNKNOWN_CMD")

        self.assertEqual(c_transport_name(4), "UART_LORA")
        self.assertEqual(c_transport_name(0xEE), "UNKNOWN_TRP")

        self.assertEqual(c_fault_name(0x0045), "CAN_TX_SEND_FAILED")
        self.assertEqual(c_fault_name(0x0400), "BMS_PACK_OVERVOLTAGE")
        self.assertEqual(c_fault_name(0x0500), "GW_MAIN_COMM_LOST")
        self.assertEqual(c_fault_name(0xFFFF), "UNKNOWN_FAULT")

        self.assertEqual(c_fault_severity_name(1), "INFO")
        self.assertEqual(c_fault_severity_name(2), "WARNING")
        self.assertEqual(c_fault_severity_name(3), "ERROR")
        self.assertEqual(c_fault_severity_name(4), "CRITICAL")
        self.assertEqual(c_fault_severity_name(0xEE), "UNKNOWN_SEV")

    def test_little_endian_c_codec_helpers(self):
        for val in (0, 1, 0x1234, 65535):
            enc = put_u16_le(val)
            self.assertEqual(len(enc), 2)
            self.assertEqual(get_u16_le(enc), val)

        for val in (-32768, -1, 0, 1234, 32767):
            enc = put_i16_le(val)
            self.assertEqual(len(enc), 2)
            self.assertEqual(get_i16_le(enc), val)

        for val in (0, 1, 0x12345678, 0xFFFFFFFF):
            enc = put_u32_le(val)
            self.assertEqual(len(enc), 4)
            self.assertEqual(get_u32_le(enc), val)

        for val in (-2147483648, -1, 0, 987654, 2147483647):
            enc = put_i32_le(val)
            self.assertEqual(len(enc), 4)
            self.assertEqual(get_i32_le(enc), val)

        # Offset reading and bounds checks
        packed = put_u16_le(500) + put_i16_le(-250)
        self.assertEqual(get_i16_le(packed, offset=2), -250)

        with self.assertRaises(ValueError):
            get_u16_le(b"\x01")
        with self.assertRaises(ValueError):
            get_u32_le(b"\x01\x02\x03")
        with self.assertRaises(ValueError):
            put_u16_le(70000)
        with self.assertRaises(ValueError):
            put_i16_le(-40000)
        with self.assertRaises(ValueError):
            put_u32_le(-1)
        with self.assertRaises(ValueError):
            put_i32_le(2147483648)

    def test_c_callback_registry_dispatch_and_unregister(self):
        reg = DeosCallbackRegistry()
        received = []

        with self.assertRaises(ValueError):
            reg.register(
                MessageClass.COMMAND,
                ServiceId.SYSTEM,
                SystemCommand.SET_STATE,
                lambda frame: received.append((frame.destination, frame.payload)),
                local_node=NodeId.INVALID,
            )

        reg.register(
            MessageClass.COMMAND,
            ServiceId.SYSTEM,
            SystemCommand.SET_STATE,
            lambda frame: received.append((frame.destination, frame.payload)),
            local_node=NodeId.MAIN_STM32,
        )

        unicast = c_encode_frame(
            NodeId.MAIN_STM32,
            NodeId.GROUND_CONTROL,
            Priority.CRITICAL_CONTROL,
            MessageClass.COMMAND,
            ServiceId.SYSTEM,
            SystemCommand.SET_STATE,
            1,
            b"\x05",
        )
        broadcast = c_encode_frame(
            NodeId.GLOBAL_BROADCAST,
            NodeId.GROUND_CONTROL,
            Priority.EMERGENCY,
            MessageClass.COMMAND,
            ServiceId.SYSTEM,
            SystemCommand.SET_STATE,
            2,
            b"\x05",
        )
        other_cmd = c_encode_frame(
            NodeId.MAIN_STM32,
            NodeId.GROUND_CONTROL,
            Priority.STATUS,
            MessageClass.REQUEST,
            ServiceId.SYSTEM,
            SystemCommand.GET_STATE,
            3,
            b"",
        )

        self.assertEqual(reg.dispatch(unicast), 1)
        self.assertEqual(reg.dispatch(broadcast), 1)
        self.assertEqual(reg.dispatch(other_cmd), 0)
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0], (int(NodeId.MAIN_STM32), b"\x05"))
        self.assertEqual(received[1], (int(NodeId.GLOBAL_BROADCAST), b"\x05"))

        reg.unregister(
            MessageClass.COMMAND,
            ServiceId.SYSTEM,
            SystemCommand.SET_STATE,
            local_node=NodeId.MAIN_STM32,
        )
        self.assertEqual(reg.dispatch(unicast), 0)


if __name__ == "__main__":
    unittest.main()
