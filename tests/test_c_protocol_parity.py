"""End-to-end bidirectional C99 <-> Python parity and header drift tests.

Verifies that:
1. All parameter IDs in `shared/deos_core/registry.py` match `deos_icd.h` identically.
2. Every node ID, service ID, and packed payload struct in `deos-protocol` headers
   is mapped in `shared/deos_core` (catching future submodule drift).
3. Frames produced by a compiled C99 binary (`deos_frame_encode` + C structs) decode
   accurately through `linker`, `UniversalDeosFrame`, and `decoder`.
4. Frames produced by `CommandRequest` + `encoder` decode cleanly inside a compiled C99
   consumer using `deos_frame_decode` and `deos_registry_dispatch`.
"""

import importlib.util
import os
import re
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
    BmsStatusPayload,
    BmsTemperaturePayload,
    BrakeCommand,
    BrakeModePayload,
    BrakeParkPayload,
    BrakePrefillPayload,
    BrakeStatusPayload,
    BrakeTargetPayload,
    ConfigCommand,
    DEOS_INTERVAL_ON_CHANGE,
    DEOS_VERSION,
    DiagnosticFaultPayload,
    GLOBAL_FAULTS,
    GlobalFaultId,
    HeartbeatPayload,
    LightingStatusPayload,
    NodeId,
    NodeInfoPayload,
    PARAMETERS,
    ParameterHeaderPayload,
    SensorImuPayload,
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
    UniversalDeosFrame,
    UnsubscribeReqPayload,
    c_fault_name,
)
from deos_core.c_bridge import DEOS_PROTOCOL_VERSION as C_BRIDGE_PROTOCOL_VERSION  # noqa: E402
from deos_core.models import CommandRequest  # noqa: E402


def _load_service_module(module_name: str, rel_path: str):
    file_path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


encoder_mod = _load_service_module("parity_encoder_svc", "services/encoder/main.py")
decoder_mod = _load_service_module("parity_decoder_svc", "services/decoder/main.py")
linker_mod = _load_service_module("parity_linker_svc", "services/linker/main.py")

SUBMODULE_INC = ROOT / "deos-protocol" / "include"
SUBMODULE_SRC = ROOT / "deos-protocol" / "src"
C_SOURCES = [
    str(SUBMODULE_SRC / "deos_frame.c"),
    str(SUBMODULE_SRC / "deos_codec.c"),
    str(SUBMODULE_SRC / "deos_registry.c"),
]


def _compile_and_run_c(source_code: str, stdin_text: str = "") -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "probe.c"
        exe_path = Path(tmpdir) / "probe"
        src_path.write_text(source_code, encoding="utf-8")
        subprocess.run(
            [
                "gcc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                f"-I{SUBMODULE_INC}",
                str(src_path),
                *C_SOURCES,
                "-o",
                str(exe_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        res = subprocess.run(
            [str(exe_path)],
            input=stdin_text,
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout


class TestCProtocolParity(unittest.TestCase):
    def test_all_parameter_ids_match_deos_icd_h(self):
        c_probe = r"""
#include <stdio.h>
#include <deos/deos_icd.h>

int main(void) {
    int trac[] = {
        DEOS_PARAM_TRACTION_PID_KP, DEOS_PARAM_TRACTION_PID_KI, DEOS_PARAM_TRACTION_PID_KD,
        DEOS_PARAM_TRACTION_MAX_CURRENT, DEOS_PARAM_TRACTION_MAX_SPEED, DEOS_PARAM_TRACTION_ACCEL_LIMIT,
        DEOS_PARAM_TRACTION_CMD_TIMEOUT_MS, DEOS_PARAM_TRACTION_POLE_PAIRS, DEOS_PARAM_TRACTION_GEAR_RATIO,
        DEOS_PARAM_TRACTION_WHEEL_CIRCUM_MM, DEOS_PARAM_TRACTION_REGEN_CUTOFF_SPD
    };
    int steer[] = {
        DEOS_PARAM_STEERING_PID_KP, DEOS_PARAM_STEERING_PID_KI, DEOS_PARAM_STEERING_PID_KD,
        DEOS_PARAM_STEERING_PID_I_MAX, DEOS_PARAM_STEERING_FEEDFORWARD_K, DEOS_PARAM_STEERING_DEADBAND,
        DEOS_PARAM_STEERING_ZERO_OFFSET, DEOS_PARAM_STEERING_MIN_ANGLE, DEOS_PARAM_STEERING_MAX_ANGLE,
        DEOS_PARAM_STEERING_CURRENT_LIMIT, DEOS_PARAM_STEERING_MAX_ANGULAR_VEL, DEOS_PARAM_STEERING_MAX_ANGULAR_ACC,
        DEOS_PARAM_STEERING_SOFT_STOP_MARGIN, DEOS_PARAM_STEERING_MAX_TRACK_ERR, DEOS_PARAM_STEERING_TRACK_TIMEOUT_MS
    };
    int brk[] = {
        DEOS_PARAM_BRAKE_PID_KP, DEOS_PARAM_BRAKE_PID_KI, DEOS_PARAM_BRAKE_PID_KD,
        DEOS_PARAM_BRAKE_MIN_POSITION, DEOS_PARAM_BRAKE_MAX_POSITION, DEOS_PARAM_BRAKE_CURRENT_LIMIT,
        DEOS_PARAM_BRAKE_SLEW_RATE_LIMIT, DEOS_PARAM_BRAKE_CMD_TIMEOUT_MS, DEOS_PARAM_BRAKE_KISS_POINT_OFFSET,
        DEOS_PARAM_BRAKE_MAX_FORCE_LIMIT
    };

    for (size_t i = 0; i < sizeof(trac)/sizeof(trac[0]); i++) printf("%d:%d\n", DEOS_SERVICE_TRACTION, trac[i]);
    for (size_t i = 0; i < sizeof(steer)/sizeof(steer[0]); i++) printf("%d:%d\n", DEOS_SERVICE_STEERING, steer[i]);
    for (size_t i = 0; i < sizeof(brk)/sizeof(brk[0]); i++) printf("%d:%d\n", DEOS_SERVICE_BRAKE, brk[i]);
    return 0;
}
"""
        out = _compile_and_run_c(c_probe)
        c_keys = set()
        for line in out.strip().splitlines():
            srv_s, pid_s = line.split(":")
            c_keys.add((int(srv_s), int(pid_s)))

        self.assertEqual(len(c_keys), 36)
        py_keys = {(int(s), int(p)) for (s, p) in PARAMETERS.keys()}
        self.assertEqual(py_keys, c_keys)

    def test_header_drift_detector_for_nodes_services_and_packed_structs(self):
        icd_text = (SUBMODULE_INC / "deos" / "deos_icd.h").read_text(encoding="utf-8")
        types_text = (SUBMODULE_INC / "deos" / "deos_types.h").read_text(encoding="utf-8")

        node_block = re.search(r"typedef enum\s*\{(.*?)\}\s*deos_node_id_t;", icd_text, re.S)
        self.assertIsNotNone(node_block)
        c_node_vals = {
            int(m.group(2), 0)
            for m in re.finditer(r"(DEOS_NODE_\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", node_block.group(1))
        }
        py_node_vals = {int(n) for n in NodeId}
        self.assertTrue(c_node_vals.issubset(py_node_vals), f"Missing NodeIds: {c_node_vals - py_node_vals}")

        srv_block = re.search(r"typedef enum\s*\{(.*?)\}\s*deos_service_id_t;", icd_text, re.S)
        self.assertIsNotNone(srv_block)
        c_srv_vals = {
            int(m.group(2), 0)
            for m in re.finditer(r"(DEOS_SERVICE_\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", srv_block.group(1))
        }
        py_srv_vals = {int(s) for s in ServiceId}
        self.assertTrue(c_srv_vals.issubset(py_srv_vals), f"Missing ServiceIds: {c_srv_vals - py_srv_vals}")

        c_struct_names = set(re.findall(r"struct\s+(deos_\w+_payload)\s*\{.*?\}\s*__attribute__\(\(packed\)\);", types_text, re.S))
        struct_mapping = {
            "deos_heartbeat_payload": HeartbeatPayload,
            "deos_subscribe_req_payload": SubscribeReqPayload,
            "deos_subscribe_resp_payload": SubscribeRespPayload,
            "deos_unsubscribe_req_payload": UnsubscribeReqPayload,
            "deos_node_info_payload": NodeInfoPayload,
            "deos_traction_target_payload": TractionTargetPayload,
            "deos_traction_gear_payload": TractionGearPayload,
            "deos_traction_torque_limit_payload": TractionTorqueLimitPayload,
            "deos_steering_target_payload": SteeringTargetPayload,
            "deos_steering_mode_payload": SteeringModePayload,
            "deos_brake_target_payload": BrakeTargetPayload,
            "deos_brake_mode_payload": BrakeModePayload,
            "deos_brake_park_payload": BrakeParkPayload,
            "deos_brake_prefill_payload": BrakePrefillPayload,
            "deos_bms_status_payload": BmsStatusPayload,
            "deos_bms_cell_voltage_payload": BmsCellVoltagePayload,
            "deos_bms_temperature_payload": BmsTemperaturePayload,
            "deos_bms_balancing_payload": BmsBalancingPayload,
            "deos_diagnostic_fault_payload": DiagnosticFaultPayload,
            "deos_parameter_payload": ParameterHeaderPayload,
            "deos_traction_status_payload": TractionStatusPayload,
            "deos_steering_status_payload": SteeringStatusPayload,
            "deos_brake_status_payload": BrakeStatusPayload,
            "deos_sensor_imu_payload": SensorImuPayload,
            "deos_lighting_status_payload": LightingStatusPayload,
        }
        self.assertEqual(c_struct_names, set(struct_mapping.keys()))

    def test_version_and_global_fault_ssot_parity(self):
        icd_text = (SUBMODULE_INC / "deos" / "deos_icd.h").read_text(encoding="utf-8")

        ver_match = re.search(r"#define\s+DEOS_PROTOCOL_VERSION\s+(0x[0-9A-Fa-f]+|\d+)", icd_text)
        self.assertIsNotNone(ver_match)
        c_proto_version = int(ver_match.group(1), 0)
        self.assertEqual(DEOS_VERSION, c_proto_version)
        self.assertEqual(C_BRIDGE_PROTOCOL_VERSION, c_proto_version)

        fault_block = re.search(r"typedef enum\s*\{(.*?)\}\s*deos_fault_id_t;", icd_text, re.S)
        self.assertIsNotNone(fault_block)
        c_fault_vals = {
            int(m.group(2), 0)
            for m in re.finditer(r"(DEOS_FAULT_\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", fault_block.group(1))
        }
        self.assertGreater(len(c_fault_vals), 0)

        py_fault_vals = {int(f) for f in GlobalFaultId}
        self.assertTrue(
            c_fault_vals.issubset(py_fault_vals),
            f"Missing GlobalFaultIds: {[hex(x) for x in sorted(c_fault_vals - py_fault_vals)]}",
        )
        self.assertTrue(
            c_fault_vals.issubset(set(GLOBAL_FAULTS.keys())),
            f"Missing GLOBAL_FAULTS entries: {[hex(x) for x in sorted(c_fault_vals - set(GLOBAL_FAULTS.keys()))]}",
        )
        for fid in sorted(c_fault_vals):
            self.assertNotEqual(c_fault_name(fid), "UNKNOWN_FAULT", f"deos_fault_name missing 0x{fid:04X}")

    def test_bidirectional_wire_parity_c_producer_to_python_decoder_and_linker(self):
        c_producer = r"""
#include <stdio.h>
#include <string.h>
#include <deos/deos_frame.h>
#include <deos/deos_types.h>

static void emit_frame(const char *tag, const deos_message_t *m) {
    uint8_t buf[128];
    int len = deos_frame_encode(m, buf, sizeof(buf));
    printf("%s:", tag);
    for (int i = 0; i < len; i++) {
        printf("%02x", buf[i]);
    }
    printf("\n");
}

int main(void) {
    deos_message_t m;

    /* 1. GET_NODE_INFO response */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_MAIN_STM32;
    m.priority = DEOS_PRIO_NETWORK;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_RESPONSE;
    m.service = DEOS_SERVICE_SYSTEM;
    m.command = DEOS_CMD_SYSTEM_GET_NODE_INFO;
    m.sequence = 10;
    struct deos_node_info_payload ni = {
        .result_code = DEOS_RESULT_SUCCESS,
        .node_id = DEOS_NODE_MAIN_STM32,
        .hw_type = DEOS_HW_TYPE_STM32H5,
        .proto_version = DEOS_PROTOCOL_VERSION,
        .fw_version_major = 2,
        .fw_version_minor = 4,
        .fw_version_patch = 1,
        .reserved = 0,
        .git_hash = 0xCAFEBABE,
        .supported_services = (1u << DEOS_SERVICE_SYSTEM) | (1u << DEOS_SERVICE_LIGHTING) | (1u << DEOS_SERVICE_SENSORS),
        .uptime_s = 777
    };
    m.payload_len = sizeof(ni);
    memcpy(m.payload, &ni, sizeof(ni));
    emit_frame("NODE_INFO", &m);

    /* 2. TRACTION status */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_TRACTION;
    m.priority = DEOS_PRIO_STATUS;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_STATUS;
    m.service = DEOS_SERVICE_TRACTION;
    m.command = DEOS_CMD_TRACTION_GET_STATUS;
    m.sequence = 11;
    struct deos_traction_status_payload ts = {
        .current_speed = 1450,
        .motor_current = 235,
        .inverter_temp = 415,
        .motor_temp = -50,
        .current_gear = DEOS_GEAR_DRIVE,
        .wheel_slip_state = 1
    };
    m.payload_len = sizeof(ts);
    memcpy(m.payload, &ts, sizeof(ts));
    emit_frame("TRACTION", &m);

    /* 3. STEERING status */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_STEERING;
    m.priority = DEOS_PRIO_STATUS;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_STATUS;
    m.service = DEOS_SERVICE_STEERING;
    m.command = DEOS_CMD_STEERING_GET_STATUS;
    m.sequence = 12;
    struct deos_steering_status_payload ss = {
        .current_angle = -1825,
        .motor_current = 92,
        .motor_temp = 355,
        .chassis_yaw_rate = -340,
        .is_tracking_target = 1
    };
    m.payload_len = sizeof(ss);
    memcpy(m.payload, &ss, sizeof(ss));
    emit_frame("STEERING", &m);

    /* 4. BRAKE status */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_BRAKE;
    m.priority = DEOS_PRIO_STATUS;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_STATUS;
    m.service = DEOS_SERVICE_BRAKE;
    m.command = DEOS_CMD_BRAKE_GET_STATUS;
    m.sequence = 13;
    struct deos_brake_status_payload bs = {
        .current_position = 1120,
        .actuator_force = 1950,
        .motor_current = 115,
        .chassis_longitudinal_accel = -410,
        .brake_system_active = 1,
        .park_brake_state = 0
    };
    m.payload_len = sizeof(bs);
    memcpy(m.payload, &bs, sizeof(bs));
    emit_frame("BRAKE", &m);

    /* 5. BMS status (with negative discharge current) */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_BMS_MAIN;
    m.priority = DEOS_PRIO_STATUS;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_STATUS;
    m.service = DEOS_SERVICE_BMS;
    m.command = DEOS_CMD_BMS_STATUS;
    m.sequence = 14;
    struct deos_bms_status_payload bms = {
        .pack_voltage = 39600,
        .pack_current = -245,
        .state_of_charge = 7850,
        .bms_temperature = 295,
        .minimum_cell_voltage = 3640,
        .maximum_cell_voltage = 3675,
        .nominal_pack_voltage = 36000,
        .cell_count = 108,
        .temperature_sensor_count = 24
    };
    m.payload_len = sizeof(bms);
    memcpy(m.payload, &bms, sizeof(bms));
    emit_frame("BMS", &m);

    /* 6. SENSORS IMU */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_IMU;
    m.priority = DEOS_PRIO_STATUS;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_STATUS;
    m.service = DEOS_SERVICE_SENSORS;
    m.command = DEOS_CMD_SENSOR_IMU_DATA;
    m.sequence = 15;
    struct deos_sensor_imu_payload imu = {
        .accel_x = -210, .accel_y = 35, .accel_z = 981,
        .gyro_x = 120, .gyro_y = -450, .gyro_z = 890,
        .mag_x = -150, .mag_y = 300, .mag_z = -45
    };
    m.payload_len = sizeof(imu);
    memcpy(m.payload, &imu, sizeof(imu));
    emit_frame("IMU", &m);

    /* 7. LIGHTING status */
    memset(&m, 0, sizeof(m));
    m.destination = DEOS_NODE_GROUND_CONTROL;
    m.source = DEOS_NODE_MAIN_STM32;
    m.priority = DEOS_PRIO_STATUS;
    m.version = DEOS_PROTOCOL_VERSION;
    m.message_class = DEOS_CLASS_STATUS;
    m.service = DEOS_SERVICE_LIGHTING;
    m.command = DEOS_CMD_LIGHTING_STATUS;
    m.sequence = 16;
    struct deos_lighting_status_payload ls = {
        .headlight_state = DEOS_LIGHT_STATE_ON,
        .brake_light_state = DEOS_LIGHT_STATE_OFF,
        .turn_left_state = DEOS_LIGHT_STATE_BLINKING,
        .turn_right_state = DEOS_LIGHT_STATE_OFF,
        .hazard_state = DEOS_LIGHT_STATE_OFF,
        .fault_flags = 0x02
    };
    m.payload_len = sizeof(ls);
    memcpy(m.payload, &ls, sizeof(ls));
    emit_frame("LIGHTING", &m);

    return 0;
}
"""
        out = _compile_and_run_c(c_producer)
        frames = {
            tag: bytes.fromhex(hex_str)
            for tag, hex_str in (line.split(":", 1) for line in out.strip().splitlines())
        }

        ni_info = linker_mod.build_frame_info(frames["NODE_INFO"])
        self.assertEqual(ni_info["src_name"], "MAIN_STM32")
        self.assertEqual(ni_info["command_name"], "GET_NODE_INFO")
        ni_dec = decoder_mod.decode_system(UniversalDeosFrame.decode(frames["NODE_INFO"]))
        self.assertEqual(ni_dec["hw_type_name"], "STM32H5")
        self.assertEqual(ni_dec["fw_version"], "2.4.1")
        self.assertEqual(ni_dec["git_hash"], "cafebabe")
        self.assertEqual(ni_dec["uptime_s"], 777)
        self.assertIn("SENSORS", ni_dec["supported_services"])

        tr_dec = decoder_mod.decode_traction(UniversalDeosFrame.decode(frames["TRACTION"]))
        self.assertEqual(tr_dec["speed_mps"], 14.5)
        self.assertEqual(tr_dec["motor_current_a"], 23.5)
        self.assertEqual(tr_dec["motor_temp_c"], -5.0)
        self.assertEqual(tr_dec["gear"], 1)
        self.assertEqual(tr_dec["wheel_slip"], 1)

        st_dec = decoder_mod.decode_steering(UniversalDeosFrame.decode(frames["STEERING"]))
        self.assertEqual(st_dec["angle_deg"], -18.25)
        self.assertEqual(st_dec["chassis_yaw_rate_deg_s"], -3.4)
        self.assertTrue(st_dec["is_tracking"])

        br_dec = decoder_mod.decode_brake(UniversalDeosFrame.decode(frames["BRAKE"]))
        self.assertEqual(br_dec["position_mm"], 11.2)
        self.assertEqual(br_dec["actuator_force_n"], 1950.0)
        self.assertEqual(br_dec["chassis_long_accel_mps2"], -4.1)

        bms_evs = decoder_mod.decode_bms(UniversalDeosFrame.decode(frames["BMS"]))
        self.assertEqual(len(bms_evs), 1)
        self.assertEqual(bms_evs[0]["pack_voltage_v"], 396.0)
        self.assertEqual(bms_evs[0]["pack_current_a"], -24.5)
        self.assertEqual(bms_evs[0]["soc_pct"], 78.5)

        imu_info = linker_mod.build_frame_info(frames["IMU"])
        self.assertEqual(imu_info["src_name"], "IMU")
        self.assertEqual(imu_info["service_name"], "SENSORS")
        imu_dec = decoder_mod.decode_sensors(UniversalDeosFrame.decode(frames["IMU"]))
        self.assertEqual(imu_dec["accel_mps2"], {"x": -2.1, "y": 0.35, "z": 9.81})
        self.assertEqual(imu_dec["gyro_deg_s"], {"x": 1.2, "y": -4.5, "z": 8.9})
        self.assertEqual(imu_dec["mag_ut"], {"x": -150.0, "y": 300.0, "z": -45.0})

        lg_dec = decoder_mod.decode_lighting(UniversalDeosFrame.decode(frames["LIGHTING"]))
        self.assertEqual(lg_dec["headlight_name"], "ON")
        self.assertEqual(lg_dec["turn_left_name"], "BLINKING")
        self.assertEqual(lg_dec["fault_flags"], "0x02")

    def test_bidirectional_wire_parity_python_encoder_to_c_consumer_and_registry(self):
        requests = [
            CommandRequest(
                destination=NodeId.MAIN_STM32,
                service=ServiceId.SYSTEM,
                command=SystemCommand.SET_STATE,
                params={"target_state": int(State.SAFE)},
            ),
            CommandRequest(
                destination=NodeId.BMS_MAIN,
                service=ServiceId.SYSTEM,
                command=SystemCommand.SUBSCRIBE,
                params={
                    "target_service": int(ServiceId.BMS),
                    "target_command": 0x02,
                    "interval_ms": DEOS_INTERVAL_ON_CHANGE,
                    "lease_ttl_s": 120,
                },
            ),
            CommandRequest(
                destination=NodeId.TRACTION,
                service=ServiceId.TRACTION,
                command=TractionCommand.SET_TARGET_SPEED,
                params={"target_speed": 12.34, "target_accel": -3.45},
            ),
            CommandRequest(
                destination=NodeId.STEERING,
                service=ServiceId.STEERING,
                command=SteeringCommand.SET_TARGET_ANGLE,
                params={"target_angle": -22.5, "target_angular_velocity": 60.0},
            ),
            CommandRequest(
                destination=NodeId.BRAKE,
                service=ServiceId.BRAKE,
                command=BrakeCommand.SET_TARGET,
                params={"target_brake_demand": 85.5, "target_deceleration": -4.2},
            ),
            CommandRequest(
                destination=NodeId.STEERING,
                service=ServiceId.STEERING,
                command=ConfigCommand.SET_PARAMETER,
                params={"param_id": 0x0010, "value": -5.25},
            ),
        ]

        encoded_hex_lines = []
        for idx, req in enumerate(requests, start=1):
            payload = encoder_mod.pack_payload(req.service, req.command, req.params)
            wire = UniversalDeosFrame(
                destination=req.destination,
                source=NodeId.GROUND_CONTROL,
                priority=req.priority,
                message_class=req.message_class,
                service=req.service,
                command=req.command,
                sequence=idx,
                payload=payload,
            ).encode(layout="UNIVERSAL_9B")
            encoded_hex_lines.append(wire.hex())

        c_consumer = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <deos/deos_frame.h>
#include <deos/deos_codec.h>
#include <deos/deos_registry.h>

static int verified = 0;

static int on_set_state(const deos_message_t *m, void *ud) {
    (void)ud;
    if (m->destination == DEOS_NODE_MAIN_STM32 && m->source == DEOS_NODE_GROUND_CONTROL &&
        m->priority == DEOS_PRIO_CRITICAL_CONTROL && m->payload_len == 1 && m->payload[0] == DEOS_STATE_SAFE) {
        verified++;
    }
    return 0;
}

static int on_subscribe(const deos_message_t *m, void *ud) {
    (void)ud;
    if (m->payload_len == sizeof(struct deos_subscribe_req_payload)) {
        const struct deos_subscribe_req_payload *p = (const struct deos_subscribe_req_payload *)m->payload;
        if (p->target_service == DEOS_SERVICE_BMS && p->target_command == DEOS_CMD_BMS_STATUS &&
            p->interval_ms == DEOS_INTERVAL_ON_CHANGE && p->lease_ttl_s == 120) {
            verified++;
        }
    }
    return 0;
}

static int on_traction_speed(const deos_message_t *m, void *ud) {
    (void)ud;
    if (m->payload_len == sizeof(struct deos_traction_target_payload)) {
        const struct deos_traction_target_payload *p = (const struct deos_traction_target_payload *)m->payload;
        if (p->target_speed == 1234 && p->target_accel == -345) {
            verified++;
        }
    }
    return 0;
}

static int on_steering_angle(const deos_message_t *m, void *ud) {
    (void)ud;
    if (m->payload_len == sizeof(struct deos_steering_target_payload)) {
        const struct deos_steering_target_payload *p = (const struct deos_steering_target_payload *)m->payload;
        if (p->target_angle == -2250 && p->target_angular_velocity == 6000) {
            verified++;
        }
    }
    return 0;
}

static int on_brake_target(const deos_message_t *m, void *ud) {
    (void)ud;
    if (m->payload_len == sizeof(struct deos_brake_target_payload)) {
        const struct deos_brake_target_payload *p = (const struct deos_brake_target_payload *)m->payload;
        if (p->target_brake_demand == 8550 && p->target_deceleration == -420) {
            verified++;
        }
    }
    return 0;
}

static int on_steering_set_param(const deos_message_t *m, void *ud) {
    (void)ud;
    if (m->payload_len == 4) {
        uint16_t pid = deos_get_u16_le(&m->payload[0]);
        int16_t val = deos_get_i16_le(&m->payload[2]);
        if (pid == DEOS_PARAM_STEERING_ZERO_OFFSET && val == -525) {
            verified++;
        }
    }
    return 0;
}

static int hex_to_bytes(const char *hex, uint8_t *out, size_t max_len) {
    size_t hlen = strlen(hex);
    while (hlen > 0 && (hex[hlen - 1] == '\n' || hex[hlen - 1] == '\r')) {
        hlen--;
    }
    if (hlen % 2 != 0 || hlen / 2 > max_len) return -1;
    for (size_t i = 0; i < hlen / 2; i++) {
        unsigned int byte_val = 0;
        if (sscanf(&hex[i * 2], "%2x", &byte_val) != 1) return -1;
        out[i] = (uint8_t)byte_val;
    }
    return (int)(hlen / 2);
}

int main(void) {
    deos_registry_t reg;
    deos_registry_init(&reg);

    deos_registry_register_for_node(&reg, DEOS_NODE_MAIN_STM32, DEOS_CLASS_COMMAND, DEOS_SERVICE_SYSTEM, DEOS_CMD_SYSTEM_SET_STATE, on_set_state, NULL);
    deos_registry_register_for_node(&reg, DEOS_NODE_BMS_MAIN, DEOS_CLASS_REQUEST, DEOS_SERVICE_SYSTEM, DEOS_CMD_SYSTEM_SUBSCRIBE, on_subscribe, NULL);
    deos_registry_register_for_node(&reg, DEOS_NODE_TRACTION, DEOS_CLASS_COMMAND, DEOS_SERVICE_TRACTION, DEOS_CMD_TRACTION_SET_TARGET_SPEED, on_traction_speed, NULL);
    deos_registry_register_for_node(&reg, DEOS_NODE_STEERING, DEOS_CLASS_COMMAND, DEOS_SERVICE_STEERING, DEOS_CMD_STEERING_SET_TARGET_ANGLE, on_steering_angle, NULL);
    deos_registry_register_for_node(&reg, DEOS_NODE_BRAKE, DEOS_CLASS_COMMAND, DEOS_SERVICE_BRAKE, DEOS_CMD_BRAKE_SET_TARGET, on_brake_target, NULL);
    deos_registry_register_for_node(&reg, DEOS_NODE_STEERING, DEOS_CLASS_CONFIG, DEOS_SERVICE_STEERING, DEOS_CMD_SET_PARAMETER, on_steering_set_param, NULL);

    char line[256];
    while (fgets(line, sizeof(line), stdin) != NULL) {
        uint8_t buf[128];
        int len = hex_to_bytes(line, buf, sizeof(buf));
        if (len <= 0) {
            fprintf(stderr, "Bad hex line\n");
            return 2;
        }
        deos_message_t msg;
        if (deos_frame_decode(buf, (size_t)len, &msg) != 0) {
            fprintf(stderr, "deos_frame_decode failed\n");
            return 3;
        }
        if (deos_registry_dispatch(&reg, &msg) != 1) {
            fprintf(stderr, "dispatch miss: node=0x%02x cls=%d srv=%d cmd=0x%02x\n",
                    msg.destination, msg.message_class, msg.service, msg.command);
            return 4;
        }
    }

    if (verified != 6) {
        fprintf(stderr, "verified=%d != 6\n", verified);
        return 5;
    }
    printf("ALL_C_ASSERTIONS_PASSED\n");
    return 0;
}
"""
        out = _compile_and_run_c(c_consumer, stdin_text="\n".join(encoded_hex_lines) + "\n")
        self.assertEqual(out.strip(), "ALL_C_ASSERTIONS_PASSED")


if __name__ == "__main__":
    unittest.main()
