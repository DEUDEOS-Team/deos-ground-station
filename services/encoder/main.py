"""DEOS Encoder Microservice (Stateless, C-Struct Payload Packing).

Receives JSON commands from `command/request`, validates them against ICD constraints,
packs payloads using `deos_types.h` C structs (`payloads.py`), builds a media-independent
Universal DEOS Transport Frame via the C engine, and publishes pure raw frame bytes to
either `lora/tx/reliable` (when ack=True) or `lora/tx/unreliable` (when ack=False).

CRITICAL RULE:
Yer istasyonu kesinlikle 29-bit CAN ID veya CAN Frame üretmez.
Yalnızca medya bağımsız Saf DEOS Evrensel Çerçevesi üretir.
0xAA 0x55, Flag, Length ve CRC16 L2 zarflaması Linker servisine aittir.
"""

import json
import logging
import os
import time
from typing import Any, Dict

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from deos_core import (
    BmsCommand,
    BrakeCommand,
    BrakeModePayload,
    BrakeParkPayload,
    BrakePrefillPayload,
    BrakeTargetPayload,
    CalibrationCommand,
    ConfigCommand,
    DEOS_VERSION,
    DiagnosticCommand,
    HeartbeatPayload,
    LightingCommand,
    LightingCommandPayload,
    NodeId,
    ParameterHeaderPayload,
    PingPongPayload,
    ResetNodePayload,
    SensorsCommand,
    ServiceId,
    SteeringCommand,
    SteeringModePayload,
    SteeringTargetPayload,
    SubscribeReqPayload,
    SystemCommand,
    SystemModePayload,
    SystemStatePayload,
    TractionCommand,
    TractionGearPayload,
    TractionTargetPayload,
    TractionTorqueLimitPayload,
    UniversalDeosFrame,
    UnsubscribeReqPayload,
    get_parameter_info,
    pack_parameter_payload,
    to_raw,
)
from deos_core.models import CommandRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [encoder] %(message)s",
)
logger = logging.getLogger("encoder")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
SOURCE_NODE = int(os.getenv("DEOS_SOURCE_NODE", str(int(NodeId.GROUND_CONTROL))), 0)
PROTOCOL_VERSION = int(os.getenv("DEOS_PROTOCOL_VERSION", str(DEOS_VERSION)), 0)
FRAME_LAYOUT = os.getenv("DEOS_FRAME_LAYOUT", "UNIVERSAL_9B")

tx_sequence = 0


def next_sequence() -> int:
    global tx_sequence
    seq = tx_sequence
    tx_sequence = (tx_sequence + 1) % 256
    return seq


def _clamp_u16(value: int) -> int:
    return max(0, min(0xFFFF, int(value)))


def _clamp_i16(value: int) -> int:
    return max(-32768, min(32767, int(value)))


def _extract_raw_payload(params: Dict[str, Any]) -> bytes:
    if "raw_payload" in params and params["raw_payload"] is not None:
        raw = params["raw_payload"]
        if isinstance(raw, str):
            return bytes.fromhex(raw)
        if isinstance(raw, (list, bytes, bytearray)):
            return bytes(raw)
    return b""


def pack_payload(service: int, command: int, params: Dict[str, Any]) -> bytes:
    """Pack command-specific parameters into Little-Endian C struct bytes (`deos_types.h`)."""
    # 0. Common Parameter Configuration (0xE0 - 0xE4 across any service)
    if command in (ConfigCommand.GET_PARAMETER, ConfigCommand.GET_PARAMETER_INFO):
        param_id = int(params.get("param_id", 0)) & 0xFFFF
        return ParameterHeaderPayload(parameter_id=param_id).to_bytes()
    elif command == ConfigCommand.SET_PARAMETER:
        param_id = int(params.get("param_id", 0)) & 0xFFFF
        param_info = get_parameter_info(service, param_id)
        val = float(params.get("value", 0.0))
        scale = param_info.scale if param_info else 1.0
        raw_val = to_raw(val, scale)
        data_type = param_info.data_type if param_info else "uint16"
        return pack_parameter_payload(param_id, data_type, raw_val)
    elif command in (ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
        return b""

    # 1. SYSTEM Service
    if service == ServiceId.SYSTEM:
        if command in (
            SystemCommand.GET_STATE,
            SystemCommand.GET_MODE,
            SystemCommand.GET_NODE_INFO,
            SystemCommand.GET_SUBSCRIPTIONS,
        ):
            return b""
        elif command == SystemCommand.SET_STATE:
            return SystemStatePayload(state=int(params.get("target_state", 0)) & 0xFF).to_bytes()
        elif command == SystemCommand.SET_MODE:
            return SystemModePayload(mode=int(params.get("target_mode", 0)) & 0xFF).to_bytes()
        elif command == SystemCommand.RESET_NODE:
            return ResetNodePayload(subcommand=int(params.get("subcommand", 0)) & 0xFF).to_bytes()
        elif command == SystemCommand.HEARTBEAT:
            return HeartbeatPayload(current_state=int(params.get("current_state", 0x03)) & 0xFF).to_bytes()
        elif command in (SystemCommand.PING, SystemCommand.PONG):
            ping_id = int(params.get("ping_id", int(time.time() * 1000))) & 0xFFFFFFFF
            return PingPongPayload(ping_id=ping_id).to_bytes()
        elif command == SystemCommand.SUBSCRIBE:
            return SubscribeReqPayload(
                target_service=int(params.get("target_service", 0)) & 0xFF,
                target_command=int(params.get("target_command", 0)) & 0xFF,
                interval_ms=int(params.get("interval_ms", 100)) & 0xFFFF,
                lease_ttl_s=int(params.get("lease_ttl_s", 0)) & 0xFFFF,
            ).to_bytes()
        elif command == SystemCommand.UNSUBSCRIBE:
            return UnsubscribeReqPayload(
                target_service=int(params.get("target_service", 0)) & 0xFF,
                target_command=int(params.get("target_command", 0xFF)) & 0xFF,
            ).to_bytes()

    # 2. TRACTION Service (4-byte deos_traction_target_payload)
    elif service == ServiceId.TRACTION:
        if command == TractionCommand.SET_TARGET_SPEED:
            spd = float(params.get("target_speed", 0.0))
            acc_param = params.get("target_accel")
            acc = float(acc_param) if acc_param is not None else 0.0
            return TractionTargetPayload(
                target_speed=_clamp_u16(to_raw(spd, 0.01)),
                target_accel=_clamp_i16(to_raw(acc, 0.01)),
            ).to_bytes()
        elif command == TractionCommand.GET_STATUS:
            return b""
        elif command == TractionCommand.SET_GEAR:
            gear_val = int(params.get("target_gear", params.get("gear", 0))) & 0xFF
            return TractionGearPayload(gear=gear_val).to_bytes()
        elif command == TractionCommand.SET_TORQUE_LIMIT:
            torque = float(params.get("dynamic_torque_limit", params.get("torque_limit", 100.0)))
            return TractionTorqueLimitPayload(
                torque_limit=_clamp_u16(to_raw(torque, 0.01)),
            ).to_bytes()

    # 3. STEERING Service (4-byte deos_steering_target_payload)
    elif service == ServiceId.STEERING:
        if command == SteeringCommand.SET_TARGET_ANGLE:
            ang = float(params.get("target_angle", 0.0))
            vel_param = params.get("target_angular_velocity")
            vel = float(vel_param) if vel_param is not None else 0.0
            return SteeringTargetPayload(
                target_angle=_clamp_i16(to_raw(ang, 0.01)),
                target_angular_velocity=_clamp_u16(to_raw(vel, 0.01)),
            ).to_bytes()
        elif command == SteeringCommand.GET_STATUS:
            return b""
        elif command == SteeringCommand.SET_MODE:
            mode_val = int(params.get("mode", params.get("steering_control_mode", 0))) & 0xFF
            return SteeringModePayload(mode=mode_val).to_bytes()

    # 4. BRAKE Service (4-byte deos_brake_target_payload)
    elif service == ServiceId.BRAKE:
        if command == BrakeCommand.SET_TARGET:
            demand_param = params.get("target_brake_demand")
            decel_param = params.get("target_deceleration")
            demand = float(demand_param) if demand_param is not None else 0.0
            decel = float(decel_param) if decel_param is not None else 0.0
            return BrakeTargetPayload(
                target_brake_demand=_clamp_u16(to_raw(demand, 0.01)),
                target_deceleration=_clamp_i16(to_raw(decel, 0.01)),
            ).to_bytes()
        elif command == BrakeCommand.GET_STATUS:
            return b""
        elif command == BrakeCommand.SET_MODE:
            mode_val = int(params.get("mode", params.get("brake_control_mode", 0))) & 0xFF
            return BrakeModePayload(mode=mode_val).to_bytes()
        elif command == BrakeCommand.SET_PARK:
            return BrakeParkPayload(
                target_park_brake=int(params.get("target_park_brake", 0)) & 0xFF,
            ).to_bytes()
        elif command == BrakeCommand.SET_PREFILL:
            prefill_val = params.get("brake_prefill_cmd", params.get("prefill_cmd", False))
            return BrakePrefillPayload(prefill_cmd=1 if prefill_val else 0).to_bytes()

    # 5. BMS Service
    elif service == ServiceId.BMS:
        if command in (
            BmsCommand.GET_STATUS,
            BmsCommand.GET_CELL_VOLTAGES,
            BmsCommand.GET_TEMPERATURES,
            BmsCommand.GET_BALANCING,
        ):
            return b""

    # 6. CALIBRATION Service
    elif service == ServiceId.CALIBRATION:
        if command in (
            CalibrationCommand.START,
            CalibrationCommand.ABORT,
            CalibrationCommand.GET_STATUS,
            CalibrationCommand.SAVE_RESULT,
            CalibrationCommand.CLEAR_RESULT,
        ):
            return _extract_raw_payload(params)

    # 7. DIAGNOSTIC Service
    elif service == ServiceId.DIAGNOSTIC:
        if command in (DiagnosticCommand.GET_HEALTH, DiagnosticCommand.GET_FAULTS, DiagnosticCommand.CLEAR_FAULTS):
            return b""

    # 8. SENSORS Service
    elif service == ServiceId.SENSORS:
        if command == SensorsCommand.IMU_DATA:
            return b""

    # 9. LIGHTING Service
    elif service == ServiceId.LIGHTING:
        if command in (LightingCommand.TURN_ON, LightingCommand.TURN_OFF):
            light_id = int(params.get("light_id", 0x01)) & 0xFF
            return LightingCommandPayload(light_id=light_id).to_bytes()
        elif command == LightingCommand.GET_STATUS:
            if "light_id" in params and params["light_id"] is not None:
                return LightingCommandPayload(light_id=int(params["light_id"]) & 0xFF).to_bytes()
            return b""

    return _extract_raw_payload(params)


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Connected to Mosquitto Broker at %s:%d", MQTT_BROKER, MQTT_PORT)
        client.subscribe("command/request")
        logger.info("Subscribed to topic: command/request")
    else:
        logger.error("Failed to connect to broker, return code %d", rc)


def on_message(client, userdata, msg):
    try:
        raw_text = msg.payload.decode("utf-8")
        data = json.loads(raw_text)
    except Exception as e:
        logger.warning("Invalid JSON received on %s: %s", msg.topic, e)
        client.publish("command/status", json.dumps({"status": "ERROR", "error": f"Invalid JSON: {e}"}))
        return

    try:
        cmd_req = CommandRequest(**data)
    except ValidationError as ve:
        err_msg = str(ve)
        logger.warning("ICD validation failed: %s", err_msg)
        client.publish("command/status", json.dumps({"status": "VALIDATION_ERROR", "error": err_msg}))
        return

    try:
        payload_bytes = pack_payload(cmd_req.service, cmd_req.command, cmd_req.params)
    except Exception as pe:
        logger.error("Failed to pack payload: %s", pe)
        client.publish("command/status", json.dumps({"status": "ENCODE_ERROR", "error": str(pe)}))
        return

    seq = next_sequence()
    frame = UniversalDeosFrame(
        destination=cmd_req.destination,
        source=SOURCE_NODE,
        priority=cmd_req.priority,
        version=PROTOCOL_VERSION,
        message_class=cmd_req.message_class,
        service=cmd_req.service,
        command=cmd_req.command,
        sequence=seq,
        payload=payload_bytes,
    )

    try:
        wire_frame = frame.encode(layout=FRAME_LAYOUT)
    except Exception as ee:
        logger.error("Failed to encode universal frame: %s", ee)
        client.publish("command/status", json.dumps({"status": "FRAME_ENCODE_ERROR", "error": str(ee)}))
        return

    target_topic = "lora/tx/reliable" if cmd_req.ack else "lora/tx/unreliable"
    client.publish(target_topic, wire_frame)
    logger.info(
        "Encoded & published [%s] -> %s(0x%02X) Class=%s Svc=%s(0x%02X) Cmd=%s(0x%02X) Seq=%d Len=%d to %s",
        FRAME_LAYOUT,
        frame.destination_name,
        cmd_req.destination,
        frame.class_name,
        frame.service_name,
        cmd_req.service,
        frame.command_name,
        cmd_req.command,
        seq,
        len(wire_frame),
        target_topic,
    )


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="deos_encoder")
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
