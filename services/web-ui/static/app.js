// DEOS Ground Station Client Application
let ws = null;
let pingStartTime = 0;
let registryData = null;
let activeSubscriptions = [];

const KNOWN_NODES = [
    { id: 0x03, name: "Main STM32", type: "Physical (VCU/Router)", state: "UNKNOWN", lastSeen: null },
    { id: 0x10, name: "Traction ECU", type: "Physical ECU", state: "UNKNOWN", lastSeen: null },
    { id: 0x11, name: "Steering ECU", type: "Physical ECU", state: "UNKNOWN", lastSeen: null },
    { id: 0x12, name: "Brake ECU", type: "Physical ECU", state: "UNKNOWN", lastSeen: null },
    { id: 0x20, name: "BMS Main (HV)", type: "Hosted (Daly Proxy)", state: "UNKNOWN", lastSeen: null },
    { id: 0x21, name: "BMS Aux (LV)", type: "Hosted (Daly Proxy)", state: "UNKNOWN", lastSeen: null },
    { id: 0x30, name: "BMS Gateway", type: "Physical Gateway", state: "UNKNOWN", lastSeen: null },
    { id: 0x04, name: "ROS 2 Bridge", type: "Virtual Bridge", state: "UNKNOWN", lastSeen: null },
];

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    initNodesTable();
    initWebSocket();
    loadRegistry();
    fetchHardwareStatus();
});

async function fetchHardwareStatus() {
    try {
        const res = await fetch("/api/hardware/status");
        if (res.ok) {
            const data = await res.json();
            if (data && data.connected !== undefined) {
                updateHardwareStatusBadge(data);
            }
        }
    } catch (e) {
        console.warn("Failed fetching initial hardware status:", e);
    }
}

function initNodesTable() {
    const tbody = document.getElementById("nodesTableBody");
    tbody.innerHTML = "";
    KNOWN_NODES.forEach(n => {
        const row = document.createElement("tr");
        row.id = `node-row-${n.id}`;
        row.innerHTML = `
            <td><span class="status-pill offline" id="pill-node-${n.id}"></span><span id="statustext-node-${n.id}" class="text-light fw-medium">OFFLINE</span></td>
            <td><code class="text-info">0x${n.id.toString(16).padStart(2, "0").toUpperCase()}</code></td>
            <td class="text-white"><strong>${n.name}</strong></td>
            <td><span class="badge bg-dark border border-secondary">${n.type}</span></td>
            <td id="state-node-${n.id}"><span class="badge bg-secondary">UNKNOWN</span></td>
            <td id="seen-node-${n.id}" class="text-secondary small">Never</td>
            <td>
                <button class="btn btn-sm btn-outline-info" onclick="quickPing(${n.id})">Ping</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    const badge = document.getElementById("wsStatusBadge");

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        badge.className = "badge badge-status-online px-3 py-2 me-3";
        badge.innerHTML = '<i class="fa-solid fa-circle-check me-1"></i> WebSocket: Connected';
        logPacket("system/ws", { status: "CONNECTED" });
    };

    ws.onclose = () => {
        badge.className = "badge badge-status-offline px-3 py-2 me-3";
        badge.innerHTML = '<i class="fa-solid fa-circle-xmark me-1"></i> WebSocket: Disconnected (reconnecting...)';
        setTimeout(initWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleIncomingEvent(msg.topic, msg.data);
        } catch (e) {
            console.error("Failed to parse WS message:", e, event.data);
        }
    };
}

async function loadRegistry() {
    try {
        const res = await fetch("/api/registry");
        registryData = await res.json();
        updateSubCommandOptions();
        updateParameterList();
    } catch (e) {
        console.error("Failed loading registry:", e);
    }
}

function handleIncomingEvent(topic, data) {
    logPacket(topic, data);

    // 0. HARDWARE STATUS
    if (topic === "telemetry/hardware") {
        updateHardwareStatusBadge(data);
    }
    // Auto-detect: If any vehicle telemetry packet arrives over LoRa, transceiver is undeniably connected!
    else if (topic.startsWith("telemetry/")) {
        const badge = document.getElementById("hwStatusBadge");
        if (badge && badge.innerText.includes("Disconnected")) {
            updateHardwareStatusBadge({ connected: true, port: "/dev/ttyUSB0", mode: "HARDWARE" });
        }
    }

    // 0.1 COMMAND STATUS (ARQ & Hardware Errors)
    else if (topic === "command/status") {
        if (data.status === "ERROR_NO_HARDWARE") {
            const resBox = document.getElementById("pingResultBox");
            if (resBox) {
                resBox.className = "mt-3 p-2 rounded bg-black border border-danger text-center small text-danger";
                resBox.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-1"></i> ${data.error || "LoRa USB transceiver disconnected!"}`;
            }
        }
    }

    // 1. SYSTEM
    else if (topic === "telemetry/system") {
        if (data.type === "heartbeat") {
            updateNodeHeartbeat(data.source, data.state_name || data.state);
        } else if (data.type === "pong") {
            const rtt = Date.now() - pingStartTime;
            const resBox = document.getElementById("pingResultBox");
            resBox.className = "mt-3 p-2 rounded bg-black border border-success text-center small text-success";
            resBox.innerHTML = `<i class="fa-solid fa-check me-1"></i> PONG from 0x${data.source.toString(16).toUpperCase()} | Ping ID: ${data.ping_id} | RTT: ${rtt} ms`;
        } else if (data.type === "node_info") {
            const resBox = document.getElementById("pingResultBox");
            resBox.className = "mt-3 p-2 rounded bg-black border border-info text-start small text-info";
            resBox.innerHTML = `
                <div><strong>Node Info (0x${data.node_id.toString(16).toUpperCase()})</strong></div>
                <div>FW: ${data.fw_version} | Git: <code>${data.git_hash}</code> | Uptime: ${data.uptime_s}s</div>
                <div>Services: ${data.supported_services ? data.supported_services.join(", ") : "None"}</div>
            `;
        } else if (data.type === "subscribe_response") {
            handleSubscribeResponse(data);
        }
    }

    // 2. TRACTION
    else if (topic === "telemetry/traction") {
        if (data.type === "status") {
            document.getElementById("tracSpeedVal").innerText = data.speed_mps !== undefined ? data.speed_mps.toFixed(2) : "--";
            document.getElementById("tracCurrentVal").innerText = data.motor_current_a !== undefined ? data.motor_current_a.toFixed(1) : "--";
            document.getElementById("tracInvTempVal").innerText = data.inverter_temp_c !== undefined ? data.inverter_temp_c.toFixed(1) : "--";
            document.getElementById("tracMotTempVal").innerText = data.motor_temp_c !== undefined ? data.motor_temp_c.toFixed(1) : "--";
        }
    }

    // 3. STEERING
    else if (topic === "telemetry/steering") {
        if (data.type === "status") {
            document.getElementById("strAngleVal").innerText = data.angle_deg !== undefined ? data.angle_deg.toFixed(2) : "--";
            document.getElementById("strYawVal").innerText = data.chassis_yaw_rate_deg_s !== undefined ? data.chassis_yaw_rate_deg_s.toFixed(2) : "--";
            document.getElementById("strCurrentVal").innerText = data.motor_current_a !== undefined ? data.motor_current_a.toFixed(1) : "--";
            document.getElementById("strTempVal").innerText = data.motor_temp_c !== undefined ? data.motor_temp_c.toFixed(1) : "--";
        }
    }

    // 4. BRAKE
    else if (topic === "telemetry/brake") {
        if (data.type === "status") {
            document.getElementById("brkPosVal").innerText = data.position_mm !== undefined ? data.position_mm.toFixed(2) : "--";
            document.getElementById("brkForceVal").innerText = data.actuator_force_n !== undefined ? data.actuator_force_n.toFixed(0) : "--";
            document.getElementById("brkAccelVal").innerText = data.chassis_long_accel_mps2 !== undefined ? data.chassis_long_accel_mps2.toFixed(2) : "--";
            document.getElementById("brkEpbVal").innerText = data.park_brake_state === 1 ? "ENGAGED" : "RELEASED";
        }
    }

    // 5. BMS
    else if (topic.startsWith("telemetry/bms")) {
        const isAux = topic.endsWith("aux");
        const prefix = isAux ? "bmsAux" : "bmsMain";

        if (data.type === "status") {
            document.getElementById(`${prefix}Volt`).innerText = data.pack_voltage_v !== undefined ? data.pack_voltage_v.toFixed(1) : "--";
            document.getElementById(`${prefix}Curr`).innerText = data.pack_current_a !== undefined ? data.pack_current_a.toFixed(1) : "--";
            document.getElementById(`${prefix}Soc`).innerText = data.soc_pct !== undefined ? data.soc_pct.toFixed(1) : "--";
            document.getElementById(`${prefix}MinCell`).innerText = data.min_cell_voltage_v !== undefined ? data.min_cell_voltage_v.toFixed(3) : "--";
            document.getElementById(`${prefix}MaxCell`).innerText = data.max_cell_voltage_v !== undefined ? data.max_cell_voltage_v.toFixed(3) : "--";
            document.getElementById(`${prefix}Temp`).innerText = data.bms_temp_c !== undefined ? data.bms_temp_c.toFixed(1) : "--";
        } else if (data.type === "cell_voltage_item") {
            updateCellVoltageRow(data.cell_index, data.voltage_v);
            document.getElementById("cellStreamStatus").className = "badge bg-warning";
            document.getElementById("cellStreamStatus").innerText = `Streaming Cell #${data.cell_index}...`;
        } else if (data.type === "cell_voltages_complete") {
            document.getElementById("cellStreamStatus").className = "badge bg-success";
            document.getElementById("cellStreamStatus").innerText = `Complete (${data.total_cells} cells streamed)`;
        } else if (data.type === "temperature_item") {
            updateTempRow(data.sensor_index, data.temperature_c);
            document.getElementById("tempStreamStatus").className = "badge bg-warning";
            document.getElementById("tempStreamStatus").innerText = `Streaming Sensor #${data.sensor_index}...`;
        } else if (data.type === "temperatures_complete") {
            document.getElementById("tempStreamStatus").className = "badge bg-success";
            document.getElementById("tempStreamStatus").innerText = `Complete (${data.total_sensors} sensors)`;
        } else if (data.type === "balancing_item") {
            updateBalancingState(data.cell_index, data.balancing);
        }
    }

    // 6. DIAGNOSTIC
    else if (topic === "telemetry/diagnostic") {
        const banner = document.getElementById("faultStreamBanner");
        if (data.type === "fault_item") {
            banner.classList.remove("d-none");
            addFaultRow(data.fault);
        } else if (data.type === "faults_complete") {
            banner.className = "alert alert-success py-2 small";
            banner.innerHTML = `<i class="fa-solid fa-circle-check me-2"></i> Stream complete: Received ${data.total_faults} faults (Terminated by <code>0x0000 END_OF_FAULT_LIST</code>).`;
        } else if (data.type === "clear_faults_response") {
            alert(`CLEAR_FAULTS response: Result=${data.result_name || data.result_code}`);
            document.getElementById("faultsTableBody").innerHTML = '<tr><td colspan="7" class="text-success text-center">Faults cleared successfully.</td></tr>';
        }
    }

    // 7. LIGHTING
    else if (topic === "telemetry/lighting") {
        if (data.type === "status") {
            updateLightingBadge("Headlight", data.headlight, data.headlight_name);
            updateLightingBadge("BrakeLight", data.brake_light, data.brake_light_name);
            updateLightingBadge("TurnLeft", data.turn_left, data.turn_left_name);
            updateLightingBadge("TurnRight", data.turn_right, data.turn_right_name);
        }
    }

    // 8. CONFIG
    else if (topic === "telemetry/config") {
        if (data.type === "parameter_value") {
            if (data.value !== null && data.value !== undefined) {
                document.getElementById("paramValueInput").value = data.value;
                alert(`Read ${data.name}: ${data.value} ${data.unit}`);
            }
        } else if (data.type === "set_parameter_response") {
            alert(`SET Parameter Result: ${data.result_name}`);
        } else if (data.type === "save_parameters_response") {
            alert(`SAVE Parameters Result: ${data.result_name}`);
        }
    }
}

function updateHardwareStatusBadge(data) {
    const badge = document.getElementById("hwStatusBadge");
    if (!badge) return;
    if (data.connected) {
        if (data.mode === "MOCK") {
            badge.className = "badge bg-warning text-dark px-3 py-2 me-2";
            badge.innerHTML = `<i class="fa-solid fa-flask me-1"></i> LoRa: Mock Mode`;
            badge.title = "Operating in simulated mock mode";
        } else {
            badge.className = "badge badge-status-online px-3 py-2 me-2";
            badge.innerHTML = `<i class="fa-solid fa-usb me-1"></i> LoRa USB: Connected`;
            badge.title = `Transceiver connected at ${data.port || "/dev/ttyUSB0"}`;
        }
    } else {
        badge.className = "badge badge-status-offline px-3 py-2 me-2";
        badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-1"></i> LoRa USB: Disconnected`;
        badge.title = data.error || "Device not found on serial port";
    }
}

function updateNodeHeartbeat(nodeId, stateName) {
    const pill = document.getElementById(`pill-node-${nodeId}`);
    const text = document.getElementById(`statustext-node-${nodeId}`);
    const state = document.getElementById(`state-node-${nodeId}`);
    const seen = document.getElementById(`seen-node-${nodeId}`);

    if (pill) pill.className = "status-pill online";
    if (text) text.innerText = "ONLINE";
    if (state) state.innerHTML = `<span class="badge bg-success">${stateName}</span>`;
    if (seen) seen.innerText = new Date().toLocaleTimeString();
}

function updateCellVoltageRow(idx, volt) {
    const tbody = document.getElementById("cellVoltagesTableBody");
    let row = document.getElementById(`cell-row-${idx}`);
    if (!row) {
        if (tbody.children.length === 1 && tbody.children[0].innerText.includes("No cell data")) {
            tbody.innerHTML = "";
        }
        row = document.createElement("tr");
        row.id = `cell-row-${idx}`;
        tbody.appendChild(row);
    }

    const pct = Math.max(0, Math.min(100, ((volt - 2.8) / (4.2 - 2.8)) * 100));
    row.innerHTML = `
        <td class="text-white"><strong>#${idx}</strong></td>
        <td><code class="text-info">${volt.toFixed(3)} V</code></td>
        <td style="width: 40%;">
            <div class="progress" style="height: 10px; background-color: #30363d;">
                <div class="progress-bar bg-info" style="width: ${pct}%;"></div>
            </div>
        </td>
        <td id="cell-bal-${idx}"><span class="badge bg-secondary">--</span></td>
    `;
}

function updateTempRow(idx, temp) {
    const tbody = document.getElementById("tempsTableBody");
    let row = document.getElementById(`temp-row-${idx}`);
    if (!row) {
        if (tbody.children.length === 1 && tbody.children[0].innerText.includes("No temperature")) {
            tbody.innerHTML = "";
        }
        row = document.createElement("tr");
        row.id = `temp-row-${idx}`;
        tbody.appendChild(row);
    }
    const color = temp > 45 ? "danger" : temp > 35 ? "warning" : "success";
    row.innerHTML = `
        <td class="text-white"><strong>Sensor #${idx}</strong></td>
        <td><code class="text-info">${temp.toFixed(1)} °C</code></td>
        <td><span class="badge bg-${color}">${temp > 45 ? "HIGH" : "NORMAL"}</span></td>
    `;
}

function updateBalancingState(idx, isBalancing) {
    const badge = document.getElementById(`cell-bal-${idx}`);
    if (badge) {
        badge.innerHTML = isBalancing
            ? '<span class="badge bg-warning text-dark"><i class="fa-solid fa-bolt me-1"></i>ACTIVE</span>'
            : '<span class="badge bg-secondary">INACTIVE</span>';
    }
}

function addFaultRow(f) {
    const tbody = document.getElementById("faultsTableBody");
    if (tbody.children.length === 1 && tbody.children[0].innerText.includes("No fault records")) {
        tbody.innerHTML = "";
    }
    const sevColor = f.severity === 4 ? "danger" : f.severity === 3 ? "danger" : f.severity === 2 ? "warning" : "info";
    const stateColor = f.state === 1 ? "danger" : f.state === 2 ? "warning" : "secondary";

    const tr = document.createElement("tr");
    tr.innerHTML = `
        <td><code class="text-info fw-bold">${f.fault_code}</code></td>
        <td class="text-white"><strong>${f.name}</strong></td>
        <td class="text-light"><span class="small">${f.description}</span></td>
        <td><span class="badge bg-${sevColor}">${f.severity_name}</span></td>
        <td><span class="badge bg-${stateColor}">${f.state_name}</span></td>
        <td class="text-white font-monospace">${f.occurrence_count}</td>
        <td class="text-white font-monospace">${f.last_occurrence_ms} ms</td>
    `;
    tbody.appendChild(tr);
}

function updateLightingBadge(prefix, stateVal, stateName) {
    const badge = document.getElementById(`badge${prefix}`);
    if (!badge) return;
    badge.innerText = stateName || (stateVal === 1 ? "ON" : "OFF");
    badge.className = stateVal === 1 ? "badge bg-success" : stateVal === 2 ? "badge bg-warning" : "badge bg-secondary";
}

// REST Command API Helper
async function postCommand(payload) {
    try {
        const res = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const json = await res.json();
        return json;
    } catch (e) {
        console.error("Command post failed:", e);
        alert(`Failed to send command: ${e}`);
    }
}

function quickPing(nodeId) {
    pingStartTime = Date.now();
    postCommand({
        destination: nodeId,
        service: 0x00,
        command: 0x08,
        priority: 0x05,
        ack: false,
        params: { ping_id: (Date.now() & 0xFFFFFFFF) },
    });
}

function sendPing() {
    const nid = parseInt(document.getElementById("pingNodeSelect").value);
    quickPing(nid);
}

function sendGetNodeInfo() {
    const nid = parseInt(document.getElementById("pingNodeSelect").value);
    postCommand({
        destination: nid,
        service: 0x00,
        command: 0x06,
        priority: 0x05,
        ack: true,
        params: {},
    });
}

function sendSetState(targetState) {
    const targetSelect = document.getElementById("stateTargetNodeSelect");
    const dest = targetSelect ? parseInt(targetSelect.value) : 0x03;
    postCommand({
        destination: dest,
        service: 0x00,
        command: 0x02,
        ack: true,
        params: { target_state: targetState },
    });
}

function sendSetMode(targetMode) {
    const targetSelect = document.getElementById("stateTargetNodeSelect");
    const dest = targetSelect ? parseInt(targetSelect.value) : 0x03;
    postCommand({
        destination: dest,
        service: 0x00,
        command: 0x04,
        ack: true,
        params: { target_mode: targetMode },
    });
}

function triggerEStop() {
    if (!confirm("Are you sure you want to TRIGGER EMERGENCY STOP?")) return;
    postCommand({
        destination: 0xFF,
        service: 0x00,
        command: 0x05,
        message_class: 0x00, // SAFETY
        priority: 0x00,      // EMERGENCY
        ack: true,
        params: { subcommand: 1 },
    });
}

// Powertrain Actions
function sendSetSpeed() {
    const spd = parseFloat(document.getElementById("targetSpeedInput").value);
    postCommand({
        destination: 0x10,
        service: 0x01,
        command: 0x01,
        ack: false,
        params: { target_speed: spd },
    });
}

function sendSetGear(gear) {
    postCommand({
        destination: 0x10,
        service: 0x01,
        command: 0x04,
        ack: true,
        params: { target_gear: gear },
    });
}

function sendSetAngle() {
    const ang = parseFloat(document.getElementById("targetAngleInput").value);
    postCommand({
        destination: 0x11,
        service: 0x02,
        command: 0x01,
        ack: false,
        params: { target_angle: ang },
    });
}

function sendSetBrakeDemand() {
    const dem = parseFloat(document.getElementById("targetDemandInput").value);
    postCommand({
        destination: 0x12,
        service: 0x03,
        command: 0x01,
        ack: false,
        params: { target_brake_demand: dem },
    });
}

function sendSetParkBrake(state) {
    postCommand({
        destination: 0x12,
        service: 0x03,
        command: 0x05,
        ack: true,
        params: { target_park_brake: state },
    });
}

// BMS Actions
function fetchBmsFull(nodeId) {
    // Request basic status + stream cell voltages, temps, and balancing
    postCommand({ destination: nodeId, service: 0x04, command: 0x01, ack: false });
    postCommand({ destination: nodeId, service: 0x04, command: 0x03, ack: false });
    postCommand({ destination: nodeId, service: 0x04, command: 0x05, ack: false });
    postCommand({ destination: nodeId, service: 0x04, command: 0x07, ack: false });
}

// Diagnostic Actions
function sendGetFaults() {
    const nid = parseInt(document.getElementById("diagNodeSelect").value);
    document.getElementById("faultsTableBody").innerHTML = "";
    const banner = document.getElementById("faultStreamBanner");
    banner.classList.remove("d-none");
    banner.className = "alert alert-secondary py-2 small";
    banner.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i> Requesting faults from Node 0x${nid.toString(16).toUpperCase()}... Waiting for 100 ms stream.`;

    postCommand({
        destination: nid,
        service: 0x06,
        command: 0x02,
        ack: true,
        params: {},
    });
}

function sendClearFaults() {
    const nid = parseInt(document.getElementById("diagNodeSelect").value);
    if (!confirm(`Clear all stored faults on Node 0x${nid.toString(16).toUpperCase()}?`)) return;
    postCommand({
        destination: nid,
        service: 0x06,
        command: 0x03,
        ack: true,
        params: {},
    });
}

// Lighting Actions (Target MUST BE Main STM32 0x03)
function sendLightCmd(lightId, turnOn) {
    postCommand({
        destination: 0x03,
        service: 0x08,
        command: turnOn ? 0x01 : 0x02,
        ack: true,
        params: { light_id: lightId },
    });
}

function sendGetLightingStatus() {
    postCommand({
        destination: 0x03,
        service: 0x08,
        command: 0x03,
        ack: false,
        params: {},
    });
}

// Subscription Engine Actions
function updateSubCommandOptions() {
    if (!registryData) return;
    const srvId = parseInt(document.getElementById("subServiceSelect").value);
    const cmdSelect = document.getElementById("subCommandSelect");
    cmdSelect.innerHTML = "";

    const srvNames = { 0: "SYSTEM", 1: "TRACTION", 2: "STEERING", 3: "BRAKE", 4: "BMS", 8: "LIGHTING" };
    const srvName = srvNames[srvId] || "SYSTEM";
    const cmds = registryData.commands[srvName] || [];

    cmds.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.innerText = `0x${c.id.toString(16).padStart(2, "0").toUpperCase()} - ${c.name}`;
        cmdSelect.appendChild(opt);
    });
}

function setSubInterval(ms) {
    document.getElementById("subIntervalInput").value = ms;
}

function sendSubscribeRequest() {
    const dest = parseInt(document.getElementById("subTargetNode").value);
    const srv = parseInt(document.getElementById("subServiceSelect").value);
    const cmd = parseInt(document.getElementById("subCommandSelect").value);
    const interval = parseInt(document.getElementById("subIntervalInput").value);
    const ttl = parseInt(document.getElementById("subTtlInput").value);

    postCommand({
        destination: dest,
        service: 0x00,
        command: 0x0A,
        ack: true,
        params: {
            target_service: srv,
            target_command: cmd,
            interval_ms: interval,
            lease_ttl_s: ttl,
        },
    });
}

function handleSubscribeResponse(data) {
    alert(`SUBSCRIBE Response: Result=${data.result_name} | Assigned Interval=${data.actual_interval_ms} ms`);
    if (data.result_code === 0) {
        activeSubscriptions.push({
            node: data.source,
            service: data.target_service,
            command: data.target_command,
            interval: data.actual_interval_ms,
        });
        renderSubscriptions();
    }
}

function renderSubscriptions() {
    const tbody = document.getElementById("subscriptionsTableBody");
    if (activeSubscriptions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-secondary text-center">No active subscriptions registered.</td></tr>';
        return;
    }
    tbody.innerHTML = "";
    activeSubscriptions.forEach((sub, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><code>0x${sub.node.toString(16).toUpperCase()}</code></td>
            <td>0x${sub.service.toString(16).toUpperCase()}</td>
            <td>0x${sub.command.toString(16).toUpperCase()}</td>
            <td>${sub.interval === 65535 ? '<span class="badge bg-warning text-dark">On-Change (0xFFFF)</span>' : `${sub.interval} ms`}</td>
            <td>Active</td>
            <td>
                <button class="btn btn-sm btn-outline-danger" onclick="sendUnsubscribe(${sub.node}, ${sub.service}, ${sub.command}, ${idx})">UNSUBSCRIBE</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function sendUnsubscribe(nodeId, serviceId, commandId, listIdx) {
    postCommand({
        destination: nodeId,
        service: 0x00,
        command: 0x0B,
        ack: true,
        params: {
            target_service: serviceId,
            target_command: commandId,
        },
    });
    if (listIdx !== undefined) {
        activeSubscriptions.splice(listIdx, 1);
        renderSubscriptions();
    }
}

// Parameter Configuration Actions
function updateParameterList() {
    if (!registryData) return;
    const srv = parseInt(document.getElementById("paramServiceSelect").value);
    const pSelect = document.getElementById("paramSelect");
    pSelect.innerHTML = "";

    const params = registryData.parameters.filter(p => p.service_id === srv);
    params.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.param_id;
        opt.innerText = `${p.param_id_hex} - ${p.name}`;
        pSelect.appendChild(opt);
    });
    onParameterSelected();
}

function onParameterSelected() {
    if (!registryData) return;
    const srv = parseInt(document.getElementById("paramServiceSelect").value);
    const pid = parseInt(document.getElementById("paramSelect").value);
    const param = registryData.parameters.find(p => p.service_id === srv && p.param_id === pid);

    if (param) {
        document.getElementById("paramDetailName").innerText = `${param.param_id_hex}: ${param.name} (${param.data_type})`;
        document.getElementById("paramDetailDesc").innerText = `${param.description} | Scale: ${param.scale} | Unit: [${param.unit || "-"}] | Bounds: [${param.min_val} to ${param.max_val}]`;
        document.getElementById("paramUnitLabel").innerText = param.unit ? `(${param.unit})` : "";
        document.getElementById("paramValueInput").value = param.default_val || 0;
    }
}

function sendGetParameter() {
    const srv = parseInt(document.getElementById("paramServiceSelect").value);
    const pid = parseInt(document.getElementById("paramSelect").value);
    const dest = srv === 1 ? 0x10 : srv === 2 ? 0x11 : 0x12;

    postCommand({
        destination: dest,
        service: srv,
        command: 0xE0,
        message_class: 0x04, // REQUEST
        ack: true,
        params: { param_id: pid },
    });
}

function sendSetParameter() {
    const srv = parseInt(document.getElementById("paramServiceSelect").value);
    const pid = parseInt(document.getElementById("paramSelect").value);
    const val = parseFloat(document.getElementById("paramValueInput").value);
    const dest = srv === 1 ? 0x10 : srv === 2 ? 0x11 : 0x12;

    postCommand({
        destination: dest,
        service: srv,
        command: 0xE1,
        message_class: 0x06, // CONFIG
        ack: true,
        params: { param_id: pid, value: val },
    });
}

function sendSaveParameters() {
    const srv = parseInt(document.getElementById("paramServiceSelect").value);
    const dest = srv === 1 ? 0x10 : srv === 2 ? 0x11 : 0x12;

    postCommand({
        destination: dest,
        service: srv,
        command: 0xE2,
        message_class: 0x06, // CONFIG
        ack: true,
        params: {},
    });
}

// Log view
function logPacket(topic, data) {
    const box = document.getElementById("logBox");
    if (!box) return;
    const entry = document.createElement("div");
    entry.className = "log-entry";
    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-topic">${topic}</span>: <span class="log-data">${JSON.stringify(data)}</span>`;
    box.appendChild(entry);
    box.scrollTop = box.scrollHeight;
}

function clearLogs() {
    const box = document.getElementById("logBox");
    if (box) box.innerHTML = "";
}

