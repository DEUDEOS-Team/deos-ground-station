"""DEOS Parameter and Fault Registries (v1.1 Master).

Derived from:
- DOC-ICD-DATA-002 v1.1 (Parameter IDs and Data Types)
- DOC-ICD-DIAG-004 v1.2 (Fault Management and Node DTC Registries)
- DOC-ICD-NODE-TRAC-008, STR-009, BRK-010, BMS-012
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .enums import FaultSeverity, NodeId, ServiceId


@dataclass(frozen=True)
class FaultInfo:
    code: int
    name: str
    description: str
    default_severity: FaultSeverity = FaultSeverity.ERROR


@dataclass(frozen=True)
class ParameterInfo:
    param_id: int
    name: str
    data_type: str  # 'uint8', 'uint16', 'int16', 'uint32', 'int32'
    scale: float
    unit: str
    description: str
    default_val: Optional[float] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None


# Common Faults (0x0000 - 0x0014) across all nodes
COMMON_FAULTS: Dict[int, FaultInfo] = {
    0x0000: FaultInfo(0x0000, "END_OF_FAULT_LIST", "Marker indicating end of fault list transmission", FaultSeverity.INFO),
    0x0001: FaultInfo(0x0001, "INTERNAL_SOFTWARE_ERROR", "Internal Software Error / Assertion Failure", FaultSeverity.ERROR),
    0x0002: FaultInfo(0x0002, "WATCHDOG_RESET", "Independent Watchdog Reset Detected", FaultSeverity.CRITICAL),
    0x0003: FaultInfo(0x0003, "INVALID_CONFIGURATION", "Invalid Configuration / CRC Mismatch", FaultSeverity.ERROR),
    0x0004: FaultInfo(0x0004, "COMMUNICATION_TIMEOUT", "Periodic Communication Timeout", FaultSeverity.WARNING),
    0x0005: FaultInfo(0x0005, "RX_BUFFER_OVERFLOW", "RX Buffer or Message Queue Overflow", FaultSeverity.WARNING),
    0x0006: FaultInfo(0x0006, "TX_FAILURE", "TX Hardware Buffer Full / Bus Transmission Failure", FaultSeverity.ERROR),
    0x0007: FaultInfo(0x0007, "PROTOCOL_INVALID_MESSAGE", "Protocol Violation or Malformed Frame", FaultSeverity.WARNING),
    0x0008: FaultInfo(0x0008, "LOCAL_STORAGE_ERROR", "EEPROM / Flash Storage Read/Write Error", FaultSeverity.ERROR),
    0x0010: FaultInfo(0x0010, "SUBSCRIPTION_TABLE_FULL", "Subscription Table Capacity Exceeded (Max 8 slots)", FaultSeverity.WARNING),
    0x0011: FaultInfo(0x0011, "SUBSCRIPTION_BROADCAST_REJECTED", "Subscription Request to Broadcast Address Rejected", FaultSeverity.ERROR),
    0x0012: FaultInfo(0x0012, "SUBSCRIPTION_MALFORMED_PAYLOAD", "Malformed Subscription Request Payload", FaultSeverity.ERROR),
    0x0013: FaultInfo(0x0013, "SUBSCRIPTION_HANDLER_NOT_FOUND", "Target Service or Command Handler Not Found", FaultSeverity.ERROR),
    0x0014: FaultInfo(0x0014, "SUBSCRIPTION_DISPATCH_FAILED", "Failed to Dispatch Subscription Telemetry Frame", FaultSeverity.ERROR),
}

# Node-Specific Fault Registries (0x0100+)
NODE_FAULTS: Dict[Tuple[int, int], FaultInfo] = {
    # Main STM32 (0x03)
    (NodeId.MAIN_STM32, 0x0100): FaultInfo(0x0100, "CANFD_BUS_OFF", "CAN-FD Controller Entered Bus-Off State", FaultSeverity.CRITICAL),
    (NodeId.MAIN_STM32, 0x0101): FaultInfo(0x0101, "ETH_LINK_FAILURE", "Ethernet Physical Link Down", FaultSeverity.ERROR),
    (NodeId.MAIN_STM32, 0x0102): FaultInfo(0x0102, "LORA_COMM_FAILURE", "LoRa UART / Radio Hardware Failure", FaultSeverity.ERROR),
    (NodeId.MAIN_STM32, 0x0103): FaultInfo(0x0103, "ROUTER_QUEUE_OVERFLOW", "Router Internal Message Queue Overflow", FaultSeverity.WARNING),
    (NodeId.MAIN_STM32, 0x0104): FaultInfo(0x0104, "INVALID_UNKNOWN_ROUTE", "Routing Failure / Destination Unreachable", FaultSeverity.WARNING),

    # Traction (0x10)
    (NodeId.TRACTION, 0x0100): FaultInfo(0x0100, "MOTOR_COMM_LOST", "Motor Driver / Inverter Communication Lost", FaultSeverity.CRITICAL),
    (NodeId.TRACTION, 0x0101): FaultInfo(0x0101, "MOTOR_OVERCURRENT", "Traction Motor Phase Overcurrent", FaultSeverity.CRITICAL),
    (NodeId.TRACTION, 0x0102): FaultInfo(0x0102, "MOTOR_OVERTEMP", "Motor / Inverter Thermal Limit Exceeded", FaultSeverity.CRITICAL),
    (NodeId.TRACTION, 0x0103): FaultInfo(0x0103, "SPEED_FEEDBACK_INVALID", "Speed Sensor Encoder Feedback Invalid", FaultSeverity.ERROR),
    (NodeId.TRACTION, 0x0104): FaultInfo(0x0104, "OVERSPEED_DETECTED", "Vehicle Overspeed Safety Limit Exceeded", FaultSeverity.CRITICAL),
    (NodeId.TRACTION, 0x0105): FaultInfo(0x0105, "ACTUATOR_RESPONSE_TIMEOUT", "Motor Inverter Control Response Timeout", FaultSeverity.ERROR),

    # Steering (0x11)
    (NodeId.STEERING, 0x0100): FaultInfo(0x0100, "STEER_ENCODER_COMM_LOST", "Steering Absolute Encoder Communication Lost", FaultSeverity.CRITICAL),
    (NodeId.STEERING, 0x0101): FaultInfo(0x0101, "STEER_POSITION_INVALID", "Steering Position Sensor Reading Out of Validity", FaultSeverity.CRITICAL),
    (NodeId.STEERING, 0x0102): FaultInfo(0x0102, "STEER_ANGLE_OUT_OF_RANGE", "Steering Angle Exceeded Software Stop Limits", FaultSeverity.ERROR),
    (NodeId.STEERING, 0x0103): FaultInfo(0x0103, "STEER_MOTOR_OVERCURRENT", "Steering Actuator Motor Overcurrent", FaultSeverity.CRITICAL),
    (NodeId.STEERING, 0x0104): FaultInfo(0x0104, "STEER_ACTUATOR_STALL", "Steering Actuator Mechanical Stall Detected", FaultSeverity.CRITICAL),
    (NodeId.STEERING, 0x0105): FaultInfo(0x0105, "STEER_RESPONSE_TIMEOUT", "Steering Control Loop Response Timeout", FaultSeverity.ERROR),

    # Brake (0x12)
    (NodeId.BRAKE, 0x0100): FaultInfo(0x0100, "BRAKE_POS_FEEDBACK_INVALID", "Brake Position Sensor Reading Invalid", FaultSeverity.CRITICAL),
    (NodeId.BRAKE, 0x0101): FaultInfo(0x0101, "BRAKE_ACTUATOR_OVERCURRENT", "Brake Linear Actuator Motor Overcurrent", FaultSeverity.CRITICAL),
    (NodeId.BRAKE, 0x0102): FaultInfo(0x0102, "BRAKE_ACTUATOR_STALL", "Brake Actuator Mechanical Stall Detected", FaultSeverity.CRITICAL),
    (NodeId.BRAKE, 0x0103): FaultInfo(0x0103, "BRAKE_POS_OUT_OF_RANGE", "Brake Actuator Position Exceeded Safe Stroke Limits", FaultSeverity.CRITICAL),
    (NodeId.BRAKE, 0x0104): FaultInfo(0x0104, "BRAKE_RESPONSE_TIMEOUT", "Brake Control Response Timeout", FaultSeverity.CRITICAL),

    # BMS Main (0x20)
    (NodeId.BMS_MAIN, 0x0100): FaultInfo(0x0100, "PACK_OVERVOLTAGE", "HV Battery Pack Total Voltage Exceeded Upper Limit", FaultSeverity.CRITICAL),
    (NodeId.BMS_MAIN, 0x0101): FaultInfo(0x0101, "PACK_UNDERVOLTAGE", "HV Battery Pack Total Voltage Below Cutoff Limit", FaultSeverity.CRITICAL),
    (NodeId.BMS_MAIN, 0x0102): FaultInfo(0x0102, "CHARGE_OVERCURRENT", "Battery Pack Charge Overcurrent Exceeded", FaultSeverity.CRITICAL),
    (NodeId.BMS_MAIN, 0x0103): FaultInfo(0x0103, "DISCHARGE_OVERCURRENT", "Battery Pack Discharge Overcurrent Exceeded", FaultSeverity.CRITICAL),
    (NodeId.BMS_MAIN, 0x0104): FaultInfo(0x0104, "OVERTEMPERATURE", "Battery Module Temperature Exceeded Maximum Safe Limit", FaultSeverity.CRITICAL),
    (NodeId.BMS_MAIN, 0x0105): FaultInfo(0x0105, "UNDERTEMPERATURE", "Battery Module Temperature Below Minimum Charge Limit", FaultSeverity.WARNING),
    (NodeId.BMS_MAIN, 0x0106): FaultInfo(0x0106, "CELL_IMBALANCE", "Cell Delta Voltage Exceeded Safe Balancing Margin", FaultSeverity.WARNING),
    (NodeId.BMS_MAIN, 0x0107): FaultInfo(0x0107, "BMS_INTERNAL_FAULT", "BMS Internal AFE / Hardware Error", FaultSeverity.CRITICAL),
    (NodeId.BMS_MAIN, 0x0108): FaultInfo(0x0108, "INVALID_MEASUREMENT", "BMS Voltage/Current Sensor Read Failure", FaultSeverity.ERROR),

    # BMS Aux (0x21)
    (NodeId.BMS_AUX, 0x0100): FaultInfo(0x0100, "PACK_OVERVOLTAGE", "LV Battery Pack Voltage Exceeded Limit", FaultSeverity.CRITICAL),
    (NodeId.BMS_AUX, 0x0101): FaultInfo(0x0101, "PACK_UNDERVOLTAGE", "LV Battery Pack Voltage Below Limit", FaultSeverity.CRITICAL),
    (NodeId.BMS_AUX, 0x0102): FaultInfo(0x0102, "CHARGE_OVERCURRENT", "LV Battery Charge Overcurrent", FaultSeverity.CRITICAL),
    (NodeId.BMS_AUX, 0x0103): FaultInfo(0x0103, "DISCHARGE_OVERCURRENT", "LV Battery Discharge Overcurrent", FaultSeverity.CRITICAL),
    (NodeId.BMS_AUX, 0x0104): FaultInfo(0x0104, "OVERTEMPERATURE", "LV Battery Overtemperature", FaultSeverity.CRITICAL),
    (NodeId.BMS_AUX, 0x0105): FaultInfo(0x0105, "UNDERTEMPERATURE", "LV Battery Undertemperature", FaultSeverity.WARNING),
    (NodeId.BMS_AUX, 0x0106): FaultInfo(0x0106, "CELL_IMBALANCE", "LV Battery Cell Imbalance", FaultSeverity.WARNING),
    (NodeId.BMS_AUX, 0x0107): FaultInfo(0x0107, "BMS_INTERNAL_FAULT", "LV BMS Internal Hardware Error", FaultSeverity.CRITICAL),
    (NodeId.BMS_AUX, 0x0108): FaultInfo(0x0108, "INVALID_MEASUREMENT", "LV BMS Measurement Invalid", FaultSeverity.ERROR),

    # BMS Gateway (0x30)
    (NodeId.BMS_GATEWAY, 0x0100): FaultInfo(0x0100, "BMS_MAIN_COMM_LOST", "Classic CAN Communication to BMS Main Lost", FaultSeverity.CRITICAL),
    (NodeId.BMS_GATEWAY, 0x0101): FaultInfo(0x0101, "BMS_AUX_COMM_LOST", "Classic CAN Communication to BMS Aux Lost", FaultSeverity.ERROR),
    (NodeId.BMS_GATEWAY, 0x0102): FaultInfo(0x0102, "CLASSIC_CAN_BUS_OFF", "Classic CAN Bus Controller Bus-Off", FaultSeverity.CRITICAL),
    (NodeId.BMS_GATEWAY, 0x0103): FaultInfo(0x0103, "CANFD_BUS_OFF", "CAN-FD Bus Controller Bus-Off", FaultSeverity.CRITICAL),
    (NodeId.BMS_GATEWAY, 0x0104): FaultInfo(0x0104, "INVALID_BMS_FRAME", "Malformed or Corrupt Daly BMS Frame", FaultSeverity.WARNING),
    (NodeId.BMS_GATEWAY, 0x0105): FaultInfo(0x0105, "BMS_PROTOCOL_CRC_ERROR", "Daly BMS Checksum Verification Failed", FaultSeverity.WARNING),

    # Ground Control (0x02)
    (NodeId.GROUND_CONTROL, 0x0100): FaultInfo(0x0100, "LORA_COMM_LOST", "LoRa Link Down / No Telemetry Received", FaultSeverity.CRITICAL),
    (NodeId.GROUND_CONTROL, 0x0101): FaultInfo(0x0101, "INVALID_LORA_MESSAGE", "Invalid LoRa / DEOS Frame Header or CRC", FaultSeverity.WARNING),
    (NodeId.GROUND_CONTROL, 0x0102): FaultInfo(0x0102, "TRANSPORT_TIMEOUT", "Transport Layer Ack/Retry Timeout", FaultSeverity.ERROR),
}


def get_fault_info(node_id: int, fault_id: int) -> FaultInfo:
    """Retrieve fault metadata for a given Node and Fault ID."""
    if fault_id in COMMON_FAULTS:
        return COMMON_FAULTS[fault_id]
    key = (node_id, fault_id)
    if key in NODE_FAULTS:
        return NODE_FAULTS[key]
    return FaultInfo(
        code=fault_id,
        name=f"FAULT_{hex(fault_id)}",
        description=f"Node-specific fault {hex(fault_id)} on Node {hex(node_id)}",
        default_severity=FaultSeverity.ERROR,
    )


# ============================================================================
# Parameter Registries (DOC-ICD-DATA-002, TRAC-008, STR-009, BRK-010)
# ============================================================================

PARAMETERS: Dict[Tuple[int, int], ParameterInfo] = {
    # ------------------ TRACTION (Service 0x01) ------------------
    (ServiceId.TRACTION, 0x0001): ParameterInfo(0x0001, "PID_KP", "uint16", 0.01, "", "Speed control proportional gain", 1.0, 0.0, 100.0),
    (ServiceId.TRACTION, 0x0002): ParameterInfo(0x0002, "PID_KI", "uint16", 0.01, "", "Speed control integral gain", 0.1, 0.0, 50.0),
    (ServiceId.TRACTION, 0x0003): ParameterInfo(0x0003, "PID_KD", "uint16", 0.01, "", "Speed control derivative gain", 0.0, 0.0, 50.0),
    (ServiceId.TRACTION, 0x0010): ParameterInfo(0x0010, "MAX_CURRENT", "uint16", 0.1, "A", "Maximum motor phase current", 50.0, 0.0, 150.0),
    (ServiceId.TRACTION, 0x0011): ParameterInfo(0x0011, "MAX_SPEED", "uint16", 0.01, "m/s", "Maximum vehicle speed limit", 15.0, 0.0, 30.0),
    (ServiceId.TRACTION, 0x0012): ParameterInfo(0x0012, "ACCEL_LIMIT", "uint16", 0.01, "m/s²", "Acceleration slew-rate limit", 2.0, 0.1, 5.0),
    (ServiceId.TRACTION, 0x0013): ParameterInfo(0x0013, "CMD_TIMEOUT_MS", "uint16", 1.0, "ms", "Command watchdog timeout", 200.0, 50.0, 2000.0),
    (ServiceId.TRACTION, 0x0014): ParameterInfo(0x0014, "POLE_PAIRS", "uint8", 1.0, "", "Motor magnetic pole pairs", 4.0, 1.0, 16.0),
    (ServiceId.TRACTION, 0x0015): ParameterInfo(0x0015, "GEAR_RATIO", "uint16", 0.01, "", "Drivetrain reduction ratio", 4.5, 1.0, 20.0),
    (ServiceId.TRACTION, 0x0020): ParameterInfo(0x0020, "WHEEL_CIRCUM_MM", "uint16", 1.0, "mm", "Dynamic wheel rolling circumference", 1250.0, 500.0, 3000.0),
    (ServiceId.TRACTION, 0x0022): ParameterInfo(0x0022, "REGEN_CUTOFF_SPD", "uint16", 0.01, "m/s", "Regen braking minimum cutoff speed", 1.0, 0.0, 5.0),

    # ------------------ STEERING (Service 0x02) ------------------
    (ServiceId.STEERING, 0x0001): ParameterInfo(0x0001, "PID_KP", "uint16", 0.01, "", "Steering angle proportional gain", 2.0, 0.0, 100.0),
    (ServiceId.STEERING, 0x0002): ParameterInfo(0x0002, "PID_KI", "uint16", 0.01, "", "Steering angle integral gain", 0.05, 0.0, 50.0),
    (ServiceId.STEERING, 0x0003): ParameterInfo(0x0003, "PID_KD", "uint16", 0.01, "", "Steering angle derivative gain", 0.1, 0.0, 50.0),
    (ServiceId.STEERING, 0x0004): ParameterInfo(0x0004, "PID_I_MAX", "uint16", 0.01, "%", "Integrator anti-windup clamp", 20.0, 0.0, 100.0),
    (ServiceId.STEERING, 0x0005): ParameterInfo(0x0005, "FEEDFORWARD_K", "uint16", 0.01, "", "Angular velocity feedforward gain", 0.5, 0.0, 10.0),
    (ServiceId.STEERING, 0x0006): ParameterInfo(0x0006, "DEADBAND", "uint16", 0.01, "deg", "Center deadband margin", 0.2, 0.0, 2.0),
    (ServiceId.STEERING, 0x0010): ParameterInfo(0x0010, "ZERO_OFFSET", "int16", 0.01, "deg", "Mechanical straight-line zero offset", 0.0, -20.0, 20.0),
    (ServiceId.STEERING, 0x0011): ParameterInfo(0x0011, "MIN_ANGLE", "int16", 0.01, "deg", "Software left turn angle limit", -28.0, -45.0, 0.0),
    (ServiceId.STEERING, 0x0012): ParameterInfo(0x0012, "MAX_ANGLE", "int16", 0.01, "deg", "Software right turn angle limit", 28.0, 0.0, 45.0),
    (ServiceId.STEERING, 0x0013): ParameterInfo(0x0013, "CURRENT_LIMIT", "uint16", 0.1, "A", "Motor electrical current ceiling", 25.0, 1.0, 50.0),
    (ServiceId.STEERING, 0x0014): ParameterInfo(0x0014, "MAX_ANGULAR_VEL", "uint16", 0.01, "deg/s", "Maximum angular rate limit", 90.0, 10.0, 360.0),
    (ServiceId.STEERING, 0x0015): ParameterInfo(0x0015, "MAX_ANGULAR_ACC", "uint16", 0.01, "deg/s²", "Maximum angular acceleration limit", 180.0, 20.0, 720.0),
    (ServiceId.STEERING, 0x0016): ParameterInfo(0x0016, "SOFT_STOP_MARGIN", "uint16", 0.01, "deg", "Soft-stop deceleration margin", 2.0, 0.5, 5.0),
    (ServiceId.STEERING, 0x0017): ParameterInfo(0x0017, "MAX_TRACK_ERR", "uint16", 0.01, "deg", "Maximum tracking error threshold", 3.0, 0.5, 10.0),
    (ServiceId.STEERING, 0x0018): ParameterInfo(0x0018, "TRACK_TIMEOUT_MS", "uint16", 1.0, "ms", "Tracking error fault duration", 500.0, 100.0, 5000.0),

    # ------------------ BRAKE (Service 0x03) ------------------
    (ServiceId.BRAKE, 0x0001): ParameterInfo(0x0001, "PID_KP", "uint16", 0.01, "", "Brake closed-loop proportional gain", 2.5, 0.0, 100.0),
    (ServiceId.BRAKE, 0x0002): ParameterInfo(0x0002, "PID_KI", "uint16", 0.01, "", "Brake closed-loop integral gain", 0.05, 0.0, 50.0),
    (ServiceId.BRAKE, 0x0003): ParameterInfo(0x0003, "PID_KD", "uint16", 0.01, "", "Brake closed-loop derivative gain", 0.2, 0.0, 50.0),
    (ServiceId.BRAKE, 0x0010): ParameterInfo(0x0010, "MIN_POSITION", "uint16", 0.01, "mm", "Caliper fully-open retracted position", 0.0, 0.0, 10.0),
    (ServiceId.BRAKE, 0x0011): ParameterInfo(0x0011, "MAX_POSITION", "uint16", 0.01, "mm", "Maximum caliper mechanical stroke", 25.0, 5.0, 50.0),
    (ServiceId.BRAKE, 0x0012): ParameterInfo(0x0012, "CURRENT_LIMIT", "uint16", 0.1, "A", "Actuator thermal current ceiling", 20.0, 1.0, 40.0),
    (ServiceId.BRAKE, 0x0013): ParameterInfo(0x0013, "SLEW_RATE_LIMIT", "uint16", 0.01, "%/ms", "Actuator application speed limit", 1.0, 0.1, 10.0),
    (ServiceId.BRAKE, 0x0014): ParameterInfo(0x0014, "CMD_TIMEOUT_MS", "uint16", 1.0, "ms", "Watchdog timeout before emergency stop", 200.0, 50.0, 2000.0),
    (ServiceId.BRAKE, 0x0015): ParameterInfo(0x0015, "KISS_POINT_OFFSET", "uint16", 0.01, "mm", "Pad-to-rotor contact zero point", 2.5, 0.0, 10.0),
    (ServiceId.BRAKE, 0x0016): ParameterInfo(0x0016, "MAX_FORCE_LIMIT", "uint16", 1.0, "N", "Actuator peak clamp force limit", 2500.0, 500.0, 5000.0),
}


def get_parameter_info(service_id: int, param_id: int) -> Optional[ParameterInfo]:
    """Retrieve parameter info for a given Service and Parameter ID."""
    return PARAMETERS.get((service_id, param_id))


def list_parameters(service_id: int) -> List[ParameterInfo]:
    """List all registered parameters for a service."""
    return [p for (s, _), p in PARAMETERS.items() if s == service_id]

