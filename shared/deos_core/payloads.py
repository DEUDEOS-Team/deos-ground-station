"""Packed Little-Endian C-struct payload definitions mirroring `deos_types.h`.

Every struct subclasses `PackedPayload(ctypes.LittleEndianStructure)` with
`_pack_ = 1` so wire layouts match GCC `__attribute__((packed))` structs in
`deos-protocol/include/deos/deos_types.h` byte-for-byte.
"""

import ctypes
import struct
from typing import Optional, Tuple, Type, TypeVar, Union

from .c_bridge import (
    get_i16_le,
    get_i32_le,
    get_u16_le,
    get_u32_le,
    put_i16_le,
    put_i32_le,
    put_u16_le,
    put_u32_le,
)

_TPayload = TypeVar("_TPayload", bound="PackedPayload")


class PackedPayload(ctypes.LittleEndianStructure):
    """Base packed Little-Endian payload struct matching C `__attribute__((packed))`."""

    _pack_ = 1

    def to_bytes(self) -> bytes:
        """Serialize struct to wire-ready Little-Endian bytes."""
        return bytes(self)

    @classmethod
    def byte_size(cls) -> int:
        """Return exact packed byte size matching C `sizeof(struct ...)`."""
        return ctypes.sizeof(cls)

    @classmethod
    def from_bytes(cls: Type[_TPayload], data: Union[bytes, bytearray, memoryview]) -> _TPayload:
        """Deserialize leading `sizeof(cls)` bytes into a new struct instance."""
        raw = bytes(data)
        expected = ctypes.sizeof(cls)
        if len(raw) < expected:
            raise ValueError(
                f"{cls.__name__} requires at least {expected} bytes, got {len(raw)}"
            )
        return cls.from_buffer_copy(raw[:expected])


# ============================================================================
# SYSTEM Payloads (0x00)
# ============================================================================

class HeartbeatPayload(PackedPayload):
    """`struct deos_heartbeat_payload` (1 Byte)."""

    _fields_ = [("current_state", ctypes.c_uint8)]


class SubscribeReqPayload(PackedPayload):
    """`struct deos_subscribe_req_payload` (6 Bytes)."""

    _fields_ = [
        ("target_service", ctypes.c_uint8),
        ("target_command", ctypes.c_uint8),
        ("interval_ms", ctypes.c_uint16),
        ("lease_ttl_s", ctypes.c_uint16),
    ]


class SubscribeRespPayload(PackedPayload):
    """`struct deos_subscribe_resp_payload` (5 Bytes)."""

    _fields_ = [
        ("result_code", ctypes.c_uint8),
        ("target_service", ctypes.c_uint8),
        ("target_command", ctypes.c_uint8),
        ("actual_interval_ms", ctypes.c_uint16),
    ]


class UnsubscribeReqPayload(PackedPayload):
    """`struct deos_unsubscribe_req_payload` (2 Bytes)."""

    _fields_ = [
        ("target_service", ctypes.c_uint8),
        ("target_command", ctypes.c_uint8),
    ]


class NodeInfoPayload(PackedPayload):
    """`struct deos_node_info_payload` (20 Bytes)."""

    _fields_ = [
        ("result_code", ctypes.c_uint8),
        ("node_id", ctypes.c_uint8),
        ("hw_type", ctypes.c_uint8),
        ("proto_version", ctypes.c_uint8),
        ("fw_version_major", ctypes.c_uint8),
        ("fw_version_minor", ctypes.c_uint8),
        ("fw_version_patch", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8),
        ("git_hash", ctypes.c_uint32),
        ("supported_services", ctypes.c_uint32),
        ("uptime_s", ctypes.c_uint32),
    ]


class SystemStatePayload(PackedPayload):
    """Scalar 1-byte SYSTEM state payload (`SET_STATE` / `GET_STATE` response)."""

    _fields_ = [("state", ctypes.c_uint8)]


class SystemModePayload(PackedPayload):
    """Scalar 1-byte SYSTEM mode payload (`SET_MODE` / `GET_MODE` response)."""

    _fields_ = [("mode", ctypes.c_uint8)]


class ResetNodePayload(PackedPayload):
    """Scalar 1-byte SYSTEM `RESET_NODE` subcommand payload."""

    _fields_ = [("subcommand", ctypes.c_uint8)]


class PingPongPayload(PackedPayload):
    """4-byte `PING` / `PONG` `ping_id` payload."""

    _fields_ = [("ping_id", ctypes.c_uint32)]


# ============================================================================
# TRACTION Payloads (0x01)
# ============================================================================

class TractionTargetPayload(PackedPayload):
    """`struct deos_traction_target_payload` (4 Bytes)."""

    _fields_ = [
        ("target_speed", ctypes.c_uint16),
        ("target_accel", ctypes.c_int16),
    ]


class TractionGearPayload(PackedPayload):
    """`struct deos_traction_gear_payload` (1 Byte)."""

    _fields_ = [("gear", ctypes.c_uint8)]


class TractionTorqueLimitPayload(PackedPayload):
    """`struct deos_traction_torque_limit_payload` (2 Bytes)."""

    _fields_ = [("torque_limit", ctypes.c_uint16)]


class TractionStatusPayload(PackedPayload):
    """`struct deos_traction_status_payload` (10 Bytes)."""

    _fields_ = [
        ("current_speed", ctypes.c_uint16),
        ("motor_current", ctypes.c_uint16),
        ("inverter_temp", ctypes.c_int16),
        ("motor_temp", ctypes.c_int16),
        ("current_gear", ctypes.c_uint8),
        ("wheel_slip_state", ctypes.c_uint8),
    ]


# ============================================================================
# STEERING Payloads (0x02)
# ============================================================================

class SteeringTargetPayload(PackedPayload):
    """`struct deos_steering_target_payload` (4 Bytes)."""

    _fields_ = [
        ("target_angle", ctypes.c_int16),
        ("target_angular_velocity", ctypes.c_uint16),
    ]


class SteeringModePayload(PackedPayload):
    """`struct deos_steering_mode_payload` (1 Byte)."""

    _fields_ = [("mode", ctypes.c_uint8)]


class SteeringStatusPayload(PackedPayload):
    """`struct deos_steering_status_payload` (9 Bytes)."""

    _fields_ = [
        ("current_angle", ctypes.c_int16),
        ("motor_current", ctypes.c_uint16),
        ("motor_temp", ctypes.c_int16),
        ("chassis_yaw_rate", ctypes.c_int16),
        ("is_tracking_target", ctypes.c_uint8),
    ]


# ============================================================================
# BRAKE Payloads (0x03)
# ============================================================================

class BrakeTargetPayload(PackedPayload):
    """`struct deos_brake_target_payload` (4 Bytes)."""

    _fields_ = [
        ("target_brake_demand", ctypes.c_uint16),
        ("target_deceleration", ctypes.c_int16),
    ]


class BrakeModePayload(PackedPayload):
    """`struct deos_brake_mode_payload` (1 Byte)."""

    _fields_ = [("mode", ctypes.c_uint8)]


class BrakeParkPayload(PackedPayload):
    """`struct deos_brake_park_payload` (1 Byte)."""

    _fields_ = [("target_park_brake", ctypes.c_uint8)]


class BrakePrefillPayload(PackedPayload):
    """`struct deos_brake_prefill_payload` (1 Byte)."""

    _fields_ = [("prefill_cmd", ctypes.c_uint8)]


class BrakeStatusPayload(PackedPayload):
    """`struct deos_brake_status_payload` (10 Bytes)."""

    _fields_ = [
        ("current_position", ctypes.c_uint16),
        ("actuator_force", ctypes.c_uint16),
        ("motor_current", ctypes.c_uint16),
        ("chassis_longitudinal_accel", ctypes.c_int16),
        ("brake_system_active", ctypes.c_uint8),
        ("park_brake_state", ctypes.c_uint8),
    ]


# ============================================================================
# BMS Payloads (0x04)
# ============================================================================

class BmsStatusPayload(PackedPayload):
    """`struct deos_bms_status_payload` (16 Bytes)."""

    _fields_ = [
        ("pack_voltage", ctypes.c_uint16),
        ("pack_current", ctypes.c_int16),
        ("state_of_charge", ctypes.c_uint16),
        ("bms_temperature", ctypes.c_int16),
        ("minimum_cell_voltage", ctypes.c_uint16),
        ("maximum_cell_voltage", ctypes.c_uint16),
        ("nominal_pack_voltage", ctypes.c_uint16),
        ("cell_count", ctypes.c_uint8),
        ("temperature_sensor_count", ctypes.c_uint8),
    ]


class BmsCellVoltagePayload(PackedPayload):
    """`struct deos_bms_cell_voltage_payload` (3 Bytes)."""

    _fields_ = [
        ("cell_index", ctypes.c_uint8),
        ("cell_voltage", ctypes.c_uint16),
    ]


class BmsTemperaturePayload(PackedPayload):
    """`struct deos_bms_temperature_payload` (3 Bytes)."""

    _fields_ = [
        ("sensor_index", ctypes.c_uint8),
        ("temperature", ctypes.c_int16),
    ]


class BmsBalancingPayload(PackedPayload):
    """`struct deos_bms_balancing_payload` (2 Bytes)."""

    _fields_ = [
        ("cell_index", ctypes.c_uint8),
        ("balancing_state", ctypes.c_uint8),
    ]


# ============================================================================
# DIAGNOSTIC Payloads (0x06)
# ============================================================================

class DiagnosticFaultPayload(PackedPayload):
    """`struct deos_diagnostic_fault_payload` (10 Bytes)."""

    _fields_ = [
        ("fault_id", ctypes.c_uint16),
        ("severity", ctypes.c_uint8),
        ("state", ctypes.c_uint8),
        ("occurrence_count", ctypes.c_uint16),
        ("last_occurrence_time", ctypes.c_uint32),
    ]


# ============================================================================
# SENSORS Payloads (0x07)
# ============================================================================

class SensorImuPayload(PackedPayload):
    """`struct deos_sensor_imu_payload` (18 Bytes)."""

    _fields_ = [
        ("accel_x", ctypes.c_int16),
        ("accel_y", ctypes.c_int16),
        ("accel_z", ctypes.c_int16),
        ("gyro_x", ctypes.c_int16),
        ("gyro_y", ctypes.c_int16),
        ("gyro_z", ctypes.c_int16),
        ("mag_x", ctypes.c_int16),
        ("mag_y", ctypes.c_int16),
        ("mag_z", ctypes.c_int16),
    ]


# ============================================================================
# LIGHTING Payloads (0x08)
# ============================================================================

class LightingCommandPayload(PackedPayload):
    """1-byte LIGHTING command payload (`TURN_ON` / `TURN_OFF` / `GET_STATUS`)."""

    _fields_ = [("light_id", ctypes.c_uint8)]


class LightingStatusPayload(PackedPayload):
    """`struct deos_lighting_status_payload` (6 Bytes)."""

    _fields_ = [
        ("headlight_state", ctypes.c_uint8),
        ("brake_light_state", ctypes.c_uint8),
        ("turn_left_state", ctypes.c_uint8),
        ("turn_right_state", ctypes.c_uint8),
        ("hazard_state", ctypes.c_uint8),
        ("fault_flags", ctypes.c_uint8),
    ]


# ============================================================================
# PARAMETER Payloads (0xE0..0xE4 - Flexible Array Member)
# ============================================================================

class ParameterHeaderPayload(PackedPayload):
    """Header prefix for `struct deos_parameter_payload` (2 Bytes)."""

    _fields_ = [("parameter_id", ctypes.c_uint16)]


def pack_parameter_payload(param_id: int, data_type: str, raw_value: int) -> bytes:
    """Pack `[parameter_id (u16 LE)] + [raw_value]` for `SET_PARAMETER`."""
    header = put_u16_le(param_id)
    if data_type == "uint8":
        if not (0 <= raw_value <= 0xFF):
            raise ValueError(f"uint8 out of range (0..255): {raw_value}")
        return header + bytes([raw_value])
    if data_type == "int8":
        if not (-128 <= raw_value <= 127):
            raise ValueError(f"int8 out of range (-128..127): {raw_value}")
        return header + struct.pack("<b", raw_value)
    if data_type == "uint16":
        return header + put_u16_le(raw_value)
    if data_type == "int16":
        return header + put_i16_le(raw_value)
    if data_type == "uint32":
        return header + put_u32_le(raw_value)
    if data_type == "int32":
        return header + put_i32_le(raw_value)
    raise ValueError(f"Unsupported parameter data_type: {data_type}")


def unpack_parameter_payload(
    data: Union[bytes, bytearray, memoryview],
    data_type: str = "uint16",
) -> Tuple[int, Optional[int]]:
    """Unpack `[parameter_id (u16 LE)] + optional [raw_value]` via C codec helpers."""
    raw = bytes(data)
    if len(raw) < 2:
        raise ValueError(f"Parameter payload too short: {len(raw)} < 2 bytes")

    param_id = get_u16_le(raw, offset=0)
    val_data = raw[2:]
    if not val_data:
        return param_id, None

    if data_type == "uint8":
        return param_id, val_data[0]
    if data_type == "int8":
        return param_id, struct.unpack("<b", val_data[:1])[0]
    if data_type == "uint16":
        return param_id, get_u16_le(val_data)
    if data_type == "int16":
        return param_id, get_i16_le(val_data)
    if data_type == "uint32":
        return param_id, get_u32_le(val_data)
    if data_type == "int32":
        return param_id, get_i32_le(val_data)
    raise ValueError(f"Unsupported parameter data_type: {data_type}")
