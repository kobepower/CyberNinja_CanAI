# backend/multi_interface.py

"""
Multi-Protocol CAN/LIN Interface
Supports: SLCAN (SavvyCAN, CANtact, etc), MCP2515, LIN

For Kobe's Keys - Automotive Diagnostics
"""

import serial
import serial.tools.list_ports
import threading
import time
import logging
import re
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Callable, Tuple
from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

class BusType(Enum):
    CAN = "CAN"
    CAN_FD = "CAN-FD"
    LIN = "LIN"

class Direction(Enum):
    RX = "RX"
    TX = "TX"

class InterfaceType(Enum):
    SIMULATION = "Simulation"
    SLCAN = "SLCAN (SavvyCAN/CANtact)"
    MCP2515 = "MCP2515 (Arduino)"
    LIN = "LIN Bus"
    SOCKETCAN = "SocketCAN (Linux)"

@dataclass
class CANFrame:
    timestamp: str
    can_id: str
    data: List[int]
    direction: Direction
    bus_type: BusType = BusType.CAN
    channel: int = 0  # For dual-channel adapters
    
    def __str__(self) -> str:
        data_hex = ' '.join(f"{byte:02X}" for byte in self.data)
        return f"[{self.timestamp}] CH{self.channel} {self.direction.value} ID:{self.can_id} Data:{data_hex}"

@dataclass 
class LINFrame:
    timestamp: str
    pid: int  # Protected ID (0-63)
    data: List[int]
    direction: Direction
    checksum: int = 0
    
    def __str__(self) -> str:
        data_hex = ' '.join(f"{byte:02X}" for byte in self.data)
        return f"[{self.timestamp}] LIN PID:{self.pid:02X} Data:{data_hex}"


# =============================================================================
# SLCAN Protocol Handler (SavvyCAN-FD-X2, CANtact, USBtin, etc)
# =============================================================================

class SLCANProtocol:
    """
    SLCAN (Serial Line CAN) Protocol
    Used by: SavvyCAN, CANtact, USBtin, Lawicel CANUSB
    
    Commands:
        O     - Open CAN channel
        C     - Close CAN channel  
        Sn    - Set bitrate (S0=10k, S1=20k, S2=50k, S3=100k, S4=125k, S5=250k, S6=500k, S7=800k, S8=1M)
        tiiildd..  - Transmit standard frame (iii=ID, l=len, dd=data)
        Tiiiiiiiildd.. - Transmit extended frame
        riiil  - Transmit RTR frame
        F     - Read status flags
        V     - Get version
        N     - Get serial number
    
    Received frames:
        tiiildd..  - Standard frame received
        Tiiiiiiiildd.. - Extended frame received
    """
    
    # Bitrate commands
    BITRATES = {
        10000: 'S0',
        20000: 'S1', 
        50000: 'S2',
        100000: 'S3',
        125000: 'S4',
        250000: 'S5',
        500000: 'S6',
        800000: 'S7',
        1000000: 'S8',
    }
    
    # Common automotive bitrates
    CAN_BITRATES = {
        '33.3 kbps (GM SW-CAN)': 33333,
        '83.3 kbps (J1850/GM Class 2)': 83333,
        '125 kbps (J1939 Trucks)': 125000,
        '250 kbps (J1939/OBD)': 250000,
        '500 kbps (ISO 15765/OBD-II)': 500000,
        '1 Mbps (CAN-FD)': 1000000,
    }
    
    @staticmethod
    def open_channel() -> bytes:
        return b'O\r'
    
    @staticmethod
    def close_channel() -> bytes:
        return b'C\r'
    
    @staticmethod
    def set_bitrate(bitrate: int) -> bytes:
        cmd = SLCANProtocol.BITRATES.get(bitrate, 'S6')  # Default 500k
        return f'{cmd}\r'.encode()
    
    @staticmethod
    def build_frame(can_id: int, data: List[int], extended: bool = False) -> bytes:
        """Build SLCAN transmit command."""
        dlc = len(data)
        data_hex = ''.join(f'{b:02X}' for b in data)
        
        if extended:
            # Extended frame: Tiiiiiiiildd...
            return f'T{can_id:08X}{dlc}{data_hex}\r'.encode()
        else:
            # Standard frame: tiiildd...
            return f't{can_id:03X}{dlc}{data_hex}\r'.encode()
    
    @staticmethod
    def parse_frame(line: str) -> Optional[CANFrame]:
        """Parse SLCAN received frame."""
        line = line.strip()
        if not line:
            return None
            
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Standard frame: tiiildd...
        if line.startswith('t') and len(line) >= 5:
            try:
                can_id = line[1:4]
                dlc = int(line[4], 16)
                data_hex = line[5:5 + dlc * 2]
                data = [int(data_hex[i:i+2], 16) for i in range(0, len(data_hex), 2)]
                return CANFrame(timestamp, can_id, data, Direction.RX)
            except (ValueError, IndexError):
                return None
        
        # Extended frame: Tiiiiiiiildd...
        elif line.startswith('T') and len(line) >= 10:
            try:
                can_id = line[1:9]
                dlc = int(line[9], 16)
                data_hex = line[10:10 + dlc * 2]
                data = [int(data_hex[i:i+2], 16) for i in range(0, len(data_hex), 2)]
                return CANFrame(timestamp, can_id, data, Direction.RX)
            except (ValueError, IndexError):
                return None
        
        return None


# =============================================================================
# MCP2515 Protocol Handler (Arduino/SPI based CAN modules)
# =============================================================================

class MCP2515Protocol:
    """
    MCP2515 over Serial (Arduino sketch)
    
    Common Arduino CAN libraries send data as:
        ID:xxx,LEN:n,DATA:xx,xx,xx...
    Or raw hex format depending on sketch.
    
    This handler supports multiple common formats.
    """
    
    # Standard MCP2515 speeds
    CAN_SPEEDS = {
        '5 kbps': 5000,
        '10 kbps': 10000,
        '20 kbps': 20000,
        '31.25 kbps': 31250,
        '33.3 kbps': 33333,
        '40 kbps': 40000,
        '50 kbps': 50000,
        '80 kbps': 80000,
        '83.3 kbps': 83333,
        '95 kbps': 95000,
        '100 kbps': 100000,
        '125 kbps': 125000,
        '200 kbps': 200000,
        '250 kbps': 250000,
        '500 kbps': 500000,
        '1000 kbps': 1000000,
    }
    
    @staticmethod
    def parse_frame(line: str) -> Optional[CANFrame]:
        """Parse various MCP2515 Arduino output formats."""
        line = line.strip()
        if not line:
            return None
            
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Format 1: ID:xxx,LEN:n,DATA:xx,xx,xx
        match = re.match(r'ID:([0-9A-Fa-f]+),LEN:(\d+),DATA:([\dA-Fa-f,\s]+)', line)
        if match:
            can_id = match.group(1).upper()
            data_str = match.group(3).replace(' ', '').replace(',', '')
            data = [int(data_str[i:i+2], 16) for i in range(0, len(data_str), 2)]
            return CANFrame(timestamp, can_id, data, Direction.RX)
        
        # Format 2: xxx#xx.xx.xx.xx (candump style)
        match = re.match(r'([0-9A-Fa-f]+)#([\dA-Fa-f.]+)', line)
        if match:
            can_id = match.group(1).upper()
            data_str = match.group(2).replace('.', '')
            data = [int(data_str[i:i+2], 16) for i in range(0, len(data_str), 2)]
            return CANFrame(timestamp, can_id, data, Direction.RX)
        
        # Format 3: Raw hex line (ID DLC D0 D1 D2...)
        parts = line.split()
        if len(parts) >= 3:
            try:
                can_id = parts[0].upper()
                # Check if second part is DLC or data
                if len(parts[1]) == 1:
                    dlc = int(parts[1])
                    data = [int(p, 16) for p in parts[2:2+dlc]]
                else:
                    data = [int(p, 16) for p in parts[1:]]
                return CANFrame(timestamp, can_id, data, Direction.RX)
            except (ValueError, IndexError):
                pass
        
        return None
    
    @staticmethod
    def build_frame(can_id: int, data: List[int]) -> bytes:
        """Build frame for sending (Arduino format)."""
        data_hex = ','.join(f'{b:02X}' for b in data)
        return f'SEND:{can_id:03X},{len(data)},{data_hex}\r\n'.encode()


# =============================================================================
# LIN Protocol Handler
# =============================================================================

class LINProtocol:
    """
    LIN (Local Interconnect Network) Bus Protocol
    
    LIN Frame Structure:
        - Sync Break (13+ dominant bits)
        - Sync Field (0x55)
        - Protected ID (6-bit ID + 2 parity bits)
        - Data (1-8 bytes)
        - Checksum (classic or enhanced)
    
    Common LIN speeds: 9600, 19200 baud (max 20kbps)
    """
    
    LIN_SPEEDS = {
        '9600 baud': 9600,
        '19200 baud': 19200,
    }
    
    # Standard LIN PIDs
    STANDARD_PIDS = {
        0x3C: "Master Request",
        0x3D: "Slave Response",
        0x3E: "Reserved",
        0x3F: "Reserved",
    }
    
    @staticmethod
    def calculate_pid(frame_id: int) -> int:
        """Calculate Protected ID from 6-bit frame ID."""
        id_bits = frame_id & 0x3F
        p0 = (id_bits ^ (id_bits >> 1) ^ (id_bits >> 2) ^ (id_bits >> 4)) & 1
        p1 = ~((id_bits >> 1) ^ (id_bits >> 3) ^ (id_bits >> 4) ^ (id_bits >> 5)) & 1
        return id_bits | (p0 << 6) | (p1 << 7)
    
    @staticmethod
    def calculate_checksum(pid: int, data: List[int], enhanced: bool = True) -> int:
        """Calculate LIN checksum (classic or enhanced)."""
        if enhanced:
            checksum = pid
        else:
            checksum = 0
            
        for byte in data:
            checksum += byte
            if checksum > 255:
                checksum -= 255
                
        return (~checksum) & 0xFF
    
    @staticmethod
    def parse_frame(line: str) -> Optional[LINFrame]:
        """Parse LIN frame from serial data."""
        line = line.strip()
        if not line:
            return None
            
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Format: PID:xx,DATA:xx,xx,xx,CKS:xx
        match = re.match(r'PID:([0-9A-Fa-f]+),DATA:([\dA-Fa-f,]+),CKS:([0-9A-Fa-f]+)', line)
        if match:
            pid = int(match.group(1), 16)
            data_str = match.group(2).replace(',', '')
            data = [int(data_str[i:i+2], 16) for i in range(0, len(data_str), 2)]
            checksum = int(match.group(3), 16)
            return LINFrame(timestamp, pid, data, Direction.RX, checksum)
        
        # Format: LIN xx xx xx xx xx (raw)
        if line.upper().startswith('LIN'):
            parts = line.split()[1:]
            if len(parts) >= 2:
                try:
                    pid = int(parts[0], 16)
                    data = [int(p, 16) for p in parts[1:-1]]
                    checksum = int(parts[-1], 16)
                    return LINFrame(timestamp, pid, data, Direction.RX, checksum)
                except (ValueError, IndexError):
                    pass
        
        return None


# =============================================================================
# Multi-Protocol Interface Class
# =============================================================================

class MultiProtocolInterface(QObject):
    """
    Unified interface for CAN/CAN-FD/LIN communication.
    Supports multiple adapter types and protocols.
    """
    
    frame_received = pyqtSignal(object)  # CANFrame or LINFrame
    connection_changed = pyqtSignal(bool, str)  # connected, message
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        self.interface_type = InterfaceType.SIMULATION
        self.bus_type = BusType.CAN
        self.serial_port = None
        self.serial_baudrate = 115200  # Serial port baud (not CAN baud)
        self.can_bitrate = 500000  # CAN bus bitrate
        
        self._serial: Optional[serial.Serial] = None
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_count = 0
        
        # Simulation settings
        self.sim_interval = 2.0
        self._sim_ids = ['7E8', '7E0', '18DAF110', '18DA10F1']
    
    @staticmethod
    def list_ports() -> List[Dict]:
        """List available serial ports with descriptions."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                'device': port.device,
                'description': port.description,
                'hwid': port.hwid,
                'vid': port.vid,
                'pid': port.pid,
            })
        return ports
    
    def connect(self, port: str, interface_type: InterfaceType, 
                can_bitrate: int = 500000, serial_baud: int = 115200) -> bool:
        """Connect to the specified interface."""
        
        self.interface_type = interface_type
        self.can_bitrate = can_bitrate
        self.serial_baudrate = serial_baud
        self.serial_port = port
        
        if interface_type == InterfaceType.SIMULATION:
            self._running.set()
            self._thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self._thread.start()
            self.connection_changed.emit(True, "Simulation mode active")
            logger.info("Started simulation mode")
            return True
        
        try:
            with self._lock:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=serial_baud,
                    timeout=0.1,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE
                )
            
            # Initialize based on interface type
            if interface_type == InterfaceType.SLCAN:
                self._init_slcan()
            elif interface_type == InterfaceType.MCP2515:
                self._init_mcp2515()
            elif interface_type == InterfaceType.LIN:
                self._init_lin()
            
            self._running.set()
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            
            self.connection_changed.emit(True, f"Connected to {port}")
            logger.info(f"Connected to {port} as {interface_type.value}")
            return True
            
        except serial.SerialException as e:
            self.error_occurred.emit(f"Connection failed: {e}")
            logger.error(f"Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from current interface."""
        self._running.clear()
        
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        
        with self._lock:
            if self._serial and self._serial.is_open:
                if self.interface_type == InterfaceType.SLCAN:
                    self._serial.write(SLCANProtocol.close_channel())
                self._serial.close()
                self._serial = None
        
        self.connection_changed.emit(False, "Disconnected")
        logger.info("Disconnected")
    
    def _init_slcan(self):
        """Initialize SLCAN adapter."""
        # Close any existing channel
        self._serial.write(SLCANProtocol.close_channel())
        time.sleep(0.1)
        
        # Set bitrate
        self._serial.write(SLCANProtocol.set_bitrate(self.can_bitrate))
        time.sleep(0.1)
        
        # Open channel
        self._serial.write(SLCANProtocol.open_channel())
        time.sleep(0.1)
        
        # Clear any pending data
        self._serial.reset_input_buffer()
        logger.info(f"SLCAN initialized at {self.can_bitrate} bps")
    
    def _init_mcp2515(self):
        """Initialize MCP2515 Arduino module."""
        # Send init command (depends on Arduino sketch)
        self._serial.write(b'INIT\r\n')
        time.sleep(0.5)
        self._serial.reset_input_buffer()
        logger.info("MCP2515 initialized")
    
    def _init_lin(self):
        """Initialize LIN interface."""
        self._serial.reset_input_buffer()
        logger.info("LIN interface initialized")
    
    def send_frame(self, can_id: int, data: List[int], extended: bool = False) -> bool:
        """Send a CAN frame."""
        if not self._running.is_set():
            return False
        
        try:
            with self._lock:
                if self.interface_type == InterfaceType.SLCAN:
                    cmd = SLCANProtocol.build_frame(can_id, data, extended)
                    self._serial.write(cmd)
                elif self.interface_type == InterfaceType.MCP2515:
                    cmd = MCP2515Protocol.build_frame(can_id, data)
                    self._serial.write(cmd)
                elif self.interface_type == InterfaceType.SIMULATION:
                    # Echo back in simulation
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    frame = CANFrame(timestamp, f"{can_id:03X}", data, Direction.TX)
                    self.frame_received.emit(frame)
                    
            self._frame_count += 1
            return True
        except Exception as e:
            self.error_occurred.emit(f"Send failed: {e}")
            return False
    
    def send_lin_frame(self, pid: int, data: List[int]) -> bool:
        """Send a LIN frame."""
        if self.interface_type != InterfaceType.LIN:
            return False
        
        try:
            checksum = LINProtocol.calculate_checksum(pid, data)
            cmd = f'LIN:{pid:02X},{",".join(f"{b:02X}" for b in data)},{checksum:02X}\r\n'
            with self._lock:
                self._serial.write(cmd.encode())
            return True
        except Exception as e:
            self.error_occurred.emit(f"LIN send failed: {e}")
            return False
    
    def _read_loop(self):
        """Main read loop for serial data."""
        buffer = ""
        
        while self._running.is_set():
            try:
                with self._lock:
                    if self._serial and self._serial.in_waiting:
                        data = self._serial.read(self._serial.in_waiting)
                        buffer += data.decode('utf-8', errors='ignore')
                
                # Process complete lines
                while '\r' in buffer or '\n' in buffer:
                    # Find line ending
                    idx = min(
                        buffer.find('\r') if '\r' in buffer else len(buffer),
                        buffer.find('\n') if '\n' in buffer else len(buffer)
                    )
                    line = buffer[:idx].strip()
                    buffer = buffer[idx+1:].lstrip('\r\n')
                    
                    if line:
                        self._process_line(line)
                
                time.sleep(0.001)  # Small delay to prevent CPU spin
                
            except Exception as e:
                if self._running.is_set():
                    self.error_occurred.emit(f"Read error: {e}")
                    logger.error(f"Read error: {e}")
                time.sleep(0.1)
    
    def _process_line(self, line: str):
        """Process a received line based on interface type."""
        frame = None
        
        if self.interface_type == InterfaceType.SLCAN:
            frame = SLCANProtocol.parse_frame(line)
        elif self.interface_type == InterfaceType.MCP2515:
            frame = MCP2515Protocol.parse_frame(line)
        elif self.interface_type == InterfaceType.LIN:
            frame = LINProtocol.parse_frame(line)
        
        if frame:
            self._frame_count += 1
            self.frame_received.emit(frame)
    
    def _simulation_loop(self):
        """Generate simulated CAN frames."""
        import random
        
        while self._running.is_set():
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            can_id = random.choice(self._sim_ids)
            
            # Generate realistic UDS-like data
            service = random.choice([0x01, 0x03, 0x09, 0x22, 0x27, 0x2E, 0x3E])
            data = [service] + [random.randint(0, 255) for _ in range(random.randint(1, 7))]
            
            direction = random.choice([Direction.RX, Direction.TX])
            frame = CANFrame(timestamp, can_id, data, direction)
            
            self.frame_received.emit(frame)
            self._frame_count += 1
            
            self._running.wait(timeout=self.sim_interval)
    
    def get_frame_count(self) -> int:
        return self._frame_count
    
    def is_connected(self) -> bool:
        return self._running.is_set()


# =============================================================================
# Convenience function for quick setup
# =============================================================================

def get_interface_options() -> Dict:
    """Get available interface types and their settings."""
    return {
        'interfaces': [t.value for t in InterfaceType],
        'slcan_bitrates': list(SLCANProtocol.CAN_BITRATES.keys()),
        'mcp2515_speeds': list(MCP2515Protocol.CAN_SPEEDS.keys()),
        'lin_speeds': list(LINProtocol.LIN_SPEEDS.keys()),
    }
