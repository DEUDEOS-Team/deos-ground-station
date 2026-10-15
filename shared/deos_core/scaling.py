"""DEOS Signal Scaling and Unit Conversion Utilities (DOC-ICD-DATA-002 v1.1).

Linear conversion:
    PhysicalValue = RawValue * Scale + Offset
    RawValue = round((PhysicalValue - Offset) / Scale)
"""

from dataclasses import dataclass
from typing import Dict, Union


@dataclass(frozen=True)
class SignalSpec:
    name: str
    scale: float
    offset: float
    unit: str
    description: str


def to_physical(raw: Union[int, float], scale: float, offset: float = 0.0, decimals: int = 4) -> float:
    """Convert raw integer wire value to physical engineering value."""
    val = (raw * scale) + offset
    return round(val, decimals)


def to_raw(physical: float, scale: float, offset: float = 0.0) -> int:
    """Convert physical engineering value back to integer wire value."""
    if scale == 0:
        return 0
    return int(round((physical - offset) / scale))


# Common Signal Specifications
SIGNALS: Dict[str, SignalSpec] = {
    # Traction
    "traction_speed": SignalSpec("speed", 0.01, 0.0, "m/s", "Vehicle speed"),
    "traction_motor_current": SignalSpec("motor_current", 0.1, 0.0, "A", "Motor current"),
    "traction_inverter_temp": SignalSpec("inverter_temp", 0.1, 0.0, "°C", "Inverter temperature"),
    "traction_motor_temp": SignalSpec("motor_temp", 0.1, 0.0, "°C", "Motor temperature"),
    "traction_torque": SignalSpec("torque", 0.01, 0.0, "%", "Torque demand / limit"),
    "traction_accel": SignalSpec("accel", 0.01, 0.0, "m/s²", "Acceleration"),

    # Steering
    "steering_angle": SignalSpec("angle", 0.01, 0.0, "deg", "Steering wheel angle"),
    "steering_motor_current": SignalSpec("motor_current", 0.1, 0.0, "A", "Steering motor current"),
    "steering_motor_temp": SignalSpec("motor_temp", 0.1, 0.0, "°C", "Steering motor temperature"),
    "steering_yaw_rate": SignalSpec("yaw_rate", 0.01, 0.0, "deg/s", "Chassis yaw rate"),
    "steering_angular_velocity": SignalSpec("angular_velocity", 0.01, 0.0, "deg/s", "Angular velocity"),

    # Brake
    "brake_position": SignalSpec("position", 0.01, 0.0, "mm", "Brake actuator position"),
    "brake_actuator_force": SignalSpec("force", 1.0, 0.0, "N", "Brake actuator force"),
    "brake_motor_current": SignalSpec("motor_current", 0.1, 0.0, "A", "Brake motor current"),
    "brake_long_accel": SignalSpec("long_accel", 0.01, 0.0, "m/s²", "Chassis longitudinal acceleration"),
    "brake_demand": SignalSpec("demand", 0.01, 0.0, "%", "Brake demand percentage"),
    "brake_deceleration": SignalSpec("deceleration", 0.01, 0.0, "m/s²", "Target deceleration"),

    # BMS
    "bms_pack_voltage": SignalSpec("pack_voltage", 0.01, 0.0, "V", "BMS Pack total voltage"),
    "bms_pack_current": SignalSpec("pack_current", 0.1, 0.0, "A", "BMS Pack current"),
    "bms_soc": SignalSpec("soc", 0.01, 0.0, "%", "State of Charge"),
    "bms_temp": SignalSpec("bms_temp", 0.1, 0.0, "°C", "BMS temperature"),
    "bms_cell_voltage": SignalSpec("cell_voltage", 0.001, 0.0, "V", "Individual cell voltage"),
    "bms_sensor_temp": SignalSpec("sensor_temp", 0.1, 0.0, "°C", "Battery module temperature sensor"),
}
