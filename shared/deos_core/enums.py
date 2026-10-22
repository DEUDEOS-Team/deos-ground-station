"""DEOS Protocol Enumerations and Constants (v1.1 Master).

Derived from:
- DOC-ICD-CORE-001 (Core Architecture)
- DOC-ICD-DATA-002 (Data Types & Config)
- DOC-ICD-NET-003  (Network Management v1.4)
- DOC-ICD-DIAG-004 (Fault Management v1.2)
- DOC-ICD-TRP-LORA-007 (LoRa Transport)
- DOC-ICD-NODE-TRAC-008 (Traction)
- DOC-ICD-NODE-STR-009 (Steering)
- DOC-ICD-NODE-BRK-010 (Brake)
- DOC-ICD-SRV-LGHT-012 (Lighting v1.2)
- DOC-ICD-NODE-BMS-012 (BMS)
"""

from enum import IntEnum

# Protocol Standard Constants
DEOS_VERSION = 0x11  # Protocol wire version v1.1
LORA_MAGIC = b"\xaa\x55"  # LoRa L2 synchronization magic bytes
END_OF_FAULT_LIST = 0x0000  # Fault ID marker for end of list
END_OF_LIST = 0x00  # Index marker for end of list in BMS
DEOS_INTERVAL_ON_CHANGE = 0xFFFF  # Special interval indicating on-change event subscription


class NodeId(IntEnum):
    """DEOS Logical Node Address Registry (DOC-ICD-CORE-001 Section 4)."""
    INVALID = 0x00
    TEXTUAL = 0x01
    GROUND_CONTROL = 0x02
    MAIN_STM32 = 0x03
    ROS_BRIDGE = 0x04
    TRACTION = 0x10
    STEERING = 0x11
    BRAKE = 0x12
    IMU = 0x13
    BMS_MAIN = 0x20
    BMS_AUX = 0x21
    BMS_GATEWAY = 0x30
    DIAG_TOOL = 0xF0
    CAN_BROADCAST = 0xFE
    GLOBAL_BROADCAST = 0xFF


class Priority(IntEnum):
    """DEOS Priority Registry (DOC-ICD-CORE-001 Section 3)."""
    EMERGENCY = 0x00          # Acil durdurma ve en kritik safety mesajlari (E-Stop)
    CRITICAL_CONTROL = 0x01   # Kritik gercek zamanli kontrol
    CONTROL = 0x02            # Normal surus kontrol mesajlari
    STATUS = 0x03             # Durum ve geri besleme mesajlari
    CONFIG = 0x04             # Konfigurasyon ve kalibrasyon
    NETWORK = 0x05            # Network management / heartbeat / ping-pong / abonelik
    LOW = 0x06                # Dusuk oncelikli servis trafigi
    BACKGROUND = 0x07         # Arka plan / gelistirme trafigi


class MessageClass(IntEnum):
    """DEOS Message Class Registry (DOC-ICD-CORE-001 Section 5)."""
    SAFETY = 0x00
    COMMAND = 0x01
    STATUS = 0x02
    EVENT = 0x03
    REQUEST = 0x04
    RESPONSE = 0x05
    CONFIG = 0x06
    NETWORK = 0x07


class ServiceId(IntEnum):
    """DEOS Functional Service Registry (DOC-ICD-CORE-001 Section 6)."""
    SYSTEM = 0x00
    TRACTION = 0x01
    STEERING = 0x02
    BRAKE = 0x03
    BMS = 0x04
    CALIBRATION = 0x05
    DIAGNOSTIC = 0x06
    SENSORS = 0x07
    LIGHTING = 0x08


class State(IntEnum):
    """DEOS Vehicle and Node State Registry (DOC-ICD-CORE-001 Section 11.1)."""
    INIT = 0x00
    STANDBY = 0x01
    READY = 0x02
    ACTIVE = 0x03
    CALIBRATING = 0x04
    SAFE = 0x05
    FAULT = 0x06
    UNKNOWN = 0xFF


class Mode(IntEnum):
    """DEOS Vehicle and Node Control Mode Registry (DOC-ICD-CORE-001 Section 11.2)."""
    NORMAL = 0x00
    MANUAL = 0x01
    AUTONOMOUS = 0x02
    SERVICE = 0x03
    TEST = 0x04
    UNKNOWN = 0xFF


class ResultCode(IntEnum):
    """DEOS Generic Result Code (DOC-ICD-CORE-001 Section 12)."""
    SUCCESS = 0x00
    UNSUPPORTED = 0x01
    INVALID_PARAMETER = 0x02
    OUT_OF_RANGE = 0x03
    NOT_ALLOWED = 0x04
    BUSY = 0x05
    NOT_READY = 0x06
    INTERNAL_ERROR = 0x07


class SystemCommand(IntEnum):
    """SYSTEM Service Command Registry (DOC-ICD-NET-003 v1.4)."""
    GET_STATE = 0x01
    SET_STATE = 0x02
    GET_MODE = 0x03
    SET_MODE = 0x04
    RESET_NODE = 0x05
    GET_NODE_INFO = 0x06
    HEARTBEAT = 0x07
    PING = 0x08
    PONG = 0x09
    SUBSCRIBE = 0x0A
    UNSUBSCRIBE = 0x0B
    GET_SUBSCRIPTIONS = 0x0C


class TractionCommand(IntEnum):
    """TRACTION Service Command Registry (DOC-ICD-NODE-TRAC-008)."""
    SET_SPEED = 0x01
    GET_STATUS = 0x02
    STATUS = 0x02
    SET_GEAR = 0x04
    SET_TORQUE = 0x05


class SteeringCommand(IntEnum):
    """STEERING Service Command Registry (DOC-ICD-NODE-STR-009)."""
    SET_TARGET_ANGLE = 0x01
    GET_STATUS = 0x02
    STATUS = 0x02
    SET_CONTROL_MODE = 0x04


class BrakeCommand(IntEnum):
    """BRAKE Service Command Registry (DOC-ICD-NODE-BRK-010)."""
    SET_DEMAND = 0x01
    GET_STATUS = 0x02
    STATUS = 0x02
    SET_DECELERATION = 0x03
    SET_CONTROL_MODE = 0x04
    SET_PARK_BRAKE = 0x05
    SET_PREFILL = 0x06


class BmsCommand(IntEnum):
    """BMS Service Command Registry (DOC-ICD-NODE-BMS-012)."""
    GET_STATUS = 0x01
    STATUS = 0x02
    GET_CELL_VOLTAGES = 0x03
    CELL_VOLTAGE = 0x04
    GET_TEMPERATURES = 0x05
    TEMPERATURE = 0x06
    GET_BALANCING = 0x07
    BALANCING = 0x08


class DiagnosticCommand(IntEnum):
    """DIAGNOSTIC Service Command Registry (DOC-ICD-DIAG-004 v1.2)."""
    GET_HEALTH = 0x01
    GET_FAULTS = 0x02
    CLEAR_FAULTS = 0x03


class LightingCommand(IntEnum):
    """LIGHTING Service Command Registry (DOC-ICD-SRV-LGHT-012 v1.2)."""
    TURN_ON = 0x01
    TURN_OFF = 0x02
    GET_STATUS = 0x03
    STATUS = 0x04


class ConfigCommand(IntEnum):
    """Generic Configuration Command Registry (DOC-ICD-DATA-002 v1.1)."""
    GET_PARAMETER = 0xE0
    SET_PARAMETER = 0xE1
    SAVE_PARAMETERS = 0xE2
    RESTORE_DEFAULTS = 0xE3
    GET_PARAMETER_INFO = 0xE4


class LightId(IntEnum):
    """Lighting Light ID Registry (DOC-ICD-SRV-LGHT-012)."""
    HEADLIGHT = 0x01
    BRAKE = 0x02
    TURN_LEFT = 0x03
    TURN_RIGHT = 0x04
    ALL = 0xFF


class LightState(IntEnum):
    """Lighting State Registry (DOC-ICD-SRV-LGHT-012)."""
    OFF = 0x00
    ON = 0x01
    BLINKING = 0x02
    FAULT = 0x03


class LoraFlag(IntEnum):
    """LoRa L2 Envelope Flags (DOC-ICD-TRP-LORA-007)."""
    NONE = 0x00       # Normal paket, ACK beklenmez
    ACK_REQ = 0x01    # Kritik paket, alicidan kesinlikle ACK beklenir
    IS_ACK = 0x02     # Alindi onay (ACK) paketi


class FaultSeverity(IntEnum):
    """Fault Severity Levels (DOC-ICD-DIAG-004)."""
    INFO = 0x01
    WARNING = 0x02
    ERROR = 0x03
    CRITICAL = 0x04


class FaultState(IntEnum):
    """Fault State (DOC-ICD-DIAG-004)."""
    INACTIVE = 0x00
    ACTIVE = 0x01
    LATCHED = 0x02


class CommonFaultId(IntEnum):
    """DEOS Common Fault Registry (0x0000 - 0x00A2)."""
    END_OF_LIST = 0x0000

    # Sistem & Donanım Hataları (0x0001 - 0x000F)
    INTERNAL_SOFTWARE_ERROR = 0x0001
    WATCHDOG_RESET = 0x0002
    INVALID_CONFIGURATION = 0x0003
    COMMUNICATION_TIMEOUT = 0x0004
    LOCAL_STORAGE_ERROR = 0x0005
    ESTOP_TRIGGERED = 0x0006
    MEMORY_ALLOCATION_FAILED = 0x0007

    # Telemetri & Abonelik Hataları (0x0010 - 0x001F)
    SUB_TABLE_FULL = 0x0010
    SUB_BROADCAST_REJECTED = 0x0011
    SUB_MALFORMED_PAYLOAD = 0x0012
    SUB_HANDLER_NOT_FOUND = 0x0013
    SUB_DISPATCH_FAILED = 0x0014

    # Yönlendirici (Router) Hataları (0x0020 - 0x002F)
    ROUTER_NO_POLICY = 0x0020
    ROUTER_UNMAPPED_ROUTE = 0x0021
    ROUTER_TRP_UNAVAILABLE = 0x0022
    ROUTER_LOOPBACK_DETECTED = 0x0023
    ROUTER_QUEUE_FULL = 0x0024

    # Protokol & Çerçeve Hataları (0x0030 - 0x003F)
    PROTOCOL_VERSION_MISMATCH = 0x0030
    FRAME_HEADER_TOO_SHORT = 0x0031
    PAYLOAD_TOO_LARGE = 0x0032
    FRAME_CRC_MISMATCH = 0x0033
    FRAME_DECODE_FAILED = 0x0034

    # CAN / CAN-FD Taşıyıcı Hataları (0x0040 - 0x005F)
    CAN_DEV_NOT_READY = 0x0040
    CAN_MODE_NOT_SUPPORTED = 0x0041
    CAN_FILTER_INSTALL_FAILED = 0x0042
    CAN_RX_QUEUE_FULL = 0x0043
    CAN_TX_QUEUE_FULL = 0x0044
    CAN_TX_SEND_FAILED = 0x0045
    CAN_FRAME_DECODE_ERR = 0x0046
    CAN_BUS_OFF = 0x0047

    # UART / LoRa Taşıyıcı Hataları (0x0060 - 0x007F)
    LORA_DEV_NOT_READY = 0x0060
    LORA_TX_QUEUE_FULL = 0x0061
    LORA_RX_BUFFER_OVERFLOW = 0x0062
    LORA_CRC_MISMATCH = 0x0063
    LORA_FRAME_MALFORMED = 0x0064
    LORA_ACK_TIMEOUT = 0x0065

    # Ethernet / Network Taşıyıcı Hataları (0x0080 - 0x009F)
    ETH_LINK_DOWN = 0x0080
    ETH_SOCKET_CREATE_FAILED = 0x0081
    ETH_SOCKET_BIND_FAILED = 0x0082
    ETH_TX_QUEUE_FULL = 0x0083
    ETH_TX_SEND_FAILED = 0x0084
    ETH_CLIENT_DISCONNECTED = 0x0085
    ETH_FRAME_DECODE_ERR = 0x0086

    # Dağıtıcı (Dispatcher) Hataları (0x00A0 - 0x00AF)
    DISPATCH_TABLE_FULL = 0x00A0
    DISPATCH_DUPLICATE_HANDLER = 0x00A1
    DISPATCH_HANDLER_NOT_FOUND = 0x00A2


class Gear(IntEnum):
    """Traction Gear Selection (DOC-ICD-NODE-TRAC-008)."""
    NEUTRAL = 0
    DRIVE = 1
    REVERSE = 2
    PARK = 3


class ParkBrakeState(IntEnum):
    """Brake Park Brake State (DOC-ICD-NODE-BRK-010)."""
    RELEASED = 0
    ENGAGED = 1

