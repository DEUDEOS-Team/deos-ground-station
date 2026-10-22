"""DEOS Ground Station Web UI Backend (FastAPI + WebSocket + MQTT Bridge).

Connects to Mosquitto, bridges `telemetry/#` and `command/status` to WebSocket clients,
and exposes REST endpoints for issuing commands and fetching registry definitions.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    PARAMETERS,
    COMMON_FAULTS,
    NODE_FAULTS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [web-ui] %(message)s",
)
logger = logging.getLogger("web-ui")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

connected_websockets: Set[WebSocket] = set()
event_loop: asyncio.AbstractEventLoop = None
mqtt_client: mqtt.Client = None
last_hardware_status: Optional[Dict[str, Any]] = None


def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Web UI connected to MQTT broker at %s:%d", MQTT_BROKER, MQTT_PORT)
        client.subscribe("telemetry/#")
        client.subscribe("command/status")
        logger.info("Subscribed to telemetry/# and command/status")
    else:
        logger.error("Failed to connect to broker, rc=%d", rc)


def on_mqtt_message(client, userdata, msg):
    global event_loop, last_hardware_status
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        payload = {"raw": msg.payload.hex()}

    if topic == "telemetry/hardware":
        last_hardware_status = payload

    event = {
        "topic": topic,
        "data": payload,
    }

    if event_loop and event_loop.is_running() and connected_websockets:
        message_str = json.dumps(event)
        for ws in list(connected_websockets):
            asyncio.run_coroutine_threadsafe(ws.send_text(message_str), event_loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global event_loop, mqtt_client
    event_loop = asyncio.get_running_loop()

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="deos_web_ui")
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.warning("Could not connect immediately to MQTT: %s", e)

    yield

    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


app = FastAPI(title="DEOS Ground Station", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "static"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    logger.info("WebSocket client connected (%d active)", len(connected_websockets))

    # Send cached hardware status immediately on connection
    if last_hardware_status:
        try:
            await websocket.send_text(json.dumps({
                "topic": "telemetry/hardware",
                "data": last_hardware_status
            }))
        except Exception:
            pass

    try:
        while True:
            # Keepalive / listen for possible incoming ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)
        logger.info("WebSocket client disconnected (%d active)", len(connected_websockets))


@app.get("/api/hardware/status")
async def get_hardware_status():
    """Return latest cached hardware status."""
    return last_hardware_status or {"connected": False, "mode": "UNKNOWN"}


@app.post("/api/command")
async def send_command(cmd: Dict[str, Any]):
    """Publish command request to MQTT topic `command/request`."""
    if not mqtt_client:
        raise HTTPException(status_code=503, detail="MQTT client not ready")

    try:
        payload = json.dumps(cmd)
        mqtt_client.publish("command/request", payload)
        logger.info("Published to command/request: %s", payload)
        return {"status": "SUCCESS", "message": "Command submitted to encoder"}
    except Exception as e:
        logger.error("Failed to publish command: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry")
async def get_registry():
    """Return dictionary of available parameters, faults, nodes, and services."""
    nodes = [{"id": n.value, "name": n.name} for n in NodeId]
    services = [{"id": s.value, "name": s.name} for s in ServiceId]

    parameters_list = []
    for (srv, pid), p in PARAMETERS.items():
        parameters_list.append({
            "service_id": srv,
            "param_id": pid,
            "param_id_hex": f"0x{pid:04X}",
            "name": p.name,
            "data_type": p.data_type,
            "scale": p.scale,
            "unit": p.unit,
            "description": p.description,
            "default_val": p.default_val,
            "min_val": p.min_val,
            "max_val": p.max_val,
        })

    faults_list = []
    for fid, f in COMMON_FAULTS.items():
        faults_list.append({
            "node_id": None,
            "fault_id": fid,
            "fault_code": f"0x{fid:04X}",
            "name": f.name,
            "description": f.description,
            "severity": f.default_severity.value,
        })
    for (nid, fid), f in NODE_FAULTS.items():
        faults_list.append({
            "node_id": nid,
            "fault_id": fid,
            "fault_code": f"0x{fid:04X}",
            "name": f.name,
            "description": f.description,
            "severity": f.default_severity.value,
        })

    commands_map = {
        "SYSTEM": [{"id": c.value, "name": c.name} for c in SystemCommand],
        "TRACTION": [{"id": c.value, "name": c.name} for c in TractionCommand],
        "STEERING": [{"id": c.value, "name": c.name} for c in SteeringCommand],
        "BRAKE": [{"id": c.value, "name": c.name} for c in BrakeCommand],
        "BMS": [{"id": c.value, "name": c.name} for c in BmsCommand],
        "DIAGNOSTIC": [{"id": c.value, "name": c.name} for c in DiagnosticCommand],
        "LIGHTING": [{"id": c.value, "name": c.name} for c in LightingCommand],
        "CONFIG": [{"id": c.value, "name": c.name} for c in ConfigCommand],
    }

    return {
        "nodes": nodes,
        "services": services,
        "parameters": parameters_list,
        "faults": faults_list,
        "commands": commands_map,
    }
