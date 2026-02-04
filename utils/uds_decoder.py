# utils/uds_decoder.py

"""
Description:
Provides UDS protocol decoding capabilities using DID configurations from JSON.
"""

# ----------------------------------------------------------------------------------
# 1) Imports & Configuration
# ----------------------------------------------------------------------------------
from typing import Optional, Dict, Callable, List, Tuple
import json
import os
import logging
from backend.can_interface import CANFrame

logger = logging.getLogger(__name__)

# Load DID configuration with fallback
def load_did_config(file_path: str = os.path.join(os.path.dirname(__file__), '..', 'data', 'dids.json')) -> Dict[int, Tuple[str, Callable[[List[int]], str]]]:
    """Load DID configuration from a JSON file with a fallback default."""
    default_dids = {
        0xF190: ("VIN", decode_ascii),
        0xF124: ("ECU Serial Number", decode_ascii),
        0xF1A0: ("Odometer", lambda d: decode_uint(d, 4)),
    }
    try:
        with open(file_path, "r") as f:
            raw_data = json.load(f)
        did_lookup = {}
        for did_hex, info in raw_data.items():
            did = int(did_hex, 16)
            decoder_name = info.get("decoder", "ascii")
            if decoder_name == "uint":
                byte_count = info.get("byte_count", 4)
                decoder = lambda d, bc=byte_count: decode_uint(d, bc)
            else:
                decoder = DECODERS.get(decoder_name, lambda x: ' '.join(f"{b:02X}" for b in x))
            did_lookup[did] = (info["name"], decoder)
        logger.info(f"Loaded DID config from {file_path}")
        return did_lookup
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to load DID config from {file_path}: {e}. Using default.")
        return default_dids

# ----------------------------------------------------------------------------------
# 2) Decoder Functions
# ----------------------------------------------------------------------------------
def decode_ascii(data: List[int]) -> str:
    """Decode bytes as ASCII, replacing non-printable chars with '.'."""
    return ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)

def decode_uint(data: List[int], byte_count: int = 4) -> str:
    """Decode bytes as an unsigned integer (big-endian)."""
    if len(data) < byte_count:
        return f"Invalid ({len(data)} bytes)"
    value = 0
    for b in data[:byte_count]:
        value = (value << 8) | b
    return str(value)

# Mapping of decoder names to functions
DECODERS: Dict[str, Callable[[List[int]], str]] = {
    "ascii": decode_ascii,
    "uint": lambda d: decode_uint(d, 4),  # Default to 4 bytes, overridden by JSON
}

DID_LOOKUP = load_did_config()  # Initial load

def _decode_did(data: List[int], start_idx: int = 1, include_payload: bool = False) -> str:
    """Helper to decode a DID from frame data and optionally include payload."""
    if len(data) < start_idx + 2:
        return "Invalid DID"
    did = (data[start_idx] << 8) | data[start_idx + 1]
    did_info = DID_LOOKUP.get(did, (f"0x{did:04X}", lambda x: ' '.join(f"{b:02X}" for b in x)))
    did_str = did_info[0]
    if include_payload and len(data) > start_idx + 2:
        payload = did_info[1](data[start_idx + 2:])
        return f"DID: {did_str}, Data: {payload}"
    return f"DID: {did_str}"

UDS_SERVICES: Dict[int, Tuple[str, Callable[[CANFrame], str]]] = {
    0x10: ("DiagnosticSessionControl", lambda f: f"Session: {f.data[1]:02X}" if len(f.data) > 1 else ""),
    0x11: ("ECUReset", lambda f: f"Reset Type: {f.data[1]:02X}" if len(f.data) > 1 else ""),
    0x14: ("ClearDiagnosticInformation", lambda f: f"DTC: {(f.data[1] << 16) | (f.data[2] << 8) | f.data[3]:06X}" if len(f.data) >= 4 else ""),
    0x19: ("ReadDTCInformation", lambda f: f"Sub-Function: {f.data[1]:02X}" if len(f.data) > 1 else ""),
    0x22: ("ReadDataByIdentifier", lambda f: _decode_did(f.data) if len(f.data) >= 3 else ""),
    0x27: ("SecurityAccess", lambda f: f"Level: {f.data[1]:02X}" if len(f.data) > 1 else ""),
    0x2E: ("WriteDataByIdentifier", lambda f: _decode_did(f.data, include_payload=True) if len(f.data) >= 4 else ""),
    0x31: ("RoutineControl", lambda f: f"Type: {f.data[1]:02X}, Routine: {(f.data[2] << 8) | f.data[3]:04X}" if len(f.data) >= 4 else ""),
    0x36: ("TransferData", lambda f: f"Block: {f.data[1]:02X}, Data: {' '.join(f'{b:02X}' for b in f.data[2:])}" if len(f.data) >= 3 else ""),
    0x3E: ("TesterPresent", lambda f: "TesterPresent"),
}

def decode_uds(frame: CANFrame) -> Optional[str]:
    """Decode a UDS frame into a human-readable string."""
    if not frame.data or len(frame.data) < 1:
        return None
    sid = frame.data[0]
    is_response = sid >= 0x40
    if is_response:
        request_sid = sid - 0x40
        if request_sid in UDS_SERVICES:
            name, _ = UDS_SERVICES[request_sid]
            if request_sid == 0x22 and len(frame.data) >= 3:
                did = (frame.data[1] << 8) | frame.data[2]
                did_info = DID_LOOKUP.get(did, (f"0x{did:04X}", lambda x: ' '.join(f"{b:02X}" for b in x)))
                payload = did_info[1](frame.data[3:]) if len(frame.data) > 3 else "No Data"
                return f"{name} Response → DID: {did_info[0]}, {payload}"
            if len(frame.data) > 1:
                return f"{name} Response → Data: {' '.join(f'{b:02X}' for b in frame.data[1:])}"
            return f"{name} Response"
    if sid == 0x7F and len(frame.data) >= 3:
        request_sid = frame.data[1]
        nrc = frame.data[2]
        nrc_desc = {
            0x10: "General Reject",
            0x11: "Service Not Supported",
            0x12: "Sub-Function Not Supported",
            0x22: "Conditions Not Correct",
            0x31: "Request Out Of Range",
        }.get(nrc, f"Unknown NRC: {nrc:02X}")
        return f"Negative Response → SID: {request_sid:02X}, {nrc_desc}"
    if sid in UDS_SERVICES:
        name, decode_func = UDS_SERVICES[sid]
        details = decode_func(frame)
        return f"{name}{f' → {details}' if details else ''}"
    return None