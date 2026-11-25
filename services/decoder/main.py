"""DEOS Decoder Microservice (C-Engine & Packed Structs).

Consumes media-independent Pure Universal DEOS Transport Frame from `lora/rx/frame`
(L2 envelope and CRC16 having been verified and stripped by Linker).
Decodes frame headers via the C `deos_frame_decode` engine (`UniversalDeosFrame.decode`),
unpacks payloads via `deos_types.h` C structs (`payloads.py`), scales engineering values,
assembles list streams (BMS Cell Voltages/Temperatures/Balancing, Fault Lists), and publishes
JSON payloads to service-specific MQTT telemetry topics (including `telemetry/sensors` IMU).
"""

import json
import logging
import os
import time
from collections import defaultdict
from typing import Any, Dict, List

import paho.mqtt.client as mqtt

from deos_core import (
    BmsBalancingPayload,
    BmsCellVoltagePayload,
    BmsCommand,
    BmsStatusPayload,
    BmsTemperaturePayload,
    BrakeCommand,
    BrakeStatusPayload,
    CalibrationCommand,
    ConfigCommand,
    DiagnosticCommand,
    DiagnosticFaultPayload,
    END_OF_FAULT_LIST,
    END_OF_LIST,
    FaultSeverity,
    FaultState,
    HardwareType,
    HeartbeatPayload,
    LightState,
    LightingCommand,
    LightingStatusPayload,
    MessageClass,
    Mode,
    NodeId,
    NodeInfoPayload,
    PingPongPayload,
    ResultCode,
    SensorImuPayload,
    SensorsCommand,
    ServiceId,
    State,
    SteeringCommand,
    SteeringStatusPayload,
    SubscribeRespPayload,
    SystemCommand,
    SystemModePayload,
    SystemStatePayload,
    TractionCommand,
    TractionStatusPayload,
    UniversalDeosFrame,
    get_fault_info,
    get_parameter_info,
    to_physical,
    unpack_parameter_payload,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [decoder] %(message)s",
)
logger = logging.getLogger("decoder")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
FRAME_LAYOUT = os.getenv("DEOS_FRAME_LAYOUT", "UNIVERSAL_9B")

# List streaming accumulators per node:
cell_voltages_acc: Dict[int, Dict[int, float]] = defaultdict(dict)
temperatures_acc: Dict[int, Dict[int, float]] = defaultdict(dict)
balancing_acc: Dict[int, Dict[int, bool]] = defaultdict(dict)
faults_acc: Dict[int, List[Dict[str, Any]]] = defaultdict(list)


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Connected to Mosquitto Broker at %s:%d", MQTT_BROKER, MQTT_PORT)
        client.subscribe("lora/rx/frame")
        logger.info("Subscribed to topic: lora/rx/frame")
    else:
        logger.error("Failed to connect to broker, return code %d", rc)


def decode_system(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == SystemCommand.HEARTBEAT:
        state = HeartbeatPayload.from_bytes(payload).current_state if len(payload) >= 1 else 0xFF
        state_name = State(state).name if state in State._value2member_map_ else "UNKNOWN"
        return {
            "type": "heartbeat",
            "source": frame.source,
            "state": state,
            "state_name": state_name,
            "sequence": frame.sequence,
        }

    elif cmd == SystemCommand.PONG:
        ping_id = PingPongPayload.from_bytes(payload).ping_id if len(payload) >= 4 else 0
        return {
            "type": "pong",
            "source": frame.source,
            "ping_id": ping_id,
            "sequence": frame.sequence,
        }

    elif cmd == SystemCommand.GET_NODE_INFO:
        if len(payload) >= NodeInfoPayload.byte_size():
            ni = NodeInfoPayload.from_bytes(payload)
            hw_type_name = (
                HardwareType(ni.hw_type).name
                if ni.hw_type in HardwareType._value2member_map_
                else "UNKNOWN"
            )
            services_list = [s.name for s in ServiceId if ni.supported_services & (1 << s.value)]

            return {
                "type": "node_info",
                "source": frame.source,
                "result_code": ni.result_code,
                "node_id": ni.node_id,
                "hw_type": ni.hw_type,
                "hw_type_name": hw_type_name,
                "proto_version": f"0x{ni.proto_version:02X}",
                "fw_version": f"{ni.fw_version_major}.{ni.fw_version_minor}.{ni.fw_version_patch}",
                "git_hash": f"{ni.git_hash:08x}",
                "supported_services_mask": f"0x{ni.supported_services:08X}",
                "supported_services": services_list,
                "uptime_s": ni.uptime_s,
            }
        elif len(payload) >= 1:
            return {"type": "node_info_response", "source": frame.source, "result_code": payload[0]}

    elif cmd == SystemCommand.SUBSCRIBE:
        if len(payload) >= SubscribeRespPayload.byte_size():
            sub = SubscribeRespPayload.from_bytes(payload)
            return {
                "type": "subscribe_response",
                "source": frame.source,
                "result_code": sub.result_code,
                "result_name": ResultCode(sub.result_code).name if sub.result_code in ResultCode._value2member_map_ else "UNKNOWN",
                "target_service": sub.target_service,
                "target_command": sub.target_command,
                "actual_interval_ms": sub.actual_interval_ms,
            }
        elif len(payload) >= 1:
            return {"type": "subscribe_response", "source": frame.source, "result_code": payload[0]}

    elif cmd == SystemCommand.UNSUBSCRIBE:
        res = payload[0] if len(payload) >= 1 else 0
        return {
            "type": "unsubscribe_response",
            "source": frame.source,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode._value2member_map_ else "UNKNOWN",
        }

    elif cmd in (SystemCommand.GET_STATE, SystemCommand.SET_STATE):
        state = SystemStatePayload.from_bytes(payload).state if len(payload) >= 1 else 0
        return {
            "type": "state_response",
            "source": frame.source,
            "state": state,
            "state_name": State(state).name if state in State._value2member_map_ else "UNKNOWN",
        }

    elif cmd in (SystemCommand.GET_MODE, SystemCommand.SET_MODE):
        mode = SystemModePayload.from_bytes(payload).mode if len(payload) >= 1 else 0
        return {
            "type": "mode_response",
            "source": frame.source,
            "mode": mode,
            "mode_name": Mode(mode).name if mode in Mode._value2member_map_ else "UNKNOWN",
        }

    return {"type": "system_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_traction(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == TractionCommand.STATUS and len(payload) >= 8:
        padded = payload if len(payload) >= TractionStatusPayload.byte_size() else payload.ljust(TractionStatusPayload.byte_size(), b"\x00")
        s = TractionStatusPayload.from_bytes(padded)
        gear = s.current_gear if len(payload) >= 9 else None
        slip = s.wheel_slip_state if len(payload) >= 10 else None

        return {
            "type": "status",
            "source": frame.source,
            "speed_mps": to_physical(s.current_speed, 0.01, decimals=2),
            "motor_current_a": to_physical(s.motor_current, 0.1, decimals=1),
            "inverter_temp_c": to_physical(s.inverter_temp, 0.1, decimals=1),
            "motor_temp_c": to_physical(s.motor_temp, 0.1, decimals=1),
            "gear": gear,
            "wheel_slip": slip,
        }

    return {"type": "traction_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_steering(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == SteeringCommand.STATUS and len(payload) >= SteeringStatusPayload.byte_size():
        s = SteeringStatusPayload.from_bytes(payload)
        return {
            "type": "status",
            "source": frame.source,
            "angle_deg": to_physical(s.current_angle, 0.01, decimals=2),
            "motor_current_a": to_physical(s.motor_current, 0.1, decimals=1),
            "motor_temp_c": to_physical(s.motor_temp, 0.1, decimals=1),
            "chassis_yaw_rate_deg_s": to_physical(s.chassis_yaw_rate, 0.01, decimals=2),
            "is_tracking": bool(s.is_tracking_target),
        }

    return {"type": "steering_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_brake(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == BrakeCommand.STATUS and len(payload) >= BrakeStatusPayload.byte_size():
        s = BrakeStatusPayload.from_bytes(payload)
        return {
            "type": "status",
            "source": frame.source,
            "position_mm": to_physical(s.current_position, 0.01, decimals=2),
            "actuator_force_n": to_physical(s.actuator_force, 1.0, decimals=1),
            "motor_current_a": to_physical(s.motor_current, 0.1, decimals=1),
            "chassis_long_accel_mps2": to_physical(s.chassis_longitudinal_accel, 0.01, decimals=2),
            "brake_system_active": bool(s.brake_system_active),
            "park_brake_state": s.park_brake_state,
        }

    return {"type": "brake_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_bms(frame: UniversalDeosFrame) -> List[Dict[str, Any]]:
    """Decode BMS frames using packed C structs, handling Status and List-streaming."""
    cmd = frame.command
    payload = frame.payload
    src = frame.source
    events = []

    # 1. BMS STATUS (16 Bytes)
    if cmd == BmsCommand.STATUS and len(payload) >= BmsStatusPayload.byte_size():
        s = BmsStatusPayload.from_bytes(payload)
        events.append({
            "type": "status",
            "source": src,
            "pack_voltage_v": to_physical(s.pack_voltage, 0.01, decimals=2),
            "pack_current_a": to_physical(s.pack_current, 0.1, decimals=1),
            "soc_pct": to_physical(s.state_of_charge, 0.01, decimals=2),
            "bms_temp_c": to_physical(s.bms_temperature, 0.1, decimals=1),
            "min_cell_voltage_v": to_physical(s.minimum_cell_voltage, 0.001, decimals=3),
            "max_cell_voltage_v": to_physical(s.maximum_cell_voltage, 0.001, decimals=3),
            "nominal_pack_voltage_v": to_physical(s.nominal_pack_voltage, 0.01, decimals=2),
            "cell_count": s.cell_count,
            "temp_sensor_count": s.temperature_sensor_count,
        })

    # 2. Cell Voltage (3 Bytes) List Streaming (Index=0 -> END_OF_LIST)
    elif cmd == BmsCommand.CELL_VOLTAGE and len(payload) >= BmsCellVoltagePayload.byte_size():
        cell = BmsCellVoltagePayload.from_bytes(payload)
        if cell.cell_index != END_OF_LIST:
            v_phys = to_physical(cell.cell_voltage, 0.001, decimals=3)
            cell_voltages_acc[src][cell.cell_index] = v_phys
            events.append({
                "type": "cell_voltage_item",
                "source": src,
                "cell_index": cell.cell_index,
                "voltage_v": v_phys,
            })
        else:
            all_cells = [
                {"index": idx, "voltage_v": val}
                for idx, val in sorted(cell_voltages_acc[src].items())
            ]
            events.append({
                "type": "cell_voltages_complete",
                "source": src,
                "total_cells": len(all_cells),
                "cells": all_cells,
            })
            cell_voltages_acc[src].clear()

    # 3. Temperature (3 Bytes) List Streaming (Index=0 -> END_OF_LIST)
    elif cmd == BmsCommand.TEMPERATURE and len(payload) >= BmsTemperaturePayload.byte_size():
        temp = BmsTemperaturePayload.from_bytes(payload)
        if temp.sensor_index != END_OF_LIST:
            t_phys = to_physical(temp.temperature, 0.1, decimals=1)
            temperatures_acc[src][temp.sensor_index] = t_phys
            events.append({
                "type": "temperature_item",
                "source": src,
                "sensor_index": temp.sensor_index,
                "temperature_c": t_phys,
            })
        else:
            all_temps = [
                {"index": idx, "temperature_c": val}
                for idx, val in sorted(temperatures_acc[src].items())
            ]
            events.append({
                "type": "temperatures_complete",
                "source": src,
                "total_sensors": len(all_temps),
                "sensors": all_temps,
            })
            temperatures_acc[src].clear()

    # 4. Balancing (2 Bytes) List Streaming (Index=0 -> END_OF_LIST)
    elif cmd == BmsCommand.BALANCING and len(payload) >= BmsBalancingPayload.byte_size():
        bal = BmsBalancingPayload.from_bytes(payload)
        if bal.cell_index != END_OF_LIST:
            balancing_acc[src][bal.cell_index] = bool(bal.balancing_state)
            events.append({
                "type": "balancing_item",
                "source": src,
                "cell_index": bal.cell_index,
                "balancing": bool(bal.balancing_state),
            })
        else:
            all_balancing = [
                {"index": idx, "balancing": val}
                for idx, val in sorted(balancing_acc[src].items())
            ]
            events.append({
                "type": "balancing_complete",
                "source": src,
                "total_cells": len(all_balancing),
                "cells": all_balancing,
            })
            balancing_acc[src].clear()

    return events


def decode_diagnostic(frame: UniversalDeosFrame) -> List[Dict[str, Any]]:
    """Decode DIAGNOSTIC frames (`GET_FAULTS` list streaming with `0x0000 END_OF_FAULT_LIST`)."""
    cmd = frame.command
    payload = frame.payload
    src = frame.source
    events = []

    if cmd == DiagnosticCommand.GET_FAULTS and len(payload) >= DiagnosticFaultPayload.byte_size():
        flt = DiagnosticFaultPayload.from_bytes(payload)
        if flt.fault_id != END_OF_FAULT_LIST:
            info = get_fault_info(src, flt.fault_id)
            sev_name = FaultSeverity(flt.severity).name if flt.severity in FaultSeverity._value2member_map_ else "UNKNOWN"
            state_name = FaultState(flt.state).name if flt.state in FaultState._value2member_map_ else "UNKNOWN"
            record = {
                "fault_id": flt.fault_id,
                "fault_code": f"0x{flt.fault_id:04X}",
                "name": info.name,
                "description": info.description,
                "severity": flt.severity,
                "severity_name": sev_name,
                "state": flt.state,
                "state_name": state_name,
                "occurrence_count": flt.occurrence_count,
                "last_occurrence_ms": flt.last_occurrence_time,
            }
            faults_acc[src].append(record)
            events.append({
                "type": "fault_item",
                "source": src,
                "fault": record,
            })
        else:
            all_faults = list(faults_acc[src])
            events.append({
                "type": "faults_complete",
                "source": src,
                "total_faults": len(all_faults),
                "faults": all_faults,
            })
            faults_acc[src].clear()

    elif cmd == DiagnosticCommand.CLEAR_FAULTS and len(payload) >= 1:
        res = payload[0]
        events.append({
            "type": "clear_faults_response",
            "source": src,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode._value2member_map_ else "UNKNOWN",
        })

    return events


def decode_sensors(frame: UniversalDeosFrame) -> Dict[str, Any]:
    """Decode SENSORS service (0x07) 9-axis IMU telemetry (`deos_sensor_imu_payload`)."""
    cmd = frame.command
    payload = frame.payload

    if cmd == SensorsCommand.IMU_DATA and len(payload) >= SensorImuPayload.byte_size():
        imu = SensorImuPayload.from_bytes(payload)
        return {
            "type": "imu",
            "source": frame.source,
            "source_name": frame.source_name,
            "sequence": frame.sequence,
            "accel_mps2": {
                "x": to_physical(imu.accel_x, 0.01, decimals=2),
                "y": to_physical(imu.accel_y, 0.01, decimals=2),
                "z": to_physical(imu.accel_z, 0.01, decimals=2),
            },
            "gyro_deg_s": {
                "x": to_physical(imu.gyro_x, 0.01, decimals=2),
                "y": to_physical(imu.gyro_y, 0.01, decimals=2),
                "z": to_physical(imu.gyro_z, 0.01, decimals=2),
            },
            "mag_ut": {
                "x": to_physical(imu.mag_x, 1.0, decimals=1),
                "y": to_physical(imu.mag_y, 1.0, decimals=1),
                "z": to_physical(imu.mag_z, 1.0, decimals=1),
            },
        }

    return {"type": "sensors_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_calibration(frame: UniversalDeosFrame) -> Dict[str, Any]:
    """Decode CALIBRATION service (0x05) status/result responses."""
    cmd = frame.command
    payload = frame.payload
    cmd_name = CalibrationCommand(cmd).name if cmd in CalibrationCommand._value2member_map_ else f"CMD_0x{cmd:02X}"

    if len(payload) >= 1:
        res = payload[0]
        return {
            "type": "calibration_response",
            "source": frame.source,
            "command": cmd,
            "command_name": cmd_name,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode._value2member_map_ else "UNKNOWN",
            "raw": payload.hex(),
        }

    return {"type": "calibration_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_lighting(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == LightingCommand.STATUS and len(payload) >= LightingStatusPayload.byte_size():
        ls = LightingStatusPayload.from_bytes(payload)
        return {
            "type": "status",
            "source": frame.source,
            "headlight": ls.headlight_state,
            "headlight_name": LightState(ls.headlight_state).name if ls.headlight_state in LightState._value2member_map_ else "UNKNOWN",
            "brake_light": ls.brake_light_state,
            "brake_light_name": LightState(ls.brake_light_state).name if ls.brake_light_state in LightState._value2member_map_ else "UNKNOWN",
            "turn_left": ls.turn_left_state,
            "turn_left_name": LightState(ls.turn_left_state).name if ls.turn_left_state in LightState._value2member_map_ else "UNKNOWN",
            "turn_right": ls.turn_right_state,
            "turn_right_name": LightState(ls.turn_right_state).name if ls.turn_right_state in LightState._value2member_map_ else "UNKNOWN",
            "hazard": ls.hazard_state,
            "hazard_name": LightState(ls.hazard_state).name if ls.hazard_state in LightState._value2member_map_ else "UNKNOWN",
            "fault_flags": f"0x{ls.fault_flags:02X}",
        }

    return {"type": "lighting_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_config(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == ConfigCommand.GET_PARAMETER and len(payload) >= 2:
        param_id, _ = unpack_parameter_payload(payload[:2], "uint16")
        param_info = get_parameter_info(frame.service, param_id)
        data_type = param_info.data_type if param_info else "uint16"
        scale = param_info.scale if param_info else 1.0

        val = None
        raw_val = None
        if len(payload) > 2:
            _, raw_val = unpack_parameter_payload(payload, data_type)
            if raw_val is not None:
                val = to_physical(raw_val, scale)

        return {
            "type": "parameter_value",
            "source": frame.source,
            "service": frame.service,
            "param_id": param_id,
            "name": param_info.name if param_info else f"PARAM_{hex(param_id)}",
            "value": val,
            "raw_value": raw_val,
            "unit": param_info.unit if param_info else "",
        }

    elif cmd == ConfigCommand.SET_PARAMETER and len(payload) >= 1:
        res = payload[0]
        return {
            "type": "set_parameter_response",
            "source": frame.source,
            "service": frame.service,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode._value2member_map_ else "UNKNOWN",
        }

    elif cmd == ConfigCommand.SAVE_PARAMETERS and len(payload) >= 1:
        res = payload[0]
        return {
            "type": "save_parameters_response",
            "source": frame.source,
            "service": frame.service,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode._value2member_map_ else "UNKNOWN",
        }

    elif cmd == ConfigCommand.RESTORE_DEFAULTS and len(payload) >= 1:
        res = payload[0]
        return {
            "type": "restore_defaults_response",
            "source": frame.source,
            "service": frame.service,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode._value2member_map_ else "UNKNOWN",
        }

    return {"type": "config_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def on_message(client, userdata, msg):
    try:
        frame = UniversalDeosFrame.decode(msg.payload, layout=FRAME_LAYOUT)
    except Exception as e:
        logger.warning("Failed to decode frame from %s: %s (len=%d)", msg.topic, e, len(msg.payload))
        return

    srv = frame.service
    cmd = frame.command
    src = frame.source

    logger.debug(
        "Received Pure Frame: %s(0x%02X) Class=%s Svc=%s(0x%02X) Cmd=%s(0x%02X) Seq=%d",
        frame.source_name,
        src,
        frame.class_name,
        frame.service_name,
        srv,
        frame.command_name,
        cmd,
        frame.sequence,
    )

    # Generic Parameter Configuration commands (0xE0..0xE3) across services
    if cmd in (
        ConfigCommand.GET_PARAMETER,
        ConfigCommand.SET_PARAMETER,
        ConfigCommand.SAVE_PARAMETERS,
        ConfigCommand.RESTORE_DEFAULTS,
    ):
        res = decode_config(frame)
        client.publish("telemetry/config", json.dumps(res))
        return

    # Dispatch to service topics
    if srv == ServiceId.SYSTEM:
        res = decode_system(frame)
        client.publish("telemetry/system", json.dumps(res))

    elif srv == ServiceId.TRACTION:
        res = decode_traction(frame)
        client.publish("telemetry/traction", json.dumps(res))

    elif srv == ServiceId.STEERING:
        res = decode_steering(frame)
        client.publish("telemetry/steering", json.dumps(res))

    elif srv == ServiceId.BRAKE:
        res = decode_brake(frame)
        client.publish("telemetry/brake", json.dumps(res))

    elif srv == ServiceId.BMS:
        topic = "telemetry/bms/aux" if src == NodeId.BMS_AUX else "telemetry/bms/main"
        events = decode_bms(frame)
        for ev in events:
            client.publish(topic, json.dumps(ev))

    elif srv == ServiceId.CALIBRATION:
        res = decode_calibration(frame)
        client.publish("telemetry/calibration", json.dumps(res))

    elif srv == ServiceId.DIAGNOSTIC:
        events = decode_diagnostic(frame)
        for ev in events:
            client.publish("telemetry/diagnostic", json.dumps(ev))

    elif srv == ServiceId.SENSORS:
        res = decode_sensors(frame)
        client.publish("telemetry/sensors", json.dumps(res))

    elif srv == ServiceId.LIGHTING:
        res = decode_lighting(frame)
        client.publish("telemetry/lighting", json.dumps(res))

    elif frame.message_class == MessageClass.RESPONSE and len(frame.payload) >= 1:
        res_code = frame.payload[0]
        client.publish(
            "telemetry/system",
            json.dumps({
                "type": "generic_response",
                "source": src,
                "service": srv,
                "command": cmd,
                "result_code": res_code,
                "result_name": ResultCode(res_code).name if res_code in ResultCode._value2member_map_ else "UNKNOWN",
            }),
        )


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="deos_decoder")
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            logger.info("Connecting to broker %s:%d...", MQTT_BROKER, MQTT_PORT)
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            logger.warning("Broker not ready (%s), retrying in 2 seconds...", e)
            time.sleep(2)

    client.loop_forever()


if __name__ == "__main__":
    main()
