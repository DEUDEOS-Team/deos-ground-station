"""DEOS Linker Microservice (Stateful Transport & Hardware Layer).

Manages:
1. Physical / Virtual UART connection to LoRa module (Ebyte E220-900T22D / /dev/ttyUSB0)
2. LoRa L2 Wire Framing & Deframing:
   - [0xAA 0x55] [Flag: 1B] [Length: 1B] [Saf DEOS Frame / ACK Payload] [CRC16-CCITT: 2B LE]
3. Stop-and-Wait ARQ for outgoing Flag=0x01 (Reliable) packets:
   - Timeout (500-1000 ms, default 600 ms)
   - Max Retries (default 3)
   - Publishes status to `command/status` (SENT, ACKED, RETRYING, TIMEOUT)
4. Automatic Flag=0x02 (ACK) response for incoming Flag=0x01 packets from the vehicle.
5. Peeling (Deframing): Strips 0xAA 0x55, Flag, Length, and CRC16; publishes pure DEOS frame to `lora/rx/frame`.
"""

import json
import logging
import os
import threading
import time
from typing import Dict, Optional

import paho.mqtt.client as mqtt
import serial

from deos_core import (
    LoraFlag,
    create_lora_ack,
    unwrap_lora_stream,
    wrap_lora_packet,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [linker] %(message)s",
)
logger = logging.getLogger("linker")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
BAUD_RATE = int(os.getenv("BAUD_RATE", "9600"))
ACK_TIMEOUT_MS = int(os.getenv("ACK_TIMEOUT_MS", "1200"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
SERIAL_MOCK = os.getenv("SERIAL_MOCK", "false").lower() in ("true", "1", "yes")
MOCK_AUTO_ACK = os.getenv("MOCK_AUTO_ACK", "false").lower() in ("true", "1", "yes")


class PendingARQ:
    def __init__(self, crc: int, wire_packet: bytes, max_retries: int = MAX_RETRIES):
        self.crc = crc
        self.wire_packet = wire_packet
        self.attempts = 1
        self.max_retries = max_retries
        self.last_sent_time = time.monotonic()


class LinkerService:
    def __init__(self):
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="deos_linker")
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message

        self.ser: Optional[serial.Serial] = None
        self.ser_lock = threading.Lock()
        self.rx_buffer = bytearray()

        self.pending_arq: Dict[int, PendingARQ] = {}
        self.arq_lock = threading.Lock()

        self.running = True
        self.is_mock = SERIAL_MOCK
        self.is_connected = False
        self.last_port_missing_logged = False
        self._last_published_hw_state = None

    def publish_hardware_status(self, connected: bool, mode: str = "HARDWARE", error: Optional[str] = None, force: bool = False):
        """Publish transceiver hardware health to `telemetry/hardware` only on state change."""
        state_key = (connected, mode, error)
        if not force and self._last_published_hw_state == state_key:
            return
        self._last_published_hw_state = state_key
        self.is_connected = connected
        msg = {
            "connected": connected,
            "port": SERIAL_PORT,
            "baud": BAUD_RATE,
            "mode": mode,
            "error": error,
            "timestamp": time.time(),
        }
        try:
            self.mqtt_client.publish("telemetry/hardware", json.dumps(msg), retain=True)
            logger.info("Published hardware status: connected=%s, mode=%s, error=%s", connected, mode, error)
        except Exception as e:
            logger.warning("Failed publishing hardware status: %s", e)

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to Mosquitto Broker at %s:%d", MQTT_BROKER, MQTT_PORT)
            client.subscribe("lora/tx/reliable")
            client.subscribe("lora/tx/unreliable")
            logger.info("Subscribed to: lora/tx/reliable, lora/tx/unreliable")
            self.publish_hardware_status(
                connected=(self.ser is not None and self.ser.is_open),
                mode="MOCK" if self.is_mock else ("HARDWARE" if (self.ser and self.ser.is_open) else "DISCONNECTED"),
                force=True,
            )
        else:
            logger.error("Failed to connect to broker, return code %d", rc)

    def on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        deos_frame = msg.payload

        if not deos_frame:
            return

        is_reliable = topic.endswith("reliable")
        flag = LoraFlag.ACK_REQ if is_reliable else LoraFlag.NONE

        wire_packet = wrap_lora_packet(flag, deos_frame)
        packet_crc = int.from_bytes(wire_packet[-2:], byteorder="little")

        # Guard: Check if physical hardware is ready or explicit mock mode is active
        if not (self.ser and self.ser.is_open) and not self.is_mock:
            logger.error("TX DROPPED: Serial port %s is disconnected! Packet CRC=0x%04X", SERIAL_PORT, packet_crc)
            self.mqtt_client.publish(
                "command/status",
                json.dumps({
                    "status": "ERROR_NO_HARDWARE",
                    "crc": f"0x{packet_crc:04X}",
                    "error": f"LoRa USB transceiver ({SERIAL_PORT}) is disconnected! Please connect device.",
                }),
            )
            return

        logger.info(
            "TX [%s]: Flag=0x%02X Len=%d CRC=0x%04X (Total wire=%d bytes)",
            "RELIABLE" if is_reliable else "UNRELIABLE",
            flag,
            len(deos_frame),
            packet_crc,
            len(wire_packet),
        )

        if is_reliable:
            with self.arq_lock:
                self.pending_arq[packet_crc] = PendingARQ(packet_crc, wire_packet, MAX_RETRIES)

        self.write_to_serial(wire_packet)

        # Report TX status to command/status
        frame_info = None
        if len(deos_frame) >= 9:
            plen = deos_frame[8]
            payload_bytes = deos_frame[9 : 9 + plen] if len(deos_frame) >= 9 + plen else deos_frame[9:]
            frame_info = {
                "dest": f"0x{deos_frame[0]:02X}",
                "src": f"0x{deos_frame[1]:02X}",
                "priority": deos_frame[2],
                "version": f"0x{deos_frame[3]:02X}",
                "message_class": deos_frame[4],
                "service": f"0x{deos_frame[5]:02X}",
                "command": f"0x{deos_frame[6]:02X}",
                "sequence": deos_frame[7],
                "payload": " ".join(f"{b:02X}" for b in payload_bytes),
            }

        status_msg = {
            "status": "SENT_AWAITING_ACK" if is_reliable else "SENT_NO_ACK_REQUIRED",
            "crc": f"0x{packet_crc:04X}",
            "flag": flag,
            "attempt": 1 if is_reliable else None,
            "length": len(deos_frame),
            "wire_hex": " ".join(f"{b:02X}" for b in wire_packet),
            "deos_hex": " ".join(f"{b:02X}" for b in deos_frame),
            "frame_info": frame_info,
        }
        self.mqtt_client.publish("command/status", json.dumps(status_msg))

    def write_to_serial(self, data: bytes):
        """Write raw bytes to UART port or mock buffer."""
        with self.ser_lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(data)
                    self.ser.flush()
                    logger.info("UART TX (%d bytes): %s", len(data), data.hex())
                    return
                except Exception as e:
                    logger.error("Failed writing to serial: %s", e)
            elif self.is_mock:
                logger.info("[MOCK SERIAL] Wrote %d bytes: %s", len(data), data.hex())
                if MOCK_AUTO_ACK and len(data) >= 6 and data[2] == LoraFlag.ACK_REQ:
                    packet_crc = int.from_bytes(data[-2:], "little")
                    threading.Timer(0.1, self._simulate_mock_ack, args=[packet_crc]).start()
            else:
                logger.warning("Serial port is not open; dropped %d bytes", len(data))

    def _simulate_mock_ack(self, packet_crc: int):
        logger.info("[MOCK SERIAL] Simulating vehicle ACK response for CRC=0x%04X...", packet_crc)
        ack_wire = create_lora_ack(packet_crc)
        packets = unwrap_lora_stream(bytearray(ack_wire))
        for flag, length, payload_bytes, rx_crc in packets:
            self.handle_incoming_packet(flag, length, payload_bytes, rx_crc)

    def handle_incoming_packet(self, flag: int, length: int, payload_bytes: bytes, rx_crc: int):
        """Process verified incoming packet from LoRa UART."""
        # 1. Received an ACK from vehicle (Flag=0x02, Length=2)
        if flag == LoraFlag.IS_ACK and length == 2:
            acked_crc = int.from_bytes(payload_bytes[:2], byteorder="little")
            logger.info("RX IS_ACK received! Acknowledged CRC=0x%04X", acked_crc)

            with self.arq_lock:
                if acked_crc in self.pending_arq:
                    del self.pending_arq[acked_crc]
                    logger.info("ARQ for CRC=0x%04X confirmed and timer stopped.", acked_crc)
                    self.mqtt_client.publish(
                        "command/status",
                        json.dumps({
                            "status": "ACKED",
                            "crc": f"0x{acked_crc:04X}",
                        }),
                    )
                else:
                    logger.debug("Received ACK for unknown/expired CRC 0x%04X", acked_crc)

        # 2. Received a Data Packet from vehicle (Flag=0x00 or Flag=0x01)
        else:
            # If the vehicle requests an ACK (Flag=0x01), immediately reply with Flag=0x02 ACK
            if flag == LoraFlag.ACK_REQ:
                logger.info("Vehicle requested ACK for CRC=0x%04X. Sending automatic ACK...", rx_crc)
                ack_packet = create_lora_ack(rx_crc)
                self.write_to_serial(ack_packet)

            # Strip L2 Envelope: payload_bytes is the pure DEOS Universal Frame!
            logger.info("Deframed pure DEOS frame (%d bytes), publishing to lora/rx/frame", len(payload_bytes))
            self.mqtt_client.publish("lora/rx/frame", payload_bytes)

    def arq_watchdog_loop(self):
        """Background thread checking for ARQ retransmissions, timeouts, and periodic hardware status heartbeat."""
        timeout_sec = ACK_TIMEOUT_MS / 1000.0
        last_hw_heartbeat = 0.0

        while self.running:
            now = time.monotonic()

            # Periodic hardware health heartbeat (every 2.0s)
            if now - last_hw_heartbeat >= 2.0:
                last_hw_heartbeat = now
                with self.ser_lock:
                    is_open = (self.ser is not None and self.ser.is_open)
                self.publish_hardware_status(
                    connected=is_open or self.is_mock,
                    mode="MOCK" if self.is_mock else ("HARDWARE" if is_open else "DISCONNECTED"),
                )

            to_retry = []
            to_timeout = []

            with self.arq_lock:
                for crc, arq in list(self.pending_arq.items()):
                    if now - arq.last_sent_time >= timeout_sec:
                        if arq.attempts < arq.max_retries:
                            arq.attempts += 1
                            arq.last_sent_time = now
                            to_retry.append((crc, arq.wire_packet, arq.attempts))
                        else:
                            to_timeout.append(crc)
                            del self.pending_arq[crc]

            for crc, packet, attempt in to_retry:
                logger.warning(
                    "ARQ Timeout for CRC=0x%04X. Retrying attempt %d/%d...",
                    crc,
                    attempt,
                    MAX_RETRIES,
                )
                self.write_to_serial(packet)
                self.mqtt_client.publish(
                    "command/status",
                    json.dumps({
                        "status": "RETRYING",
                        "crc": f"0x{crc:04X}",
                        "attempt": attempt,
                    }),
                )

            for crc in to_timeout:
                logger.error("ARQ Max retries exhausted for CRC=0x%04X. TIMEOUT!", crc)
                self.mqtt_client.publish(
                    "command/status",
                    json.dumps({
                        "status": "TIMEOUT",
                        "crc": f"0x{crc:04X}",
                        "retries_exhausted": True,
                    }),
                )

            time.sleep(0.05)

    def serial_rx_loop(self):
        """Background thread reading from UART and unwraping LoRa frames."""
        backoff = 1.0

        while self.running:
            if not self.ser or not self.ser.is_open:
                if not os.path.exists(SERIAL_PORT) and not SERIAL_MOCK:
                    if not self.last_port_missing_logged:
                        logger.warning(
                            "Serial port %s not found. Waiting for USB transceiver to be plugged in...",
                            SERIAL_PORT,
                        )
                        self.last_port_missing_logged = True
                    self.is_mock = False
                    self.publish_hardware_status(
                        connected=False,
                        mode="DISCONNECTED",
                        error=f"Device {SERIAL_PORT} not found",
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 5.0)
                    continue

                if SERIAL_MOCK:
                    self.is_mock = True
                    self.publish_hardware_status(connected=True, mode="MOCK")
                    time.sleep(1.0)
                    continue

                try:
                    logger.info("Opening serial port %s at %d baud...", SERIAL_PORT, BAUD_RATE)
                    with self.ser_lock:
                        self.ser = serial.Serial(
                            port=SERIAL_PORT,
                            baudrate=BAUD_RATE,
                            timeout=0.1,
                        )
                    self.is_mock = False
                    self.last_port_missing_logged = False
                    backoff = 1.0
                    logger.info("Successfully opened %s", SERIAL_PORT)
                    self.publish_hardware_status(connected=True, mode="HARDWARE")
                except Exception as e:
                    logger.warning("Failed opening serial port (%s). Retrying in %.1fs...", e, backoff)
                    self.publish_hardware_status(connected=False, mode="ERROR", error=str(e))
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 5.0)
                    continue

            # Read available bytes from serial
            try:
                incoming = self.ser.read(self.ser.in_waiting or 1)
                if incoming:
                    logger.info("UART RX (%d bytes): %s", len(incoming), incoming.hex())
                    self.rx_buffer.extend(incoming)
                    packets = unwrap_lora_stream(self.rx_buffer)
                    for flag, length, payload_bytes, rx_crc in packets:
                        self.handle_incoming_packet(flag, length, payload_bytes, rx_crc)
            except Exception as e:
                logger.error("Error reading from serial port: %s", e)
                with self.ser_lock:
                    if self.ser:
                        try:
                            self.ser.close()
                        except Exception:
                            pass
                        self.ser = None
                self.publish_hardware_status(connected=False, mode="DISCONNECTED", error=str(e))
                time.sleep(1.0)

    def run(self):
        # Connect to MQTT
        while True:
            try:
                logger.info("Connecting to broker %s:%d...", MQTT_BROKER, MQTT_PORT)
                self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
                break
            except Exception as e:
                logger.warning("Broker not ready (%s), retrying in 2 seconds...", e)
                time.sleep(2)

        self.mqtt_client.loop_start()

        # Start RX and ARQ background threads
        rx_thread = threading.Thread(target=self.serial_rx_loop, daemon=True)
        arq_thread = threading.Thread(target=self.arq_watchdog_loop, daemon=True)
        rx_thread.start()
        arq_thread.start()

        logger.info("Linker service running.")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping linker service...")
            self.running = False


def main():
    service = LinkerService()
    service.run()


if __name__ == "__main__":
    main()

