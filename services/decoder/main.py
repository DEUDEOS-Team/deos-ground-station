"""DEOS Decoder Microservice (Stateless & List-Streaming Assembler).

Consumes media-independent Pure Universal DEOS Transport Frame from `lora/rx/frame`
(L2 envelope and CRC16 having been verified and stripped by Linker).
Parses DEOS header, unpacks and scales engineering telemetry values,
assembles 100 ms list streams (BMS Cell Voltages/Temperatures/Balancing, Fault Lists),
and publishes JSON payloads to service-specific MQTT telemetry topics.
"""

import json
import logging
import os
import struct
import time
from collections import defaultdict
from typing import Any, Dict, List

import paho.mqtt.client as mqtt

from deos_core import (
    BmsCommand,
    BrakeCommand,
    ConfigCommand,
    DiagnosticCommand,
    END_OF_FAULT_LIST,
    END_OF_LIST,
    FaultSeverity,
    FaultState,
    LightState,
    LightingCommand,
    MessageClass,
    NodeId,
    ResultCode,
    ServiceId,
    State,
    SteeringCommand,
    SystemCommand,
    TractionCommand,
    UniversalDeosFrame,
    get_fault_info,
    get_parameter_info,
    to_physical,
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
# node_id -> { "cells": {idx: volt}, "temps": {idx: temp}, "balancing": {idx: state}, "faults": [list] }
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
        state = payload[0] if len(payload) >= 1 else 0xFF
        state_name = State(state).name if state in State else "UNKNOWN"
        return {
            "type": "heartbeat",
            "source": frame.source,
            "state": state,
            "state_name": state_name,
            "sequence": frame.sequence,
        }

    elif cmd == SystemCommand.PONG:
        ping_id = struct.unpack("<I", payload[:4])[0] if len(payload) >= 4 else 0
        return {
            "type": "pong",
            "source": frame.source,
            "ping_id": ping_id,
            "sequence": frame.sequence,
        }

    elif cmd == SystemCommand.GET_NODE_INFO:
        if len(payload) >= 20:
            (
                res,
                nid,
                hw,
                proto,
                maj,
                minr,
                pat,
                resv,
                git_hash,
                supp_srv,
                uptime,
            ) = struct.unpack("<BBBBBBBBIII", payload[:20])

            services_list = []
            for s in ServiceId:
                if supp_srv & (1 << s.value):
                    services_list.append(s.name)

            return {
                "type": "node_info",
                "source": frame.source,
                "result_code": res,
                "node_id": nid,
                "hw_type": hw,
                "proto_version": f"0x{proto:02X}",
                "fw_version": f"{maj}.{minr}.{pat}",
                "git_hash": f"{git_hash:08x}",
                "supported_services_mask": f"0x{supp_srv:08X}",
                "supported_services": services_list,
                "uptime_s": uptime,
            }
        elif len(payload) >= 1:
            return {"type": "node_info_response", "source": frame.source, "result_code": payload[0]}

    elif cmd == SystemCommand.SUBSCRIBE:
        if len(payload) >= 5:
            res, srv, c, interval = struct.unpack("<BBBH", payload[:5])
            return {
                "type": "subscribe_response",
                "source": frame.source,
                "result_code": res,
                "result_name": ResultCode(res).name if res in ResultCode else "UNKNOWN",
                "target_service": srv,
                "target_command": c,
                "actual_interval_ms": interval,
            }
        elif len(payload) >= 1:
            return {"type": "subscribe_response", "source": frame.source, "result_code": payload[0]}

    elif cmd == SystemCommand.UNSUBSCRIBE:
        res = payload[0] if len(payload) >= 1 else 0
        return {
            "type": "unsubscribe_response",
            "source": frame.source,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode else "UNKNOWN",
        }

    elif cmd in (SystemCommand.GET_STATE, SystemCommand.SET_STATE):
        state = payload[0] if len(payload) >= 1 else 0
        return {
            "type": "state_response",
            "source": frame.source,
            "state": state,
            "state_name": State(state).name if state in State else "UNKNOWN",
        }

    elif cmd in (SystemCommand.GET_MODE, SystemCommand.SET_MODE):
        mode = payload[0] if len(payload) >= 1 else 0
        return {
            "type": "mode_response",
            "source": frame.source,
            "mode": mode,
            "mode_name": Mode(mode).name if mode in Mode else "UNKNOWN",
        }

    return {"type": "system_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_traction(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == TractionCommand.STATUS and len(payload) >= 8:
        spd_raw, cur_raw, inv_temp_raw, mot_temp_raw = struct.unpack("<HHhh", payload[:8])
        gear = payload[8] if len(payload) >= 9 else None
        slip = payload[9] if len(payload) >= 10 else None

        return {
            "type": "status",
            "source": frame.source,
            "speed_mps": to_physical(spd_raw, 0.01, decimals=2),
            "motor_current_a": to_physical(cur_raw, 0.1, decimals=1),
            "inverter_temp_c": to_physical(inv_temp_raw, 0.1, decimals=1),
            "motor_temp_c": to_physical(mot_temp_raw, 0.1, decimals=1),
            "gear": gear,
            "wheel_slip": slip,
        }

    return {"type": "traction_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_steering(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == SteeringCommand.STATUS and len(payload) >= 9:
        ang_raw, cur_raw, mot_temp_raw, yaw_raw, tracking = struct.unpack("<hHhhB", payload[:9])
        return {
            "type": "status",
            "source": frame.source,
            "angle_deg": to_physical(ang_raw, 0.01, decimals=2),
            "motor_current_a": to_physical(cur_raw, 0.1, decimals=1),
            "motor_temp_c": to_physical(mot_temp_raw, 0.1, decimals=1),
            "chassis_yaw_rate_deg_s": to_physical(yaw_raw, 0.01, decimals=2),
            "is_tracking": bool(tracking),
        }

    return {"type": "steering_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_brake(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == BrakeCommand.STATUS and len(payload) >= 10:
        pos_raw, force_raw, cur_raw, accel_raw, active, park = struct.unpack("<HHHhBB", payload[:10])
        return {
            "type": "status",
            "source": frame.source,
            "position_mm": to_physical(pos_raw, 0.01, decimals=2),
            "actuator_force_n": to_physical(force_raw, 1.0, decimals=1),
            "motor_current_a": to_physical(cur_raw, 0.1, decimals=1),
            "chassis_long_accel_mps2": to_physical(accel_raw, 0.01, decimals=2),
            "brake_system_active": bool(active),
            "park_brake_state": park,
        }

    return {"type": "brake_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_bms(frame: UniversalDeosFrame) -> List[Dict[str, Any]]:
    """Decode BMS frames, handling Status and List-streaming (Cells, Temps, Balancing)."""
    cmd = frame.command
    payload = frame.payload
    src = frame.source
    events = []

    # 1. BMS STATUS (16 Bytes)
    if cmd == BmsCommand.STATUS and len(payload) >= 16:
        (
            v_raw,
            i_raw,
            soc_raw,
            temp_raw,
            min_v_raw,
            max_v_raw,
            nom_v_raw,
            cell_cnt,
            temp_cnt,
        ) = struct.unpack("<HhHhHHHBB", payload[:16])

        events.append({
            "type": "status",
            "source": src,
            "pack_voltage_v": to_physical(v_raw, 0.01, decimals=2),
            "pack_current_a": to_physical(i_raw, 0.1, decimals=1),
            "soc_pct": to_physical(soc_raw, 0.01, decimals=2),
            "bms_temp_c": to_physical(temp_raw, 0.1, decimals=1),
            "min_cell_voltage_v": to_physical(min_v_raw, 0.001, decimals=3),
            "max_cell_voltage_v": to_physical(max_v_raw, 0.001, decimals=3),
            "nominal_pack_voltage_v": to_physical(nom_v_raw, 0.01, decimals=2),
            "cell_count": cell_cnt,
            "temp_sensor_count": temp_cnt,
        })

    # 2. Cell Voltage (3 Bytes: <BH) List Streaming (Index=0 -> END_OF_LIST)
    elif cmd == BmsCommand.CELL_VOLTAGE and len(payload) >= 3:
        cell_idx, v_raw = struct.unpack("<BH", payload[:3])
        if cell_idx != END_OF_LIST:
            v_phys = to_physical(v_raw, 0.001, decimals=3)
            cell_voltages_acc[src][cell_idx] = v_phys
            events.append({
                "type": "cell_voltage_item",
                "source": src,
                "cell_index": cell_idx,
                "voltage_v": v_phys,
            })
        else:
            # End of list!
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

    # 3. Temperature (3 Bytes: <Bh) List Streaming (Index=0 -> END_OF_LIST)
    elif cmd == BmsCommand.TEMPERATURE and len(payload) >= 3:
        sensor_idx, t_raw = struct.unpack("<Bh", payload[:3])
        if sensor_idx != END_OF_LIST:
            t_phys = to_physical(t_raw, 0.1, decimals=1)
            temperatures_acc[src][sensor_idx] = t_phys
            events.append({
                "type": "temperature_item",
                "source": src,
                "sensor_index": sensor_idx,
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

    # 4. Balancing (2 Bytes: <BB) List Streaming (Index=0 -> END_OF_LIST)
    elif cmd == BmsCommand.BALANCING and len(payload) >= 2:
        cell_idx, state = struct.unpack("<BB", payload[:2])
        if cell_idx != END_OF_LIST:
            balancing_acc[src][cell_idx] = bool(state)
            events.append({
                "type": "balancing_item",
                "source": src,
                "cell_index": cell_idx,
                "balancing": bool(state),
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
    """Decode DIAGNOSTIC frames (GET_FAULTS list streaming with 0x0000 END_OF_FAULT_LIST)."""
    cmd = frame.command
    payload = frame.payload
    src = frame.source
    events = []

    if cmd == DiagnosticCommand.GET_FAULTS and len(payload) >= 10:
        fault_id, severity, state, count, uptime = struct.unpack("<HBBHI", payload[:10])
        if fault_id != END_OF_FAULT_LIST:
            info = get_fault_info(src, fault_id)
            sev_name = FaultSeverity(severity).name if severity in FaultSeverity else "UNKNOWN"
            state_name = FaultState(state).name if state in FaultState else "UNKNOWN"
            record = {
                "fault_id": fault_id,
                "fault_code": f"0x{fault_id:04X}",
                "name": info.name,
                "description": info.description,
                "severity": severity,
                "severity_name": sev_name,
                "state": state,
                "state_name": state_name,
                "occurrence_count": count,
                "last_occurrence_ms": uptime,
            }
            faults_acc[src].append(record)
            events.append({
                "type": "fault_item",
                "source": src,
                "fault": record,
            })
        else:
            # End of fault list received!
            all_faults = list(faults_acc[src])
            events.append({
                "type": "faults_complete",
                "source": src,
                "total_faults": len(all_faults),
                "faults": all_faults,
            })
            faults_acc[src].clear()

    elif cmd == DiagnosticCommand.CLEAR_FAULTS and len(payload) >= 1:
        events.append({
            "type": "clear_faults_response",
            "source": src,
            "result_code": payload[0],
            "result_name": ResultCode(payload[0]).name if payload[0] in ResultCode else "UNKNOWN",
        })

    return events


def decode_lighting(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == LightingCommand.STATUS and len(payload) >= 6:
        hl, bl, tl, tr, hz, flt = struct.unpack("<BBBBBB", payload[:6])
        return {
            "type": "status",
            "source": frame.source,
            "headlight": hl,
            "headlight_name": LightState(hl).name if hl in LightState else "UNKNOWN",
            "brake_light": bl,
            "brake_light_name": LightState(bl).name if bl in LightState else "UNKNOWN",
            "turn_left": tl,
            "turn_left_name": LightState(tl).name if tl in LightState else "UNKNOWN",
            "turn_right": tr,
            "turn_right_name": LightState(tr).name if tr in LightState else "UNKNOWN",
            "hazard": hz,
            "hazard_name": LightState(hz).name if hz in LightState else "UNKNOWN",
            "fault_flags": f"0x{flt:02X}",
        }

    return {"type": "lighting_generic", "source": frame.source, "command": cmd, "raw": payload.hex()}


def decode_config(frame: UniversalDeosFrame) -> Dict[str, Any]:
    cmd = frame.command
    payload = frame.payload

    if cmd == ConfigCommand.GET_PARAMETER and len(payload) >= 2:
        param_id = struct.unpack("<H", payload[:2])[0]
        param_info = get_parameter_info(frame.service, param_id)
        val = None
        raw_val = None

        if len(payload) > 2:
            data = payload[2:]
            data_type = param_info.data_type if param_info else "uint16"
            scale = param_info.scale if param_info else 1.0

            if data_type == "uint8" and len(data) >= 1:
                raw_val = data[0]
            elif data_type == "int8" and len(data) >= 1:
                raw_val = struct.unpack("<b", data[:1])[0]
            elif data_type == "int16" and len(data) >= 2:
                raw_val = struct.unpack("<h", data[:2])[0]
            elif data_type == "uint32" and len(data) >= 4:
                raw_val = struct.unpack("<I", data[:4])[0]
            elif data_type == "int32" and len(data) >= 4:
                raw_val = struct.unpack("<i", data[:4])[0]
            elif len(data) >= 2:
                raw_val = struct.unpack("<H", data[:2])[0]

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
            "result_name": ResultCode(res).name if res in ResultCode else "UNKNOWN",
        }

    elif cmd == ConfigCommand.SAVE_PARAMETERS and len(payload) >= 1:
        res = payload[0]
        return {
            "type": "save_parameters_response",
            "source": frame.source,
            "service": frame.service,
            "result_code": res,
            "result_name": ResultCode(res).name if res in ResultCode else "UNKNOWN",
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

    logger.debug("Received Pure Frame: Srv=0x%02X Cmd=0x%02X Src=0x%02X Seq=%d", srv, cmd, src, frame.sequence)

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

    elif srv == ServiceId.DIAGNOSTIC:
        events = decode_diagnostic(frame)
        for ev in events:
            client.publish("telemetry/diagnostic", json.dumps(ev))

    elif srv == ServiceId.LIGHTING:
        res = decode_lighting(frame)
        client.publish("telemetry/lighting", json.dumps(res))

    # Generic configuration or responses
    if cmd in (ConfigCommand.GET_PARAMETER, ConfigCommand.SET_PARAMETER, ConfigCommand.SAVE_PARAMETERS):
        res = decode_config(frame)
        client.publish("telemetry/config", json.dumps(res))

    elif frame.message_class == MessageClass.RESPONSE and len(frame.payload) >= 1:
        # Fallback for unexpected generic response
        res_code = frame.payload[0]
        client.publish(
            "telemetry/system",
            json.dumps({
                "type": "generic_response",
                "source": src,
                "service": srv,
                "command": cmd,
                "result_code": res_code,
                "result_name": ResultCode(res_code).name if res_code in ResultCode else "UNKNOWN",
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

