"""Symmetrical Encoder and Decoder tests.

Tests pure media-independent Universal DEOS frame interaction between Encoder and Decoder.
Verifies:
- Absence of 29-bit CAN IDs or CAN frames
- Pydantic v2 validation rules (Unicast restrictions, BMS routing, Lighting routing)
- Scaling and payload packing/unpacking symmetry across all services
- List streaming assembly (BMS 100 ms index=0x00, Diagnostic fault 0x0000)
- Subscription engine (SUBSCRIBE 6B, RESPONSE 5B, 0xFFFF On-Change)
"""

import unittest
import sys
import os
import struct
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared")))

from pydantic import ValidationError

from deos_core import (
    NodeId,
    ServiceId,
    SystemCommand,
    TractionCommand,
    SteeringCommand,
    BrakeCommand,
    BmsCommand,
    DiagnosticCommand,
    LightingCommand,
    ConfigCommand,
    UniversalDeosFrame,
    DEOS_INTERVAL_ON_CHANGE,
    END_OF_FAULT_LIST,
    END_OF_LIST,
)
from deos_core.models import CommandRequest

# Load encoder and decoder modules independently to avoid sys.modules collision
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

encoder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/encoder/main.py"))
decoder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/decoder/main.py"))

encoder_mod = load_module_from_path("encoder_service", encoder_path)
decoder_mod = load_module_from_path("decoder_service", decoder_path)


class TestEncoderDecoderSymmetry(unittest.TestCase):
    def test_icd_unicast_validation_rules(self):
        # 1. PING to broadcast must fail validation
        with self.assertRaises(ValidationError):
            CommandRequest(destination=NodeId.GLOBAL_BROADCAST, service=ServiceId.SYSTEM, command=SystemCommand.PING)

        with self.assertRaises(ValidationError):
            CommandRequest(destination=NodeId.CAN_BROADCAST, service=ServiceId.SYSTEM, command=SystemCommand.PING)

        # 2. GET_NODE_INFO to broadcast must fail
        with self.assertRaises(ValidationError):
            CommandRequest(destination=NodeId.GLOBAL_BROADCAST, service=ServiceId.SYSTEM, command=SystemCommand.GET_NODE_INFO)

        # 3. SUBSCRIBE to broadcast must fail
        with self.assertRaises(ValidationError):
            CommandRequest(destination=NodeId.GLOBAL_BROADCAST, service=ServiceId.SYSTEM, command=SystemCommand.SUBSCRIBE)

        # 4. BMS service cannot target BMS_GATEWAY (0x30)
        with self.assertRaises(ValidationError):
            CommandRequest(destination=NodeId.BMS_GATEWAY, service=ServiceId.BMS, command=BmsCommand.GET_STATUS)

        # 5. Lighting service must target MAIN_STM32 (0x03)
        with self.assertRaises(ValidationError):
            CommandRequest(destination=NodeId.TRACTION, service=ServiceId.LIGHTING, command=LightingCommand.TURN_ON)

        # Valid cases pass cleanly
        req_ping = CommandRequest(destination=NodeId.MAIN_STM32, service=ServiceId.SYSTEM, command=SystemCommand.PING)
        self.assertEqual(req_ping.destination, 0x03)

        req_bms = CommandRequest(destination=NodeId.BMS_MAIN, service=ServiceId.BMS, command=BmsCommand.GET_STATUS)
        self.assertEqual(req_bms.destination, 0x20)

        req_light = CommandRequest(destination=NodeId.MAIN_STM32, service=ServiceId.LIGHTING, command=LightingCommand.TURN_ON)
        self.assertEqual(req_light.destination, 0x03)

    def test_system_subscription_symmetry(self):
        # Pack SUBSCRIBE request (6 Bytes: <BBHH)
        params = {
            "target_service": ServiceId.BMS,
            "target_command": BmsCommand.STATUS,
            "interval_ms": DEOS_INTERVAL_ON_CHANGE,  # 0xFFFF
            "lease_ttl_s": 60,
        }
        packed_payload = encoder_mod.pack_payload(ServiceId.SYSTEM, SystemCommand.SUBSCRIBE, params)
        self.assertEqual(len(packed_payload), 6)
        srv, cmd, interval, ttl = struct.unpack("<BBHH", packed_payload)
        self.assertEqual(srv, ServiceId.BMS)
        self.assertEqual(cmd, BmsCommand.STATUS)
        self.assertEqual(interval, 0xFFFF)
        self.assertEqual(ttl, 60)

        # Simulate SUBSCRIBE response from vehicle (5 Bytes: <BBBH)
        resp_payload = struct.pack("<BBBH", 0x00, ServiceId.BMS, BmsCommand.STATUS, 0xFFFF)
        resp_frame = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.BMS_MAIN,
            priority=0x05,
            message_class=0x05,
            service=ServiceId.SYSTEM,
            command=SystemCommand.SUBSCRIBE,
            sequence=1,
            payload=resp_payload,
        )
        decoded = decoder_mod.decode_system(resp_frame)
        self.assertEqual(decoded["type"], "subscribe_response")
        self.assertEqual(decoded["result_code"], 0)
        self.assertEqual(decoded["result_name"], "SUCCESS")
        self.assertEqual(decoded["target_service"], ServiceId.BMS)
        self.assertEqual(decoded["actual_interval_ms"], 0xFFFF)

    def test_system_node_info_response(self):
        # 20 Bytes standard response (<BBBBBBBBIII)
        resp_payload = struct.pack(
            "<BBBBBBBBIII",
            0x00,       # result_code SUCCESS
            0x03,       # node_id MAIN_STM32
            0x01,       # hw_type STM32H5
            0x11,       # proto_version v1.1
            1, 2, 0,    # fw 1.2.0
            0,          # reserved
            0xABCD1234,# git_hash
            0x00000101,# supported_services bitmask (SYSTEM + LIGHTING)
            12345,      # uptime_s
        )
        frame = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.MAIN_STM32,
            priority=0x05,
            message_class=0x05,
            service=ServiceId.SYSTEM,
            command=SystemCommand.GET_NODE_INFO,
            sequence=2,
            payload=resp_payload,
        )
        decoded = decoder_mod.decode_system(frame)
        self.assertEqual(decoded["type"], "node_info")
        self.assertEqual(decoded["node_id"], 0x03)
        self.assertEqual(decoded["fw_version"], "1.2.0")
        self.assertEqual(decoded["uptime_s"], 12345)
        self.assertIn("SYSTEM", decoded["supported_services"])
        self.assertIn("LIGHTING", decoded["supported_services"])

    def test_traction_speed_symmetry(self):
        # Encoder: SET_SPEED 8.5 m/s with 1.2 m/s² accel
        params = {"target_speed": 8.5, "target_accel": 1.2}
        payload = encoder_mod.pack_payload(ServiceId.TRACTION, TractionCommand.SET_SPEED, params)
        self.assertEqual(len(payload), 4)
        spd_raw, acc_raw = struct.unpack("<HH", payload)
        self.assertEqual(spd_raw, 850)
        self.assertEqual(acc_raw, 120)

        # Decoder: STATUS (10 bytes: speed, current, inverter_temp, motor_temp, gear, slip)
        status_payload = struct.pack("<HHhhBB", 850, 150, 420, 550, 1, 0)
        frame = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.TRACTION,
            priority=0x03,
            message_class=0x02,
            service=ServiceId.TRACTION,
            command=TractionCommand.STATUS,
            sequence=3,
            payload=status_payload,
        )
        decoded = decoder_mod.decode_traction(frame)
        self.assertEqual(decoded["speed_mps"], 8.5)
        self.assertEqual(decoded["motor_current_a"], 15.0)
        self.assertEqual(decoded["inverter_temp_c"], 42.0)
        self.assertEqual(decoded["motor_temp_c"], 55.0)
        self.assertEqual(decoded["gear"], 1)

    def test_bms_list_streaming_assembly(self):
        # Reset accumulator for BMS Main (0x20)
        decoder_mod.cell_voltages_acc[NodeId.BMS_MAIN].clear()

        # Cell 1: 3.651 V (3651 raw)
        c1 = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.BMS_MAIN,
            priority=0x03,
            message_class=0x05,
            service=ServiceId.BMS,
            command=BmsCommand.CELL_VOLTAGE,
            sequence=10,
            payload=struct.pack("<BH", 1, 3651),
        )
        ev1 = decoder_mod.decode_bms(c1)
        self.assertEqual(len(ev1), 1)
        self.assertEqual(ev1[0]["type"], "cell_voltage_item")
        self.assertEqual(ev1[0]["cell_index"], 1)
        self.assertEqual(ev1[0]["voltage_v"], 3.651)

        # Cell 2: 3.648 V (3648 raw)
        c2 = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.BMS_MAIN,
            priority=0x03,
            message_class=0x05,
            service=ServiceId.BMS,
            command=BmsCommand.CELL_VOLTAGE,
            sequence=11,
            payload=struct.pack("<BH", 2, 3648),
        )
        ev2 = decoder_mod.decode_bms(c2)
        self.assertEqual(ev2[0]["cell_index"], 2)
        self.assertEqual(ev2[0]["voltage_v"], 3.648)

        # End of List marker: Cell Index = 0x00
        c_end = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.BMS_MAIN,
            priority=0x03,
            message_class=0x05,
            service=ServiceId.BMS,
            command=BmsCommand.CELL_VOLTAGE,
            sequence=12,
            payload=struct.pack("<BH", END_OF_LIST, 0),
        )
        ev_end = decoder_mod.decode_bms(c_end)
        self.assertEqual(len(ev_end), 1)
        self.assertEqual(ev_end[0]["type"], "cell_voltages_complete")
        self.assertEqual(ev_end[0]["total_cells"], 2)
        self.assertEqual(ev_end[0]["cells"][0]["voltage_v"], 3.651)
        self.assertEqual(ev_end[0]["cells"][1]["voltage_v"], 3.648)

    def test_diagnostic_fault_streaming_assembly(self):
        # Reset accumulator for Steering (0x11)
        decoder_mod.faults_acc[NodeId.STEERING].clear()

        # Fault 1: 0x0100 (STEER_ENCODER_COMM_LOST)
        f1_payload = struct.pack("<HBBHI", 0x0100, 4, 1, 3, 5000)
        f1 = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.STEERING,
            priority=0x03,
            message_class=0x05,
            service=ServiceId.DIAGNOSTIC,
            command=DiagnosticCommand.GET_FAULTS,
            sequence=20,
            payload=f1_payload,
        )
        ev1 = decoder_mod.decode_diagnostic(f1)
        self.assertEqual(len(ev1), 1)
        self.assertEqual(ev1[0]["type"], "fault_item")
        self.assertEqual(ev1[0]["fault"]["fault_id"], 0x0100)
        self.assertEqual(ev1[0]["fault"]["name"], "STEER_ENCODER_COMM_LOST")

        # End of fault list: 0x0000 (END_OF_FAULT_LIST)
        f_end_payload = struct.pack("<HBBHI", END_OF_FAULT_LIST, 0, 0, 0, 0)
        f_end = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.STEERING,
            priority=0x03,
            message_class=0x05,
            service=ServiceId.DIAGNOSTIC,
            command=DiagnosticCommand.GET_FAULTS,
            sequence=21,
            payload=f_end_payload,
        )
        ev_end = decoder_mod.decode_diagnostic(f_end)
        self.assertEqual(len(ev_end), 1)
        self.assertEqual(ev_end[0]["type"], "faults_complete")
        self.assertEqual(ev_end[0]["total_faults"], 1)
        self.assertEqual(ev_end[0]["faults"][0]["fault_id"], 0x0100)

    def test_steering_and_brake_symmetry(self):
        # Steering command
        str_payload = encoder_mod.pack_payload(ServiceId.STEERING, SteeringCommand.SET_TARGET_ANGLE, {"target_angle": -15.5, "target_angular_velocity": 45.0})
        self.assertEqual(len(str_payload), 4)
        ang_raw, vel_raw = struct.unpack("<hH", str_payload)
        self.assertEqual(ang_raw, -1550)
        self.assertEqual(vel_raw, 4500)

        # Steering status (9 bytes: <hHhhB)
        str_status = struct.pack("<hHhhB", -1550, 85, 380, 120, 1)
        f_str = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.STEERING,
            priority=0x03,
            message_class=0x02,
            service=ServiceId.STEERING,
            command=SteeringCommand.STATUS,
            sequence=30,
            payload=str_status,
        )
        d_str = decoder_mod.decode_steering(f_str)
        self.assertEqual(d_str["angle_deg"], -15.5)
        self.assertEqual(d_str["motor_current_a"], 8.5)
        self.assertEqual(d_str["motor_temp_c"], 38.0)
        self.assertEqual(d_str["chassis_yaw_rate_deg_s"], 1.2)
        self.assertTrue(d_str["is_tracking"])

        # Brake command: demand 75%
        brk_payload = encoder_mod.pack_payload(ServiceId.BRAKE, BrakeCommand.SET_DEMAND, {"target_brake_demand": 75.0})
        self.assertEqual(len(brk_payload), 2)
        self.assertEqual(struct.unpack("<H", brk_payload)[0], 7500)

        # Brake status (10 bytes: <HHHhBB)
        brk_status = struct.pack("<HHHhBB", 1250, 1800, 120, -250, 1, 1)
        f_brk = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.BRAKE,
            priority=0x03,
            message_class=0x02,
            service=ServiceId.BRAKE,
            command=BrakeCommand.STATUS,
            sequence=31,
            payload=brk_status,
        )
        d_brk = decoder_mod.decode_brake(f_brk)
        self.assertEqual(d_brk["position_mm"], 12.5)
        self.assertEqual(d_brk["actuator_force_n"], 1800.0)
        self.assertEqual(d_brk["motor_current_a"], 12.0)
        self.assertEqual(d_brk["chassis_long_accel_mps2"], -2.5)
        self.assertTrue(d_brk["brake_system_active"])
        self.assertEqual(d_brk["park_brake_state"], 1)

    def test_lighting_and_config_symmetry(self):
        # Lighting turn on headlight
        l_on = encoder_mod.pack_payload(ServiceId.LIGHTING, LightingCommand.TURN_ON, {"light_id": 1})
        self.assertEqual(l_on, b"\x01")

        # Lighting status (6 bytes: <BBBBBB)
        l_status = struct.pack("<BBBBBB", 1, 0, 2, 0, 0, 0)
        f_l = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.MAIN_STM32,
            priority=0x03,
            message_class=0x02,
            service=ServiceId.LIGHTING,
            command=LightingCommand.STATUS,
            sequence=40,
            payload=l_status,
        )
        d_l = decoder_mod.decode_lighting(f_l)
        self.assertEqual(d_l["headlight"], 1)
        self.assertEqual(d_l["headlight_name"], "ON")
        self.assertEqual(d_l["turn_left_name"], "BLINKING")

        # Config: SET_PARAMETER PID_KP (0x0001) for Steering (scale 0.01)
        cfg_set = encoder_mod.pack_payload(ServiceId.STEERING, ConfigCommand.SET_PARAMETER, {"param_id": 0x0001, "value": 2.5})
        self.assertEqual(len(cfg_set), 4)
        pid, raw_val = struct.unpack("<HH", cfg_set)
        self.assertEqual(pid, 0x0001)
        self.assertEqual(raw_val, 250)

        # Config: GET_PARAMETER response
        cfg_resp = UniversalDeosFrame(
            destination=NodeId.GROUND_CONTROL,
            source=NodeId.STEERING,
            priority=0x04,
            message_class=0x05,
            service=ServiceId.STEERING,
            command=ConfigCommand.GET_PARAMETER,
            sequence=41,
            payload=struct.pack("<HH", 0x0001, 250),
        )
        d_cfg = decoder_mod.decode_config(cfg_resp)
        self.assertEqual(d_cfg["param_id"], 0x0001)
        self.assertEqual(d_cfg["name"], "PID_KP")
        self.assertEqual(d_cfg["value"], 2.5)


if __name__ == "__main__":
    unittest.main()

