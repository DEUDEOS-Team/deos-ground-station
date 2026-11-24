import ctypes
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from deos_core import (  # noqa: E402
    BmsBalancingPayload,
    BmsCellVoltagePayload,
    BmsCommand,
    BmsStatusPayload,
    BmsTemperaturePayload,
    BrakeCommand,
    BrakeModePayload,
    BrakeParkPayload,
    BrakePrefillPayload,
    BrakeStatusPayload,
    BrakeTargetPayload,
    CalibrationCommand,
    ConfigCommand,
    DiagnosticCommand,
    DiagnosticFaultPayload,
    HardwareType,
    HeartbeatPayload,
    LightingCommand,
    LightingStatusPayload,
    MessageClass,
    Mode,
    NodeId,
    NodeInfoPayload,
    Priority,
    ResultCode,
    SensorImuPayload,
    SensorsCommand,
    ServiceId,
    State,
    SteeringCommand,
    SteeringModePayload,
    SteeringStatusPayload,
    SteeringTargetPayload,
    SubscribeReqPayload,
    SubscribeRespPayload,
    SystemCommand,
    TractionCommand,
    TractionGearPayload,
    TractionStatusPayload,
    TractionTargetPayload,
    TractionTorqueLimitPayload,
    TransportType,
    UnsubscribeReqPayload,
    pack_parameter_payload,
    unpack_parameter_payload,
)
from deos_core.models import CommandRequest  # noqa: E402


class TestPayloadsAndEnumsParity(unittest.TestCase):
    def test_c_headers_struct_sizes_offsets_and_enums_parity(self):
        c_probe = r"""
#include <stdio.h>
#include <stddef.h>
#include <deos/deos_icd.h>
#include <deos/deos_types.h>

int main(void) {
    printf("SZ:%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu\n",
        sizeof(struct deos_heartbeat_payload),
        sizeof(struct deos_subscribe_req_payload),
        sizeof(struct deos_subscribe_resp_payload),
        sizeof(struct deos_unsubscribe_req_payload),
        sizeof(struct deos_node_info_payload),
        sizeof(struct deos_traction_target_payload),
        sizeof(struct deos_traction_gear_payload),
        sizeof(struct deos_traction_torque_limit_payload),
        sizeof(struct deos_traction_status_payload),
        sizeof(struct deos_steering_target_payload),
        sizeof(struct deos_steering_mode_payload),
        sizeof(struct deos_steering_status_payload),
        sizeof(struct deos_brake_target_payload),
        sizeof(struct deos_brake_mode_payload),
        sizeof(struct deos_brake_park_payload),
        sizeof(struct deos_brake_prefill_payload),
        sizeof(struct deos_brake_status_payload),
        sizeof(struct deos_bms_status_payload),
        sizeof(struct deos_bms_cell_voltage_payload),
        sizeof(struct deos_bms_temperature_payload),
        sizeof(struct deos_bms_balancing_payload),
        sizeof(struct deos_diagnostic_fault_payload));

    printf("SZ2:%zu,%zu\n",
        sizeof(struct deos_sensor_imu_payload),
        sizeof(struct deos_lighting_status_payload));

    printf("OFF_NI:%zu,%zu,%zu,%zu\n",
        offsetof(struct deos_node_info_payload, hw_type),
        offsetof(struct deos_node_info_payload, git_hash),
        offsetof(struct deos_node_info_payload, supported_services),
        offsetof(struct deos_node_info_payload, uptime_s));

    printf("OFF_BMS:%zu,%zu,%zu,%zu,%zu\n",
        offsetof(struct deos_bms_status_payload, pack_current),
        offsetof(struct deos_bms_status_payload, minimum_cell_voltage),
        offsetof(struct deos_bms_status_payload, nominal_pack_voltage),
        offsetof(struct deos_bms_status_payload, cell_count),
        offsetof(struct deos_bms_status_payload, temperature_sensor_count));

    printf("OFF_DIAG:%zu,%zu,%zu,%zu\n",
        offsetof(struct deos_diagnostic_fault_payload, severity),
        offsetof(struct deos_diagnostic_fault_payload, state),
        offsetof(struct deos_diagnostic_fault_payload, occurrence_count),
        offsetof(struct deos_diagnostic_fault_payload, last_occurrence_time));

    printf("OFF_ACT:%zu,%zu,%zu,%zu,%zu,%zu\n",
        offsetof(struct deos_traction_status_payload, inverter_temp),
        offsetof(struct deos_traction_status_payload, wheel_slip_state),
        offsetof(struct deos_steering_status_payload, chassis_yaw_rate),
        offsetof(struct deos_steering_status_payload, is_tracking_target),
        offsetof(struct deos_brake_status_payload, chassis_longitudinal_accel),
        offsetof(struct deos_brake_status_payload, park_brake_state));

    printf("OFF_IMU:%zu,%zu,%zu\n",
        offsetof(struct deos_sensor_imu_payload, gyro_x),
        offsetof(struct deos_sensor_imu_payload, mag_x),
        offsetof(struct deos_sensor_imu_payload, mag_z));

    printf("ENUM_CORE:%d,%d,%d,%d,%d,%d,%d,%d\n",
        DEOS_NODE_GROUND_CONTROL,
        DEOS_NODE_MAIN_STM32,
        DEOS_NODE_GLOBAL_BROADCAST,
        DEOS_PRIO_CRITICAL_CONTROL,
        DEOS_CLASS_COMMAND,
        DEOS_CLASS_REQUEST,
        DEOS_SERVICE_CALIBRATION,
        DEOS_SERVICE_SENSORS);

    printf("ENUM_STATE:%d,%d,%d,%d,%d,%d\n",
        DEOS_STATE_SAFE,
        DEOS_MODE_AUTONOMOUS,
        DEOS_RESULT_INTERNAL_ERROR,
        DEOS_HW_TYPE_STM32H5,
        DEOS_HW_TYPE_ESP32,
        DEOS_TRANSPORT_UART_LORA);

    printf("ENUM_CMD:%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
        DEOS_CMD_SYSTEM_SET_STATE,
        DEOS_CMD_SYSTEM_SUBSCRIBE,
        DEOS_CMD_TRACTION_SET_TARGET_SPEED,
        DEOS_CMD_TRACTION_GET_STATUS,
        DEOS_CMD_TRACTION_SET_GEAR,
        DEOS_CMD_TRACTION_SET_TORQUE_LIMIT,
        DEOS_CMD_STEERING_SET_TARGET_ANGLE,
        DEOS_CMD_STEERING_GET_STATUS,
        DEOS_CMD_STEERING_SET_MODE,
        DEOS_CMD_BRAKE_SET_TARGET,
        DEOS_CMD_BRAKE_GET_STATUS,
        DEOS_CMD_BRAKE_SET_MODE,
        DEOS_CMD_BRAKE_SET_PARK,
        DEOS_CMD_BRAKE_SET_PREFILL,
        DEOS_CMD_BMS_BALANCING,
        DEOS_CMD_CAL_START,
        DEOS_CMD_SENSOR_IMU_DATA);

    printf("ENUM_MISC:%d,%d,%d,%d\n",
        DEOS_CMD_DIAG_GET_FAULTS,
        DEOS_CMD_LIGHTING_STATUS,
        DEOS_CMD_GET_PARAMETER,
        DEOS_CMD_RESTORE_DEFAULTS);
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "parity_probe.c"
            exe = Path(tmpdir) / "parity_probe"
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
            lines = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.strip().splitlines()

        parsed = {}
        for line in lines:
            tag, rest = line.split(":", 1)
            parsed[tag] = [int(x) for x in rest.split(",")]

        expected_sizes = [
            HeartbeatPayload,
            SubscribeReqPayload,
            SubscribeRespPayload,
            UnsubscribeReqPayload,
            NodeInfoPayload,
            TractionTargetPayload,
            TractionGearPayload,
            TractionTorqueLimitPayload,
            TractionStatusPayload,
            SteeringTargetPayload,
            SteeringModePayload,
            SteeringStatusPayload,
            BrakeTargetPayload,
            BrakeModePayload,
            BrakeParkPayload,
            BrakePrefillPayload,
            BrakeStatusPayload,
            BmsStatusPayload,
            BmsCellVoltagePayload,
            BmsTemperaturePayload,
            BmsBalancingPayload,
            DiagnosticFaultPayload,
        ]
        self.assertEqual([cls.byte_size() for cls in expected_sizes], parsed["SZ"])
        self.assertEqual([SensorImuPayload.byte_size(), LightingStatusPayload.byte_size()], parsed["SZ2"])

        self.assertEqual(
            [
                NodeInfoPayload.hw_type.offset,
                NodeInfoPayload.git_hash.offset,
                NodeInfoPayload.supported_services.offset,
                NodeInfoPayload.uptime_s.offset,
            ],
            parsed["OFF_NI"],
        )
        self.assertEqual(
            [
                BmsStatusPayload.pack_current.offset,
                BmsStatusPayload.minimum_cell_voltage.offset,
                BmsStatusPayload.nominal_pack_voltage.offset,
                BmsStatusPayload.cell_count.offset,
                BmsStatusPayload.temperature_sensor_count.offset,
            ],
            parsed["OFF_BMS"],
        )
        self.assertEqual(
            [
                DiagnosticFaultPayload.severity.offset,
                DiagnosticFaultPayload.state.offset,
                DiagnosticFaultPayload.occurrence_count.offset,
                DiagnosticFaultPayload.last_occurrence_time.offset,
            ],
            parsed["OFF_DIAG"],
        )
        self.assertEqual(
            [
                TractionStatusPayload.inverter_temp.offset,
                TractionStatusPayload.wheel_slip_state.offset,
                SteeringStatusPayload.chassis_yaw_rate.offset,
                SteeringStatusPayload.is_tracking_target.offset,
                BrakeStatusPayload.chassis_longitudinal_accel.offset,
                BrakeStatusPayload.park_brake_state.offset,
            ],
            parsed["OFF_ACT"],
        )
        self.assertEqual(
            [
                SensorImuPayload.gyro_x.offset,
                SensorImuPayload.mag_x.offset,
                SensorImuPayload.mag_z.offset,
            ],
            parsed["OFF_IMU"],
        )

        self.assertEqual(
            [
                int(NodeId.GROUND_CONTROL),
                int(NodeId.MAIN_STM32),
                int(NodeId.GLOBAL_BROADCAST),
                int(Priority.CRITICAL_CONTROL),
                int(MessageClass.COMMAND),
                int(MessageClass.REQUEST),
                int(ServiceId.CALIBRATION),
                int(ServiceId.SENSORS),
            ],
            parsed["ENUM_CORE"],
        )
        self.assertEqual(
            [
                int(State.SAFE),
                int(Mode.AUTONOMOUS),
                int(ResultCode.INTERNAL_ERROR),
                int(HardwareType.STM32H5),
                int(HardwareType.ESP32),
                int(TransportType.UART_LORA),
            ],
            parsed["ENUM_STATE"],
        )
        self.assertEqual(
            [
                int(SystemCommand.SET_STATE),
                int(SystemCommand.SUBSCRIBE),
                int(TractionCommand.SET_TARGET_SPEED),
                int(TractionCommand.GET_STATUS),
                int(TractionCommand.SET_GEAR),
                int(TractionCommand.SET_TORQUE_LIMIT),
                int(SteeringCommand.SET_TARGET_ANGLE),
                int(SteeringCommand.GET_STATUS),
                int(SteeringCommand.SET_MODE),
                int(BrakeCommand.SET_TARGET),
                int(BrakeCommand.GET_STATUS),
                int(BrakeCommand.SET_MODE),
                int(BrakeCommand.SET_PARK),
                int(BrakeCommand.SET_PREFILL),
                int(BmsCommand.BALANCING),
                int(CalibrationCommand.START),
                int(SensorsCommand.IMU_DATA),
            ],
            parsed["ENUM_CMD"],
        )
        self.assertEqual(
            [
                int(DiagnosticCommand.GET_FAULTS),
                int(LightingCommand.STATUS),
                int(ConfigCommand.GET_PARAMETER),
                int(ConfigCommand.RESTORE_DEFAULTS),
            ],
            parsed["ENUM_MISC"],
        )

    def test_packed_payload_roundtrip_and_signed_fields(self):
        # Traction 4B with negative target_accel (regen)
        trac = TractionTargetPayload(target_speed=1250, target_accel=-350)
        raw_trac = trac.to_bytes()
        self.assertEqual(len(raw_trac), 4)
        dec_trac = TractionTargetPayload.from_bytes(raw_trac)
        self.assertEqual(dec_trac.target_speed, 1250)
        self.assertEqual(dec_trac.target_accel, -350)

        # Steering 4B with negative target_angle
        steer = SteeringTargetPayload(target_angle=-1850, target_angular_velocity=4500)
        dec_steer = SteeringTargetPayload.from_bytes(steer.to_bytes())
        self.assertEqual(dec_steer.target_angle, -1850)
        self.assertEqual(dec_steer.target_angular_velocity, 4500)

        # Brake 4B with negative target_deceleration
        brk = BrakeTargetPayload(target_brake_demand=8000, target_deceleration=-450)
        dec_brk = BrakeTargetPayload.from_bytes(brk.to_bytes())
        self.assertEqual(dec_brk.target_brake_demand, 8000)
        self.assertEqual(dec_brk.target_deceleration, -450)

        # IMU 18B signed 9 axes
        imu = SensorImuPayload(
            accel_x=-100, accel_y=250, accel_z=981,
            gyro_x=-15, gyro_y=0, gyro_z=1200,
            mag_x=-320, mag_y=450, mag_z=-120,
        )
        raw_imu = imu.to_bytes()
        self.assertEqual(len(raw_imu), 18)
        dec_imu = SensorImuPayload.from_bytes(raw_imu)
        self.assertEqual(dec_imu.accel_x, -100)
        self.assertEqual(dec_imu.accel_z, 981)
        self.assertEqual(dec_imu.gyro_z, 1200)
        self.assertEqual(dec_imu.mag_z, -120)

        # NodeInfo 20B & BmsStatus 16B
        ni = NodeInfoPayload(
            result_code=0, node_id=3, hw_type=HardwareType.STM32H5, proto_version=0x11,
            fw_version_major=1, fw_version_minor=2, fw_version_patch=3, reserved=0,
            git_hash=0xDEADBEEF, supported_services=0x0101, uptime_s=4321,
        )
        dec_ni = NodeInfoPayload.from_bytes(ni.to_bytes())
        self.assertEqual(dec_ni.hw_type, HardwareType.STM32H5)
        self.assertEqual(dec_ni.git_hash, 0xDEADBEEF)
        self.assertEqual(dec_ni.uptime_s, 4321)

        bms = BmsStatusPayload(
            pack_voltage=38450, pack_current=-125, state_of_charge=8500, bms_temperature=315,
            minimum_cell_voltage=3610, maximum_cell_voltage=3650, nominal_pack_voltage=36000,
            cell_count=108, temperature_sensor_count=24,
        )
        dec_bms = BmsStatusPayload.from_bytes(bms.to_bytes())
        self.assertEqual(dec_bms.pack_current, -125)
        self.assertEqual(dec_bms.cell_count, 108)

        # Short buffer must raise ValueError
        with self.assertRaises(ValueError):
            SensorImuPayload.from_bytes(raw_imu[:-1])
        with self.assertRaises(ValueError):
            NodeInfoPayload.from_bytes(b"\x00" * 19)

    def test_parameter_payload_pack_and_unpack(self):
        for dtype, raw_val in [
            ("uint8", 200),
            ("int8", -45),
            ("uint16", 65000),
            ("int16", -1550),
            ("uint32", 3000000000),
            ("int32", -123456789),
        ]:
            packed = pack_parameter_payload(0x0012, dtype, raw_val)
            pid, val = unpack_parameter_payload(packed, dtype)
            self.assertEqual(pid, 0x0012)
            self.assertEqual(val, raw_val)

        # Header-only (GET_PARAMETER request)
        pid_only, val_none = unpack_parameter_payload(b"\x15\x00", "uint16")
        self.assertEqual(pid_only, 0x0015)
        self.assertIsNone(val_none)

    def test_calibration_and_sensors_command_inference(self):
        cal_start = CommandRequest(destination=NodeId.STEERING, service=ServiceId.CALIBRATION, command=CalibrationCommand.START)
        self.assertEqual(cal_start.message_class, MessageClass.COMMAND)

        cal_status = CommandRequest(destination=NodeId.STEERING, service=ServiceId.CALIBRATION, command=CalibrationCommand.GET_STATUS)
        self.assertEqual(cal_status.message_class, MessageClass.REQUEST)

        imu_req = CommandRequest(destination=NodeId.IMU, service=ServiceId.SENSORS, command=SensorsCommand.IMU_DATA)
        self.assertEqual(imu_req.message_class, MessageClass.REQUEST)


if __name__ == "__main__":
    unittest.main()
