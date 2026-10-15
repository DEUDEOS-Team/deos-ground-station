"""DEOS Encoder Microservice (Stateless).

Receives JSON commands from `command/request`, validates them against ICD constraints,
builds a media-independent Universal DEOS Transport Frame, and publishes pure raw frame
bytes to either `lora/tx/reliable` (when ack=True) or `lora/tx/unreliable` (when ack=False).

CRITICAL RULE:
Yer istasyonu kesinlikle 29-bit CAN ID veya CAN Frame üretmez.
Yalnızca medya bağımsız Saf DEOS Evrensel Çerçevesi üretir.
0xAA 0x55, Flag, Length ve CRC16 L2 zarflaması Linker servisine aittir.
"""

import json
import logging
import os
import struct
import sys
import time
from typing import Any, Dict

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from deos_core import (
    BmsCommand,
    BrakeCommand,
    ConfigCommand,
    DEOS_VERSION,
    DiagnosticCommand,
    LightingCommand,
    NodeId,
    ServiceId,
    SteeringCommand,
    SystemCommand,
    TractionCommand,
    UniversalDeosFrame,
    get_parameter_info,
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


def pack_payload(service: int, command: int, params: Dict[str, Any]) -> bytes:
    """Pack command-specific parameters into Little-Endian bytes."""
    # 1. SYSTEM Service
    if service == ServiceId.SYSTEM:
        if command in (SystemCommand.GET_STATE, SystemCommand.GET_MODE, SystemCommand.GET_NODE_INFO):
            return b""
        elif command == SystemCommand.SET_STATE:
            return struct.pack("<B", int(params.get("target_state", 0)) & 0xFF)
        elif command == SystemCommand.SET_MODE:
            return struct.pack("<B", int(params.get("target_mode", 0)) & 0xFF)
        elif command == SystemCommand.RESET_NODE:
            return struct.pack("<B", int(params.get("subcommand", 0)) & 0xFF)
        elif command == SystemCommand.HEARTBEAT:
            return struct.pack("<B", int(params.get("current_state", 0x03)) & 0xFF)
        elif command in (SystemCommand.PING, SystemCommand.PONG):
            ping_id = int(params.get("ping_id", int(time.time() * 1000) & 0xFFFFFFFF))
            return struct.pack("<I", ping_id)
        elif command == SystemCommand.SUBSCRIBE:
            target_service = int(params.get("target_service", 0)) & 0xFF
            target_command = int(params.get("target_command", 0)) & 0xFF
            interval_ms = int(params.get("interval_ms", 100)) & 0xFFFF
            lease_ttl_s = int(params.get("lease_ttl_s", 0)) & 0xFFFF
            return struct.pack("<BBHH", target_service, target_command, interval_ms, lease_ttl_s)
        elif command == SystemCommand.UNSUBSCRIBE:
            target_service = int(params.get("target_service", 0)) & 0xFF
            target_command = int(params.get("target_command", 0xFF)) & 0xFF
            return struct.pack("<BB", target_service, target_command)

    # 2. TRACTION Service
    elif service == ServiceId.TRACTION:
        if command == TractionCommand.SET_SPEED:
            spd = float(params.get("target_speed", 0.0))
            spd_raw = to_raw(spd, 0.01)
            if "target_accel" in params and params["target_accel"] is not None:
                acc = float(params["target_accel"])
                acc_raw = to_raw(acc, 0.01)
                return struct.pack("<HH", spd_raw & 0xFFFF, acc_raw & 0xFFFF)
            return struct.pack("<H", spd_raw & 0xFFFF)
        elif command == TractionCommand.GET_STATUS:
            return b""
        elif command == TractionCommand.SET_GEAR:
            return struct.pack("<B", int(params.get("target_gear", 0)) & 0xFF)
        elif command == TractionCommand.SET_TORQUE:
            torque = float(params.get("dynamic_torque_limit", 100.0))
            t_raw = to_raw(torque, 0.01)
            return struct.pack("<H", t_raw & 0xFFFF)

    # 3. STEERING Service
    elif service == ServiceId.STEERING:
        if command == SteeringCommand.SET_TARGET_ANGLE:
            ang = float(params.get("target_angle", 0.0))
            ang_raw = to_raw(ang, 0.01)
            if "target_angular_velocity" in params and params["target_angular_velocity"] is not None:
                vel = float(params["target_angular_velocity"])
                vel_raw = to_raw(vel, 0.01)
                return struct.pack("<hH", ang_raw, vel_raw & 0xFFFF)
            return struct.pack("<h", ang_raw)
        elif command == SteeringCommand.GET_STATUS:
            return b""
        elif command == SteeringCommand.SET_CONTROL_MODE:
            return struct.pack("<B", int(params.get("steering_control_mode", 0)) & 0xFF)

    # 4. BRAKE Service
    elif service == ServiceId.BRAKE:
        if command == BrakeCommand.SET_DEMAND:
            demand = float(params.get("target_brake_demand", 0.0))
            d_raw = to_raw(demand, 0.01)
            return struct.pack("<H", d_raw & 0xFFFF)
        elif command == BrakeCommand.GET_STATUS:
            return b""
        elif command == BrakeCommand.SET_DECELERATION:
            if "estop_brake_override" in params and params["estop_brake_override"] is not None:
                return struct.pack("<B", 1 if params["estop_brake_override"] else 0)
            decel = float(params.get("target_deceleration", 0.0))
            dec_raw = to_raw(decel, 0.01)
            return struct.pack("<H", dec_raw & 0xFFFF)
        elif command == BrakeCommand.SET_CONTROL_MODE:
            return struct.pack("<B", int(params.get("brake_control_mode", 0)) & 0xFF)
        elif command == BrakeCommand.SET_PARK_BRAKE:
            return struct.pack("<B", int(params.get("target_park_brake", 0)) & 0xFF)
        elif command == BrakeCommand.SET_PREFILL:
            return struct.pack("<B", 1 if params.get("brake_prefill_cmd") else 0)

    # 5. BMS Service
    elif service == ServiceId.BMS:
        if command in (
            BmsCommand.GET_STATUS,
            BmsCommand.GET_CELL_VOLTAGES,
            BmsCommand.GET_TEMPERATURES,
            BmsCommand.GET_BALANCING,
        ):
            return b""

    # 6. DIAGNOSTIC Service
    elif service == ServiceId.DIAGNOSTIC:
        if command in (DiagnosticCommand.GET_HEALTH, DiagnosticCommand.GET_FAULTS, DiagnosticCommand.CLEAR_FAULTS):
            return b""

    # 7. LIGHTING Service
    elif service == ServiceId.LIGHTING:
        if command in (LightingCommand.TURN_ON, LightingCommand.TURN_OFF):
            light_id = int(params.get("light_id", 0x01)) & 0xFF
            return struct.pack("<B", light_id)
        elif command == LightingCommand.GET_STATUS:
            if "light_id" in params and params["light_id"] is not None:
                return struct.pack("<B", int(params["light_id"]) & 0xFF)
            return b""

    # 8. Common Parameter Configuration (0xE0 - 0xE4)
    if command == ConfigCommand.GET_PARAMETER:
        param_id = int(params.get("param_id", 0)) & 0xFFFF
        return struct.pack("<H", param_id)
    elif command == ConfigCommand.SET_PARAMETER:
        param_id = int(params.get("param_id", 0)) & 0xFFFF
        param_info = get_parameter_info(service, param_id)
        val = float(params.get("value", 0.0))
        scale = param_info.scale if param_info else 1.0
        raw_val = to_raw(val, scale)
        data_type = param_info.data_type if param_info else "uint16"

        if data_type == "uint8":
            return struct.pack("<HB", param_id, raw_val & 0xFF)
        elif data_type == "int8":
            return struct.pack("<Hb", param_id, raw_val)
        elif data_type == "int16":
            return struct.pack("<Hh", param_id, raw_val)
        elif data_type == "uint32":
            return struct.pack("<HI", param_id, raw_val & 0xFFFFFFFF)
        elif data_type == "int32":
            return struct.pack("<Hi", param_id, raw_val)
        else:  # uint16 default
            return struct.pack("<HH", param_id, raw_val & 0xFFFF)
    elif command in (ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
        return b""

    # If raw payload provided in params, use it
    if "raw_payload" in params:
        raw = params["raw_payload"]
        if isinstance(raw, str):
            return bytes.fromhex(raw)
        elif isinstance(raw, list):
            return bytes(raw)

    return b""


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
        "Encoded & published [%s] -> Dest=0x%02X Srv=0x%02X Cmd=0x%02X Seq=%d Len=%d to %s",
        FRAME_LAYOUT,
        cmd_req.destination,
        cmd_req.service,
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

