"""Safe ctypes bridge to the `deos-protocol` ANSI C99 shared library.

Provides Pythonic wrappers around `deos_frame.c`, `deos_codec.c`, and
`deos_registry.c` without ever writing inside the `deos-protocol` git submodule.
"""

import ctypes
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

logger = logging.getLogger("deos.c_bridge")

# Constants matching deos-protocol/include/deos/{deos_icd.h,deos_types.h,deos_frame.h,deos_registry.h}
DEOS_UNIVERSAL_HEADER_SIZE = 9
DEOS_PROTOCOL_VERSION = 0x12
DEOS_MAX_PAYLOAD_LEN = 60
DEOS_MAX_REGISTRY_HANDLERS = 32

_LIB_NAME = "libdeos_protocol.so"
_SUBMODULE_SOURCES = (
    "deos_frame.c",
    "deos_codec.c",
    "deos_registry.c",
)

_lib_instance: Optional[ctypes.CDLL] = None


class CDeosMessage(ctypes.Structure):
    """Exact ABI mirror of `deos_message_t` in `deos_types.h`."""

    _fields_ = [
        ("priority", ctypes.c_uint),
        ("message_class", ctypes.c_uint),
        ("service", ctypes.c_uint),
        ("destination", ctypes.c_uint),
        ("source", ctypes.c_uint),
        ("version", ctypes.c_uint8),
        ("sequence", ctypes.c_uint8),
        ("command", ctypes.c_uint8),
        ("payload", ctypes.c_uint8 * DEOS_MAX_PAYLOAD_LEN),
        ("payload_len", ctypes.c_uint8),
    ]


C_HANDLER_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.POINTER(CDeosMessage),
    ctypes.c_void_p,
)


class CDeosRegistryEntry(ctypes.Structure):
    """Exact ABI mirror of `deos_registry_entry_t` in `deos_registry.h`."""

    _fields_ = [
        ("in_use", ctypes.c_bool),
        ("local_node", ctypes.c_uint),
        ("message_class", ctypes.c_uint),
        ("service", ctypes.c_uint),
        ("command", ctypes.c_uint8),
        ("handler", C_HANDLER_TYPE),
        ("user_data", ctypes.c_void_p),
    ]


class CDeosRegistry(ctypes.Structure):
    """Exact ABI mirror of `deos_registry_t` in `deos_registry.h`."""

    _fields_ = [
        ("entries", CDeosRegistryEntry * DEOS_MAX_REGISTRY_HANDLERS),
        ("count", ctypes.c_size_t),
    ]


def _is_cached_lib_fresh(so_path: Path, src_dir: Path, inc_dir: Path) -> bool:
    """Return True if cached shared library exists and is newer than all C sources/headers."""
    if not so_path.is_file():
        return False
    so_mtime = so_path.stat().st_mtime
    watched_files = list(src_dir.glob("*.c")) + list(inc_dir.glob("*.h"))
    if not watched_files:
        return False
    return all(f.stat().st_mtime <= so_mtime for f in watched_files)


def _compile_local_shared_lib(submodule_dir: Path, target_so: Path) -> Path:
    """Compile `deos-protocol` C99 sources into `<repo_root>/build/libdeos_protocol.so`."""
    src_dir = submodule_dir / "src"
    inc_root = submodule_dir / "include"
    inc_deos = inc_root / "deos"

    required_files = [src_dir / name for name in _SUBMODULE_SOURCES] + [inc_deos / "deos_frame.h"]
    if any(not p.is_file() for p in required_files):
        raise RuntimeError(
            "deos-protocol submodule kaynak kodları bulunamadı! "
            "Lütfen 'git submodule update --init --recursive' çalıştırın."
        )

    if _is_cached_lib_fresh(target_so, src_dir, inc_deos):
        return target_so

    target_so.parent.mkdir(parents=True, exist_ok=True)
    tmp_so = target_so.parent / f".{target_so.name}.{os.getpid()}.tmp"
    c_sources = [str(src_dir / name) for name in _SUBMODULE_SOURCES]
    cmd = [
        "gcc",
        "-std=c99",
        "-Wall",
        "-Wextra",
        "-O2",
        "-fPIC",
        "-shared",
        f"-I{inc_root}",
        *c_sources,
        "-o",
        str(tmp_so),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        os.replace(tmp_so, target_so)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"C derleyicisi (gcc) bulunamadı ve hazır {_LIB_NAME} mevcut değil."
        ) from exc
    except subprocess.CalledProcessError as exc:
        if tmp_so.exists():
            tmp_so.unlink()
        raise RuntimeError(
            f"libdeos_protocol.so derlenemedi (exit={exc.returncode}): {exc.stderr.strip()}"
        ) from exc

    return target_so


def _configure_signatures(lib: ctypes.CDLL) -> ctypes.CDLL:
    """Attach explicit ctypes argtypes/restype signatures to all exported C functions."""
    u8_ptr = ctypes.POINTER(ctypes.c_uint8)
    msg_ptr = ctypes.POINTER(CDeosMessage)
    reg_ptr = ctypes.POINTER(CDeosRegistry)

    lib.deos_frame_encode.argtypes = [msg_ptr, u8_ptr, ctypes.c_size_t]
    lib.deos_frame_encode.restype = ctypes.c_int

    lib.deos_frame_decode.argtypes = [u8_ptr, ctypes.c_size_t, msg_ptr]
    lib.deos_frame_decode.restype = ctypes.c_int

    lib.deos_node_name.argtypes = [ctypes.c_uint8]
    lib.deos_node_name.restype = ctypes.c_char_p

    lib.deos_transport_name.argtypes = [ctypes.c_uint]
    lib.deos_transport_name.restype = ctypes.c_char_p

    lib.deos_service_name.argtypes = [ctypes.c_uint8]
    lib.deos_service_name.restype = ctypes.c_char_p

    lib.deos_class_name.argtypes = [ctypes.c_uint8]
    lib.deos_class_name.restype = ctypes.c_char_p

    lib.deos_command_name.argtypes = [ctypes.c_uint8, ctypes.c_uint8]
    lib.deos_command_name.restype = ctypes.c_char_p

    lib.deos_fault_name.argtypes = [ctypes.c_uint16]
    lib.deos_fault_name.restype = ctypes.c_char_p

    lib.deos_fault_severity_name.argtypes = [ctypes.c_uint]
    lib.deos_fault_severity_name.restype = ctypes.c_char_p

    lib.deos_registry_sizeof.argtypes = []
    lib.deos_registry_sizeof.restype = ctypes.c_size_t

    lib.deos_registry_init.argtypes = [reg_ptr]
    lib.deos_registry_init.restype = ctypes.c_int

    lib.deos_registry_register_for_node.argtypes = [
        reg_ptr,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint8,
        C_HANDLER_TYPE,
        ctypes.c_void_p,
    ]
    lib.deos_registry_register_for_node.restype = ctypes.c_int

    lib.deos_registry_unregister.argtypes = [
        reg_ptr,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint8,
    ]
    lib.deos_registry_unregister.restype = ctypes.c_int

    lib.deos_registry_dispatch.argtypes = [reg_ptr, msg_ptr]
    lib.deos_registry_dispatch.restype = ctypes.c_int

    lib.deos_put_u16_le.argtypes = [u8_ptr, ctypes.c_uint16]
    lib.deos_put_u16_le.restype = None

    lib.deos_get_u16_le.argtypes = [u8_ptr]
    lib.deos_get_u16_le.restype = ctypes.c_uint16

    lib.deos_put_i16_le.argtypes = [u8_ptr, ctypes.c_int16]
    lib.deos_put_i16_le.restype = None

    lib.deos_get_i16_le.argtypes = [u8_ptr]
    lib.deos_get_i16_le.restype = ctypes.c_int16

    lib.deos_put_u32_le.argtypes = [u8_ptr, ctypes.c_uint32]
    lib.deos_put_u32_le.restype = None

    lib.deos_get_u32_le.argtypes = [u8_ptr]
    lib.deos_get_u32_le.restype = ctypes.c_uint32

    lib.deos_put_i32_le.argtypes = [u8_ptr, ctypes.c_int32]
    lib.deos_put_i32_le.restype = None

    lib.deos_get_i32_le.argtypes = [u8_ptr]
    lib.deos_get_i32_le.restype = ctypes.c_int32

    return lib


def load_deos_protocol_lib() -> ctypes.CDLL:
    """Locate or build `libdeos_protocol.so`, configure ctypes signatures, and return it."""
    env_path = os.getenv("DEOS_PROTOCOL_LIB_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(f"/usr/local/lib/{_LIB_NAME}"))

    for candidate in candidates:
        if candidate.is_file():
            return _configure_signatures(ctypes.CDLL(str(candidate)))

    repo_root = Path(__file__).resolve().parents[2]
    submodule_dir = Path(os.getenv("DEOS_PROTOCOL_DIR", str(repo_root / "deos-protocol")))
    cached_so = repo_root / "build" / _LIB_NAME
    built_so = _compile_local_shared_lib(submodule_dir, cached_so)
    return _configure_signatures(ctypes.CDLL(str(built_so)))


def get_lib() -> ctypes.CDLL:
    """Return the cached singleton CDLL handle for `libdeos_protocol.so`."""
    global _lib_instance
    if _lib_instance is None:
        _lib_instance = load_deos_protocol_lib()
    return _lib_instance


@dataclass(frozen=True)
class CDecodedFrame:
    """Decoded Universal DEOS Frame produced by `deos_frame_decode`."""

    destination: int
    source: int
    priority: int
    version: int
    message_class: int
    service: int
    command: int
    sequence: int
    payload: bytes

    @property
    def destination_name(self) -> str:
        return c_node_name(self.destination)

    @property
    def source_name(self) -> str:
        return c_node_name(self.source)

    @property
    def service_name(self) -> str:
        return c_service_name(self.service)

    @property
    def class_name(self) -> str:
        return c_class_name(self.message_class)

    @property
    def command_name(self) -> str:
        return c_command_name(self.service, self.command)


def _c_msg_from_fields(
    destination: int,
    source: int,
    priority: int,
    message_class: int,
    service: int,
    command: int,
    sequence: int = 0,
    payload: Union[bytes, bytearray, memoryview] = b"",
    version: int = DEOS_PROTOCOL_VERSION,
) -> CDeosMessage:
    """Build and validate a `CDeosMessage` from Python field values."""
    payload_bytes = bytes(payload)
    if len(payload_bytes) > DEOS_MAX_PAYLOAD_LEN:
        raise ValueError(
            f"Payload length {len(payload_bytes)} exceeds DEOS_MAX_PAYLOAD_LEN ({DEOS_MAX_PAYLOAD_LEN})"
        )

    c_msg = CDeosMessage()
    c_msg.destination = destination & 0xFF
    c_msg.source = source & 0xFF
    c_msg.priority = priority & 0xFF
    c_msg.version = version & 0xFF
    c_msg.message_class = message_class & 0xFF
    c_msg.service = service & 0xFF
    c_msg.command = command & 0xFF
    c_msg.sequence = sequence & 0xFF
    c_msg.payload_len = len(payload_bytes)

    if payload_bytes:
        ctypes.memmove(c_msg.payload, payload_bytes, len(payload_bytes))

    return c_msg


def _decoded_from_c_msg(c_msg: CDeosMessage) -> CDecodedFrame:
    """Convert a `CDeosMessage` struct to an immutable `CDecodedFrame`."""
    plen = int(c_msg.payload_len)
    if plen > DEOS_MAX_PAYLOAD_LEN:
        raise ValueError(f"Decoded payload_len {plen} exceeds {DEOS_MAX_PAYLOAD_LEN}")
    return CDecodedFrame(
        destination=int(c_msg.destination),
        source=int(c_msg.source),
        priority=int(c_msg.priority),
        version=int(c_msg.version),
        message_class=int(c_msg.message_class),
        service=int(c_msg.service),
        command=int(c_msg.command),
        sequence=int(c_msg.sequence),
        payload=bytes(c_msg.payload[:plen]),
    )


def c_encode_frame(
    destination: int,
    source: int,
    priority: int,
    message_class: int,
    service: int,
    command: int,
    sequence: int = 0,
    payload: Union[bytes, bytearray, memoryview] = b"",
    version: int = DEOS_PROTOCOL_VERSION,
) -> bytes:
    """Encode a Universal DEOS Frame (9+N bytes) via C `deos_frame_encode`."""
    lib = get_lib()
    c_msg = _c_msg_from_fields(
        destination=destination,
        source=source,
        priority=priority,
        message_class=message_class,
        service=service,
        command=command,
        sequence=sequence,
        payload=payload,
        version=version,
    )
    out_cap = DEOS_UNIVERSAL_HEADER_SIZE + c_msg.payload_len
    out_buf = (ctypes.c_uint8 * out_cap)()
    res = lib.deos_frame_encode(ctypes.byref(c_msg), out_buf, out_cap)
    if res < 0:
        raise ValueError(f"deos_frame_encode failed ({res}): {os.strerror(-res)}")
    return bytes(out_buf[:res])


def c_decode_frame(data: Union[bytes, bytearray, memoryview]) -> CDecodedFrame:
    """Decode a Universal DEOS Frame (9+N bytes) via C `deos_frame_decode`."""
    raw = bytes(data)
    if len(raw) < DEOS_UNIVERSAL_HEADER_SIZE:
        raise ValueError(
            f"Frame too short for UNIVERSAL_9B: {len(raw)} < {DEOS_UNIVERSAL_HEADER_SIZE} bytes"
        )

    lib = get_lib()
    in_buf = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
    c_msg = CDeosMessage()
    res = lib.deos_frame_decode(in_buf, len(raw), ctypes.byref(c_msg))
    if res != 0:
        raise ValueError(f"deos_frame_decode failed ({res}): {os.strerror(-res)}")
    return _decoded_from_c_msg(c_msg)


def c_node_name(node_id: int) -> str:
    """Return official C node name string for `node_id`."""
    return get_lib().deos_node_name(node_id & 0xFF).decode("utf-8")


def c_transport_name(transport_id: int) -> str:
    """Return official C transport name string for `transport_id`."""
    return get_lib().deos_transport_name(int(transport_id) & 0xFF).decode("utf-8")


def c_service_name(service_id: int) -> str:
    """Return official C service name string for `service_id`."""
    return get_lib().deos_service_name(service_id & 0xFF).decode("utf-8")


def c_class_name(msg_class: int) -> str:
    """Return official C message class name string for `msg_class`."""
    return get_lib().deos_class_name(msg_class & 0xFF).decode("utf-8")


_ICD_PARAM_CMD_NAMES = {
    0xE0: "GET_PARAMETER",
    0xE1: "SET_PARAMETER",
    0xE2: "SAVE_PARAMETERS",
    0xE3: "RESTORE_DEFAULTS",
    0xE4: "GET_PARAMETER_INFO",
}


def c_command_name(service_id: int, command_id: int) -> str:
    """Return official C command name string, falling back to `deos_icd.h` for PARAM commands."""
    srv = service_id & 0xFF
    cmd = command_id & 0xFF
    name = get_lib().deos_command_name(srv, cmd).decode("utf-8")
    if name == "UNKNOWN_CMD" and cmd in _ICD_PARAM_CMD_NAMES:
        return _ICD_PARAM_CMD_NAMES[cmd]
    return name


def c_fault_name(fault_id: int) -> str:
    """Return official C fault name string for `fault_id`."""
    return get_lib().deos_fault_name(int(fault_id) & 0xFFFF).decode("utf-8")


def c_fault_severity_name(severity: int) -> str:
    """Return official C fault severity string for `severity`."""
    return get_lib().deos_fault_severity_name(int(severity) & 0xFF).decode("utf-8")


def _extract_codec_slice(
    data: Union[bytes, bytearray, memoryview],
    offset: int,
    size: int,
) -> ctypes.Array:
    """Validate bounds and copy `size` bytes into a ctypes uint8 array."""
    if offset < 0:
        raise ValueError(f"Offset must be non-negative, got {offset}")
    raw = bytes(data)
    if len(raw) - offset < size:
        raise ValueError(
            f"Buffer too short for {size}-byte decode at offset {offset}: len={len(raw)}"
        )
    return (ctypes.c_uint8 * size).from_buffer_copy(raw[offset : offset + size])


def put_u16_le(value: int) -> bytes:
    """Pack an unsigned 16-bit integer in Little-Endian using `deos_put_u16_le`."""
    if not (0 <= value <= 0xFFFF):
        raise ValueError(f"uint16 out of range (0..65535): {value}")
    buf = (ctypes.c_uint8 * 2)()
    get_lib().deos_put_u16_le(buf, value)
    return bytes(buf)


def get_u16_le(data: Union[bytes, bytearray, memoryview], offset: int = 0) -> int:
    """Unpack an unsigned 16-bit Little-Endian integer using `deos_get_u16_le`."""
    buf = _extract_codec_slice(data, offset, 2)
    return int(get_lib().deos_get_u16_le(buf))


def put_i16_le(value: int) -> bytes:
    """Pack a signed 16-bit integer in Little-Endian using `deos_put_i16_le`."""
    if not (-32768 <= value <= 32767):
        raise ValueError(f"int16 out of range (-32768..32767): {value}")
    buf = (ctypes.c_uint8 * 2)()
    get_lib().deos_put_i16_le(buf, value)
    return bytes(buf)


def get_i16_le(data: Union[bytes, bytearray, memoryview], offset: int = 0) -> int:
    """Unpack a signed 16-bit Little-Endian integer using `deos_get_i16_le`."""
    buf = _extract_codec_slice(data, offset, 2)
    return int(get_lib().deos_get_i16_le(buf))


def put_u32_le(value: int) -> bytes:
    """Pack an unsigned 32-bit integer in Little-Endian using `deos_put_u32_le`."""
    if not (0 <= value <= 0xFFFFFFFF):
        raise ValueError(f"uint32 out of range (0..4294967295): {value}")
    buf = (ctypes.c_uint8 * 4)()
    get_lib().deos_put_u32_le(buf, value)
    return bytes(buf)


def get_u32_le(data: Union[bytes, bytearray, memoryview], offset: int = 0) -> int:
    """Unpack an unsigned 32-bit Little-Endian integer using `deos_get_u32_le`."""
    buf = _extract_codec_slice(data, offset, 4)
    return int(get_lib().deos_get_u32_le(buf))


def put_i32_le(value: int) -> bytes:
    """Pack a signed 32-bit integer in Little-Endian using `deos_put_i32_le`."""
    if not (-2147483648 <= value <= 2147483647):
        raise ValueError(f"int32 out of range (-2147483648..2147483647): {value}")
    buf = (ctypes.c_uint8 * 4)()
    get_lib().deos_put_i32_le(buf, value)
    return bytes(buf)


def get_i32_le(data: Union[bytes, bytearray, memoryview], offset: int = 0) -> int:
    """Unpack a signed 32-bit Little-Endian integer using `deos_get_i32_le`."""
    buf = _extract_codec_slice(data, offset, 4)
    return int(get_lib().deos_get_i32_le(buf))


class DeosCallbackRegistry:
    """Pythonic wrapper over C `deos_registry_t` retaining callback GC references."""

    def __init__(self) -> None:
        self._lib = get_lib()
        expected_size = int(self._lib.deos_registry_sizeof())
        if expected_size != ctypes.sizeof(CDeosRegistry):
            raise RuntimeError(
                f"CDeosRegistry ABI size mismatch: Python={ctypes.sizeof(CDeosRegistry)}, C={expected_size}"
            )
        self._reg = CDeosRegistry()
        rc = self._lib.deos_registry_init(ctypes.byref(self._reg))
        if rc != 0:
            raise RuntimeError(f"deos_registry_init failed ({rc}): {os.strerror(-rc)}")
        self._callbacks: Dict[Tuple[int, int, int, int], C_HANDLER_TYPE] = {}

    def register(
        self,
        message_class: int,
        service: int,
        command: int,
        callback: Callable[[CDecodedFrame], None],
        local_node: int = 0xFF,
    ) -> None:
        """Register a Python callback in the C registry for `(local_node, class, service, cmd)`."""
        key = (local_node & 0xFF, message_class & 0xFF, service & 0xFF, command & 0xFF)

        def _c_shim(msg_ptr, _user_data) -> int:
            try:
                frame = _decoded_from_c_msg(msg_ptr.contents)
                callback(frame)
                return 0
            except Exception as exc:
                logger.error("Error in DeosCallbackRegistry callback: %s", exc)
                return -1

        c_func = C_HANDLER_TYPE(_c_shim)
        rc = self._lib.deos_registry_register_for_node(
            ctypes.byref(self._reg),
            key[0],
            key[1],
            key[2],
            key[3],
            c_func,
            None,
        )
        if rc != 0:
            raise ValueError(f"deos_registry_register_for_node failed ({rc}): {os.strerror(-rc)}")
        self._callbacks[key] = c_func

    def unregister(
        self,
        message_class: int,
        service: int,
        command: int,
        local_node: int = 0xFF,
    ) -> None:
        """Remove a previously registered callback from the C registry."""
        key = (local_node & 0xFF, message_class & 0xFF, service & 0xFF, command & 0xFF)
        rc = self._lib.deos_registry_unregister(
            ctypes.byref(self._reg),
            key[0],
            key[1],
            key[2],
            key[3],
        )
        if rc != 0:
            raise ValueError(f"deos_registry_unregister failed ({rc}): {os.strerror(-rc)}")
        self._callbacks.pop(key, None)

    def dispatch(self, frame_or_bytes: Union[CDecodedFrame, bytes, bytearray, memoryview]) -> int:
        """Dispatch a decoded frame or raw Universal Frame bytes through `deos_registry_dispatch`."""
        frame = (
            frame_or_bytes
            if isinstance(frame_or_bytes, CDecodedFrame)
            else c_decode_frame(frame_or_bytes)
        )
        c_msg = _c_msg_from_fields(
            destination=frame.destination,
            source=frame.source,
            priority=frame.priority,
            message_class=frame.message_class,
            service=frame.service,
            command=frame.command,
            sequence=frame.sequence,
            payload=frame.payload,
            version=frame.version,
        )
        rc = self._lib.deos_registry_dispatch(ctypes.byref(self._reg), ctypes.byref(c_msg))
        if rc < 0:
            raise ValueError(f"deos_registry_dispatch failed ({rc}): {os.strerror(-rc)}")
        return int(rc)
