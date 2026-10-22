"""Pydantic Models and Request Validators (v1.1 Master).

Derived from:
- BLUEPRINT_GROUND_STATION_MICROSERVICES-v2.2.md Section 1, 5
- DOC-ICD-CORE-001 (Addressing & Unicast rules)
- DOC-ICD-NET-003  (SYSTEM unicast constraints & Subscription engine)
- DOC-ICD-NODE-BMS-012 (Direct addressing to 0x20/0x21, never 0x30 for BMS service)
- DOC-ICD-SRV-LGHT-012 (Lighting always targets Main STM32 0x03)
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator

from .enums import (
    BmsCommand,
    BrakeCommand,
    ConfigCommand,
    DiagnosticCommand,
    LightingCommand,
    MessageClass,
    NodeId,
    Priority,
    ServiceId,
    SteeringCommand,
    SystemCommand,
    TractionCommand,
)


class CommandRequest(BaseModel):
    """Universal Command Request received from Web UI or API on `command/request`."""
    destination: int = Field(..., description="Target Node ID (deos_node_id_t)")
    service: int = Field(..., description="Functional Service ID (deos_service_id_t)")
    command: int = Field(..., description="Command ID within the service")
    message_class: Optional[int] = Field(None, description="Message class (auto-inferred if None)")
    priority: Optional[int] = Field(None, description="Priority (auto-inferred if None)")
    ack: bool = Field(False, description="True for reliable transmission (Flag=0x01), False for unreliable (Flag=0x00)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters/payload fields")

    @model_validator(mode="after")
    def validate_icd_rules(self) -> "CommandRequest":
        dest = self.destination
        srv = self.service
        cmd = self.command

        # Rule 1: Broadcast restriction for Unicast-only commands
        # PING (0x08), GET_NODE_INFO (0x06), SUBSCRIBE (0x0A), UNSUBSCRIBE (0x0B)
        # MUST NOT target 0xFE (CAN_BROADCAST) or 0xFF (GLOBAL_BROADCAST).
        if srv == ServiceId.SYSTEM and cmd in (
            SystemCommand.PING,
            SystemCommand.GET_NODE_INFO,
            SystemCommand.SUBSCRIBE,
            SystemCommand.UNSUBSCRIBE,
        ):
            if dest in (NodeId.CAN_BROADCAST, NodeId.GLOBAL_BROADCAST):
                raise ValueError(
                    f"Command {SystemCommand(cmd).name} requires UNICAST destination! "
                    f"Targeting broadcast {hex(dest)} is prohibited by DOC-ICD-NET-003."
                )

        # Rule 2: BMS Service Addressing Rule (DOC-ICD-NODE-BMS-012 Section 2)
        # BMS service messages must NEVER be addressed to BMS_GATEWAY (0x30).
        # They must directly address BMS_MAIN (0x20) or BMS_AUX (0x21).
        if srv == ServiceId.BMS and dest == NodeId.BMS_GATEWAY:
            raise ValueError(
                "BMS Service messages cannot target BMS_GATEWAY (0x30)! "
                "Must directly target BMS_MAIN (0x20) or BMS_AUX (0x21)."
            )

        # Rule 3: Lighting Service Rule (DOC-ICD-SRV-LGHT-012 Section 1)
        # Lighting is not an independent node; it runs on MAIN_STM32 (0x03).
        if srv == ServiceId.LIGHTING and dest != NodeId.MAIN_STM32:
            raise ValueError(
                f"LIGHTING service (0x08) must target DEOS_NODE_MAIN_STM32 (0x03), got {hex(dest)}!"
            )

        # Auto-infer default message class and priority if omitted
        if self.message_class is None:
            if srv == ServiceId.SYSTEM:
                if cmd in (SystemCommand.PING, SystemCommand.PONG, SystemCommand.HEARTBEAT):
                    self.message_class = MessageClass.NETWORK
                elif cmd in (
                    SystemCommand.GET_NODE_INFO,
                    SystemCommand.GET_STATE,
                    SystemCommand.GET_MODE,
                    SystemCommand.SUBSCRIBE,
                    SystemCommand.UNSUBSCRIBE,
                ):
                    self.message_class = MessageClass.REQUEST
                elif cmd in (SystemCommand.SET_STATE, SystemCommand.SET_MODE, SystemCommand.RESET_NODE):
                    self.message_class = MessageClass.COMMAND
                else:
                    self.message_class = MessageClass.COMMAND

            elif srv == ServiceId.TRACTION:
                if cmd == TractionCommand.GET_STATUS:
                    self.message_class = MessageClass.REQUEST
                elif cmd in (ConfigCommand.SET_PARAMETER, ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
                    self.message_class = MessageClass.CONFIG
                elif cmd == ConfigCommand.GET_PARAMETER:
                    self.message_class = MessageClass.REQUEST
                else:
                    self.message_class = MessageClass.COMMAND

            elif srv == ServiceId.STEERING:
                if cmd == SteeringCommand.GET_STATUS:
                    self.message_class = MessageClass.REQUEST
                elif cmd in (ConfigCommand.SET_PARAMETER, ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
                    self.message_class = MessageClass.CONFIG
                elif cmd == ConfigCommand.GET_PARAMETER:
                    self.message_class = MessageClass.REQUEST
                else:
                    self.message_class = MessageClass.COMMAND

            elif srv == ServiceId.BRAKE:
                if cmd == BrakeCommand.GET_STATUS:
                    self.message_class = MessageClass.REQUEST
                elif cmd in (ConfigCommand.SET_PARAMETER, ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
                    self.message_class = MessageClass.CONFIG
                elif cmd == ConfigCommand.GET_PARAMETER:
                    self.message_class = MessageClass.REQUEST
                else:
                    self.message_class = MessageClass.COMMAND

            elif srv == ServiceId.BMS:
                if cmd in (
                    BmsCommand.GET_STATUS,
                    BmsCommand.GET_CELL_VOLTAGES,
                    BmsCommand.GET_TEMPERATURES,
                    BmsCommand.GET_BALANCING,
                    ConfigCommand.GET_PARAMETER,
                ):
                    self.message_class = MessageClass.REQUEST
                elif cmd in (ConfigCommand.SET_PARAMETER, ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
                    self.message_class = MessageClass.CONFIG
                else:
                    self.message_class = MessageClass.COMMAND

            elif srv == ServiceId.DIAGNOSTIC:
                if cmd in (DiagnosticCommand.GET_HEALTH, DiagnosticCommand.GET_FAULTS):
                    self.message_class = MessageClass.REQUEST
                elif cmd == DiagnosticCommand.CLEAR_FAULTS:
                    self.message_class = MessageClass.COMMAND
                else:
                    self.message_class = MessageClass.REQUEST

            elif srv == ServiceId.LIGHTING:
                if cmd == LightingCommand.GET_STATUS:
                    self.message_class = MessageClass.REQUEST
                else:
                    self.message_class = MessageClass.COMMAND

            elif cmd == ConfigCommand.GET_PARAMETER:
                self.message_class = MessageClass.REQUEST
            elif cmd in (ConfigCommand.SET_PARAMETER, ConfigCommand.SAVE_PARAMETERS, ConfigCommand.RESTORE_DEFAULTS):
                self.message_class = MessageClass.CONFIG
            else:
                self.message_class = MessageClass.COMMAND

        if self.priority is None:
            if srv == ServiceId.SYSTEM:
                if cmd in (SystemCommand.RESET_NODE,):
                    self.priority = Priority.EMERGENCY
                elif cmd in (SystemCommand.SET_STATE, SystemCommand.SET_MODE):
                    self.priority = Priority.CRITICAL_CONTROL
                elif cmd in (SystemCommand.SUBSCRIBE, SystemCommand.UNSUBSCRIBE):
                    self.priority = Priority.CONFIG
                elif cmd in (SystemCommand.PING, SystemCommand.PONG, SystemCommand.HEARTBEAT):
                    self.priority = Priority.NETWORK
                else:
                    self.priority = Priority.NETWORK
            elif self.message_class == MessageClass.SAFETY:
                self.priority = Priority.EMERGENCY
            elif self.message_class == MessageClass.COMMAND:
                self.priority = Priority.CRITICAL_CONTROL
            elif self.message_class == MessageClass.CONFIG:
                self.priority = Priority.CONFIG
            elif self.message_class == MessageClass.REQUEST:
                self.priority = Priority.STATUS
            else:
                self.priority = Priority.STATUS

        return self

