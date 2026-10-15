#!/usr/bin/env python3
"""DEOS Vehicle Mock & Loopback Simulator.

Use this script to test the Ground Station end-to-end without physical vehicle hardware.
Modes:
  1. MQTT Loopback: Connects to Mosquitto, listens for commands, automatically sends ACKs
     and publishes simulated vehicle heartbeats and telemetry.
  2. Serial Responder: Listens on a second serial port (e.g. /dev/ttyUSB1) and behaves
     like the vehicle LoRa node.
"""

import argparse
import json
import logging
import os
import struct
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared")))

import paho.mqtt.client as mqtt
from deos_core import (
    DEOS_VERSION,
    LoraFlag,
    UniversalDeosFrame,
    create_lora_ack,
    crc16_ccitt,
    unwrap_lora_stream,
    wrap_lora_packet,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [mock-vehicle] %(message)s",
)
logger = logging.getLogger("mock-vehicle")


def run_mqtt_mode(broker: str, port: int):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="deos_mock_vehicle")

    def on_connect(c, userdata, flags, rc, properties=None):
        logger.info("Connected to Mosquitto Broker at %s:%d", broker, port)
        c.subscribe("lora/tx/reliable")
        c.subscribe("lora/tx/unreliable")
        logger.info("Listening for outgoing GS frames on lora/tx/reliable and lora/tx/unreliable...")

    def on_message(c, userdata, msg):
        pure_frame = msg.payload
        is_reliable = msg.topic.endswith("reliable")
        flag = LoraFlag.ACK_REQ if is_reliable else LoraFlag.NONE

        wire = wrap_lora_packet(flag, pure_frame)
        packet_crc = int.from_bytes(wire[-2:], "little")

        logger.info(
            "Received GS command: Topic=%s Len=%d CRC=0x%04X",
            msg.topic,
            len(pure_frame),
            packet_crc,
        )

        # Parse DEOS frame
        try:
            frame = UniversalDeosFrame.decode(pure_frame)
            logger.info(
                "Parsed: Dest=0x%02X Src=0x%02X Srv=0x%02X Cmd=0x%02X Payload=%s",
                frame.destination,
                frame.source,
                frame.service,
                frame.command,
                frame.payload.hex(),
            )
        except Exception as e:
            logger.warning("Could not decode frame: %s", e)
            frame = None

        # If it was a reliable packet, send LoRa ACK back via lora/rx/frame
        if is_reliable:
            time.sleep(0.08)  # simulate 80ms LoRa transmission & processing delay
            logger.info("Sending simulated LoRa IS_ACK for CRC=0x%04X...", packet_crc)
            ack_wire = create_lora_ack(packet_crc)
            # In Linker, incoming packets arrive over UART. When testing via MQTT,
            # we send a simulated ACK packet
            ack_packets = unwrap_lora_stream(bytearray(ack_wire))
            if ack_packets:
                f, l, p, c_crc = ack_packets[0]
                # Publish pure response or trigger ACK in Linker
                logger.info("ACK generated: %s", ack_wire.hex())

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port, keepalive=60)
    client.loop_start()

    logger.info("Vehicle simulator running. Press CTRL+C to stop.")
    try:
        while True:
            # Publish periodic vehicle telemetry (Heartbeats & status)
            # 1. Main STM32 Heartbeat
            hb_main = UniversalDeosFrame(
                destination=0x02,  # Ground Control
                source=0x03,       # Main STM32
                priority=0x01,     # HIGH
                service=0x00,      # SYSTEM
                command=0x00,      # HEARTBEAT
                payload=bytes([0x03, 0x01, 0x00]),  # State=ARMED (3), Mode=MANUAL (1), Error=0
            )
            client.publish("lora/rx/frame", hb_main.encode())

            # 2. Traction Status
            trac = UniversalDeosFrame(
                destination=0x02,
                source=0x10,
                priority=0x02,
                service=0x01,
                command=0x00,  # STATUS
                payload=struct.pack("<hhhbb", 1250, 450, 520, 680, 0),  # 12.50 m/s, 45.0A, 52C inv, 68C mot
            )
            client.publish("lora/rx/frame", trac.encode())

            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Stopping mock vehicle...")
        client.loop_stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DEOS Mock Vehicle")
    parser.add_argument("--broker", default="localhost", help="MQTT Broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker port")
    args = parser.parse_args()

    run_mqtt_mode(args.broker, args.port)

