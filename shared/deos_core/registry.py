"""DEOS Parameter and Fault Registries (v1.1 Master).

Derived from:
- DOC-ICD-DATA-002 v1.1 (Parameter IDs and Data Types)
- DOC-ICD-DIAG-004 v1.2 (Fault Management and Node DTC Registries)
- DOC-ICD-NODE-TRAC-008, STR-009, BRK-010, BMS-012
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .enums import CommonFaultId, FaultSeverity, NodeId, ServiceId


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


# Common Faults (0x0000 - 0x00AF) across all nodes (DOC-ICD-DIAG-004)
COMMON_FAULTS: Dict[int, FaultInfo] = {
    CommonFaultId.END_OF_LIST: FaultInfo(0x0000, "END_OF_FAULT_LIST", "Arıza Listesi Sonu (Aktif arıza taraması tamamlandı)", FaultSeverity.INFO),

    # Sistem & Donanım Hataları (0x0001 - 0x000F)
    CommonFaultId.INTERNAL_SOFTWARE_ERROR: FaultInfo(0x0001, "INTERNAL_SOFTWARE_ERROR", "Dahili Yazılım Hatası / Assertion Failure", FaultSeverity.ERROR),
    CommonFaultId.WATCHDOG_RESET: FaultInfo(0x0002, "WATCHDOG_RESET", "Bağımsız Watchdog (IWDG) Reset Algılandı", FaultSeverity.CRITICAL),
    CommonFaultId.INVALID_CONFIGURATION: FaultInfo(0x0003, "INVALID_CONFIGURATION", "Geçersiz Konfigürasyon / Parametre CRC Hatası", FaultSeverity.ERROR),
    CommonFaultId.COMMUNICATION_TIMEOUT: FaultInfo(0x0004, "COMMUNICATION_TIMEOUT", "Periyodik İletişim Zaman Aşımı (Heartbeat/Keepalive Kaybı)", FaultSeverity.WARNING),
    CommonFaultId.LOCAL_STORAGE_ERROR: FaultInfo(0x0005, "LOCAL_STORAGE_ERROR", "Dahili Depolama / Flash / EEPROM Okuma/Yazma Hatası", FaultSeverity.ERROR),
    CommonFaultId.ESTOP_TRIGGERED: FaultInfo(0x0006, "ESTOP_TRIGGERED", "Acil Durdurma (E-Stop) Tetiklendi", FaultSeverity.CRITICAL),
    CommonFaultId.MEMORY_ALLOCATION_FAILED: FaultInfo(0x0007, "MEMORY_ALLOCATION_FAILED", "Dinamik Bellek Ayırma Başarısız (Heap/Pool Exhausted)", FaultSeverity.CRITICAL),

    # Telemetri & Abonelik Hataları (0x0010 - 0x001F)
    CommonFaultId.SUB_TABLE_FULL: FaultInfo(0x0010, "SUB_TABLE_FULL", "Abonelik Tablosu Dolu (Maksimum slot aşıldı)", FaultSeverity.WARNING),
    CommonFaultId.SUB_BROADCAST_REJECTED: FaultInfo(0x0011, "SUB_BROADCAST_REJECTED", "Broadcast Adresine Abonelik Reddedildi (Unicast Zorunlu)", FaultSeverity.ERROR),
    CommonFaultId.SUB_MALFORMED_PAYLOAD: FaultInfo(0x0012, "SUB_MALFORMED_PAYLOAD", "Bozuk Abonelik İstek Veri Yükü (Malformed Payload)", FaultSeverity.ERROR),
    CommonFaultId.SUB_HANDLER_NOT_FOUND: FaultInfo(0x0013, "SUB_HANDLER_NOT_FOUND", "Abonelik Hedef Servis veya Komut Handler Bulunamadı", FaultSeverity.ERROR),
    CommonFaultId.SUB_DISPATCH_FAILED: FaultInfo(0x0014, "SUB_DISPATCH_FAILED", "Abonelik Telemetri Çerçevesi Dağıtılamadı", FaultSeverity.ERROR),

    # Yönlendirici (Router) Hataları (0x0020 - 0x002F)
    CommonFaultId.ROUTER_NO_POLICY: FaultInfo(0x0020, "ROUTER_NO_POLICY", "Rota Politikası Fonksiyonu Atanmamış", FaultSeverity.ERROR),
    CommonFaultId.ROUTER_UNMAPPED_ROUTE: FaultInfo(0x0021, "ROUTER_UNMAPPED_ROUTE", "Hedef Düğüm Rota Tablosunda Yok (Paket Düşürüldü)", FaultSeverity.WARNING),
    CommonFaultId.ROUTER_TRP_UNAVAILABLE: FaultInfo(0x0022, "ROUTER_TRP_UNAVAILABLE", "Hedef Hat Bağlı Değil veya Taşıyıcı TX Kaydı Yok", FaultSeverity.ERROR),
    CommonFaultId.ROUTER_LOOPBACK_DETECTED: FaultInfo(0x0023, "ROUTER_LOOPBACK_DETECTED", "Paket Geldiği Hatta Geri Gönderilmek İstendi (Loopback)", FaultSeverity.WARNING),
    CommonFaultId.ROUTER_QUEUE_FULL: FaultInfo(0x0024, "ROUTER_QUEUE_FULL", "Router Mesaj Kuyruğu Taştı (Queue Overflow)", FaultSeverity.ERROR),

    # Protokol & Çerçeve Hataları (0x0030 - 0x003F)
    CommonFaultId.PROTOCOL_VERSION_MISMATCH: FaultInfo(0x0030, "PROTOCOL_VERSION_MISMATCH", "Protokol Versiyonu Uyumsuz (v1.1 Bekleniyordu)", FaultSeverity.WARNING),
    CommonFaultId.FRAME_HEADER_TOO_SHORT: FaultInfo(0x0031, "FRAME_HEADER_TOO_SHORT", "Evrensel Çerçeve Başlık Boyutu Yetersiz (< 9 Byte)", FaultSeverity.WARNING),
    CommonFaultId.PAYLOAD_TOO_LARGE: FaultInfo(0x0032, "PAYLOAD_TOO_LARGE", "Payload DEOS_MAX_PAYLOAD_LEN Sınırını Aşıyor", FaultSeverity.WARNING),
    CommonFaultId.FRAME_CRC_MISMATCH: FaultInfo(0x0033, "FRAME_CRC_MISMATCH", "Çerçeve CRC16 Doğrulama Hatası", FaultSeverity.WARNING),
    CommonFaultId.FRAME_DECODE_FAILED: FaultInfo(0x0034, "FRAME_DECODE_FAILED", "Çerçeve Decode Edilemedi (Parse Hatası)", FaultSeverity.WARNING),

    # CAN / CAN-FD Taşıyıcı Hataları (0x0040 - 0x005F)
    CommonFaultId.CAN_DEV_NOT_READY: FaultInfo(0x0040, "CAN_DEV_NOT_READY", "CAN Donanım Aygıtı Hazır Değil", FaultSeverity.CRITICAL),
    CommonFaultId.CAN_MODE_NOT_SUPPORTED: FaultInfo(0x0041, "CAN_MODE_NOT_SUPPORTED", "CAN-FD Modu Donanımca Desteklenmiyor", FaultSeverity.ERROR),
    CommonFaultId.CAN_FILTER_INSTALL_FAILED: FaultInfo(0x0042, "CAN_FILTER_INSTALL_FAILED", "Donanımsal CAN RX Filtre Kurulamadı", FaultSeverity.ERROR),
    CommonFaultId.CAN_RX_QUEUE_FULL: FaultInfo(0x0043, "CAN_RX_QUEUE_FULL", "CAN RX Alıcı Kuyruğu Taştı", FaultSeverity.WARNING),
    CommonFaultId.CAN_TX_QUEUE_FULL: FaultInfo(0x0044, "CAN_TX_QUEUE_FULL", "CAN TX Gönderici Kuyruğu Taştı", FaultSeverity.WARNING),
    CommonFaultId.CAN_TX_SEND_FAILED: FaultInfo(0x0045, "CAN_TX_SEND_FAILED", "CAN Veriyolu İletim Hatası (Zephyr can_send başarısız / TX Mailbox Dolu / Hatta ACK Alınamadı)", FaultSeverity.WARNING),
    CommonFaultId.CAN_FRAME_DECODE_ERR: FaultInfo(0x0046, "CAN_FRAME_DECODE_ERR", "Gelen CAN Çerçevesi Parse Edilemedi", FaultSeverity.WARNING),
    CommonFaultId.CAN_BUS_OFF: FaultInfo(0x0047, "CAN_BUS_OFF", "CAN Controller Bus-Off Durumuna Geçti (Veriyolu Kilitli)", FaultSeverity.CRITICAL),

    # UART / LoRa Taşıyıcı Hataları (0x0060 - 0x007F)
    CommonFaultId.LORA_DEV_NOT_READY: FaultInfo(0x0060, "LORA_DEV_NOT_READY", "LoRa UART Donanımı Hazır Değil / Yanıt Vermiyor", FaultSeverity.ERROR),
    CommonFaultId.LORA_TX_QUEUE_FULL: FaultInfo(0x0061, "LORA_TX_QUEUE_FULL", "LoRa TX Kuyruğu Taştı", FaultSeverity.WARNING),
    CommonFaultId.LORA_RX_BUFFER_OVERFLOW: FaultInfo(0x0062, "LORA_RX_BUFFER_OVERFLOW", "LoRa Ring Buffer Taştı", FaultSeverity.WARNING),
    CommonFaultId.LORA_CRC_MISMATCH: FaultInfo(0x0063, "LORA_CRC_MISMATCH", "Havadan Gelen LoRa Paketinin CRC'si Hatalı", FaultSeverity.WARNING),
    CommonFaultId.LORA_FRAME_MALFORMED: FaultInfo(0x0064, "LORA_FRAME_MALFORMED", "Havadan Gelen LoRa Paket Başlığı Bozuk (Magic/Flag Hatası)", FaultSeverity.WARNING),
    CommonFaultId.LORA_ACK_TIMEOUT: FaultInfo(0x0065, "LORA_ACK_TIMEOUT", "LoRa Güvenilir İletimde ACK Yanıtı Alınamadı (Timeout)", FaultSeverity.WARNING),

    # Ethernet / Network Taşıyıcı Hataları (0x0080 - 0x009F)
    CommonFaultId.ETH_LINK_DOWN: FaultInfo(0x0080, "ETH_LINK_DOWN", "Ethernet Kablosu Takılı Değil / Link Yok", FaultSeverity.WARNING),
    CommonFaultId.ETH_SOCKET_CREATE_FAILED: FaultInfo(0x0081, "ETH_SOCKET_CREATE_FAILED", "TCP/UDP Soket Oluşturulamadı", FaultSeverity.ERROR),
    CommonFaultId.ETH_SOCKET_BIND_FAILED: FaultInfo(0x0082, "ETH_SOCKET_BIND_FAILED", "Soket Porta Bind Edilemedi", FaultSeverity.ERROR),
    CommonFaultId.ETH_TX_QUEUE_FULL: FaultInfo(0x0083, "ETH_TX_QUEUE_FULL", "Ethernet TX Kuyruğu Taştı", FaultSeverity.WARNING),
    CommonFaultId.ETH_TX_SEND_FAILED: FaultInfo(0x0084, "ETH_TX_SEND_FAILED", "Soket Send / Sendto Hatası", FaultSeverity.ERROR),
    CommonFaultId.ETH_CLIENT_DISCONNECTED: FaultInfo(0x0085, "ETH_CLIENT_DISCONNECTED", "Bağlı Web UI / ROS Bridge İstemcisi Koptu", FaultSeverity.WARNING),
    CommonFaultId.ETH_FRAME_DECODE_ERR: FaultInfo(0x0086, "ETH_FRAME_DECODE_ERR", "Gelen Ethernet Çerçevesi Bozuk", FaultSeverity.WARNING),

    # Dağıtıcı (Dispatcher) Hataları (0x00A0 - 0x00AF)
    CommonFaultId.DISPATCH_TABLE_FULL: FaultInfo(0x00A0, "DISPATCH_TABLE_FULL", "Handler Tablosunda Yer Kalmadı", FaultSeverity.ERROR),
    CommonFaultId.DISPATCH_DUPLICATE_HANDLER: FaultInfo(0x00A1, "DISPATCH_DUPLICATE_HANDLER", "Aynı Komut İçin Mükerrer Handler Kaydı Yapıldı", FaultSeverity.WARNING),
    CommonFaultId.DISPATCH_HANDLER_NOT_FOUND: FaultInfo(0x00A2, "DISPATCH_HANDLER_NOT_FOUND", "Gelen Komut İçin Handler Tanımlı Değil (İşlenemedi)", FaultSeverity.ERROR),
}

# Node-Specific Fault Registries (0x0100+)
NODE_FAULTS: Dict[Tuple[int, int], FaultInfo] = {
    # Main STM32 (0x03)
    (NodeId.MAIN_STM32, 0x0045): FaultInfo(0x0045, "CAN_TX_SEND_FAILED", "Main STM32 CAN-FD İletim Hatası (Zephyr can_send başarısız / TX Mailbox Dolu / Hatta ACK Alınamadı)", FaultSeverity.WARNING),
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

    # Smart subsystem range fallbacks for unlisted codes
    if 0x0040 <= fault_id <= 0x004F:
        name = f"CAN_BUS_ERR_0x{fault_id:02X}"
        desc = f"CAN / CAN-FD Veriyolu Hatası (0x{fault_id:04X}) - TX/RX veya Donanım İletim Problemi"
        severity = FaultSeverity.WARNING
    elif 0x0050 <= fault_id <= 0x005F:
        name = f"LORA_RADIO_ERR_0x{fault_id:02X}"
        desc = f"LoRa RF / UART Radyo Hatası (0x{fault_id:04X}) - Paket veya Arayüz Hatası"
        severity = FaultSeverity.ERROR
    elif 0x0060 <= fault_id <= 0x006F:
        name = f"ETH_NET_ERR_0x{fault_id:02X}"
        desc = f"Ethernet Ağ Arayüz Hatası (0x{fault_id:04X}) - PHY veya Link Hatası"
        severity = FaultSeverity.ERROR
    elif 0x0070 <= fault_id <= 0x007F:
        name = f"SENSOR_ERR_0x{fault_id:02X}"
        desc = f"Sensör / ADC Giriş Okuma Hatası (0x{fault_id:04X})"
        severity = FaultSeverity.WARNING
    elif 0x0080 <= fault_id <= 0x008F:
        name = f"POWER_ERR_0x{fault_id:02X}"
        desc = f"Voltaj / Güç Besleme Hatası (0x{fault_id:04X})"
        severity = FaultSeverity.CRITICAL
    else:
        name = f"DTC_0x{fault_id:04X}"
        desc = f"Düğüm 0x{node_id:02X} üzerinde tanımsız arıza kodu (0x{fault_id:04X}) - ICD dokümanını kontrol edin"
        severity = FaultSeverity.ERROR

    return FaultInfo(
        code=fault_id,
        name=name,
        description=desc,
        default_severity=severity,
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

