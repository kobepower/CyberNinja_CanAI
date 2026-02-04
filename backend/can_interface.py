# backend/can_interface.py

"""
Description:
Handles low-level CAN communication, including serial interface and simulation mode.
"""

# ----------------------------------------------------------------------------------
# 1) Imports & Constants
# ----------------------------------------------------------------------------------
from typing import List, Optional, Dict, Callable, Tuple
import serial
import random
import threading
import time
import logging
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from PyQt5.QtCore import QObject, pyqtSignal

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# 2) Data Structures
# ----------------------------------------------------------------------------------
class Direction(Enum):
    RX = "RX"
    TX = "TX"

@dataclass
class CANFrame:
    timestamp: str
    can_id: str
    data: List[int]
    direction: Direction

    def __str__(self) -> str:
        data_hex = ' '.join(f"{byte:02X}" for byte in self.data)
        return f"[{self.timestamp}] {self.direction.value} ID:{self.can_id} Data:{data_hex}"

# ----------------------------------------------------------------------------------
# 3) CANInterface Class
# ----------------------------------------------------------------------------------
class CANInterface(QObject):
    """Manages physical/simulated CAN interface with thread-safe operations."""
    frame_received = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)  # True=connected, False=disconnected
    connection_lost = pyqtSignal(str)

    def __init__(
        self,
        simulate: bool = True,
        serial_port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        sim_interval: float = 1.0,  # Generate frame every 1 second in simulation
        max_data_bytes: int = 8,
        reconnect_attempts: int = 5
    ):
        super().__init__()
        self.simulate = simulate
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.sim_interval = sim_interval
        self.max_data_bytes = max_data_bytes
        self._reconnect_attempts = max(1, reconnect_attempts)
        self.auto_reconnect = False  # Added for CANMonitorTab compatibility
        self._running = threading.Event()
        self._serial: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._serial_lock = threading.Lock()
        self._can_id_range: Tuple[int, int] = (0x100, 0x7FF)
        self._frame_parser: Callable[[str], Optional[CANFrame]] = self._default_frame_parser
        self._frame_count: int = 0

    def start(self) -> bool:
        if self._running.is_set():
            logger.warning("[CANInterface] Already running")
            return True
        self._running.set()
        target = self._simulate_frames if self.simulate else self._serial_read_loop
        if not self.simulate and not self._open_serial():
            self._running.clear()
            return False
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        logger.info(f"[CANInterface] Started in {'simulation' if self.simulate else 'serial'} mode")
        self.connection_changed.emit(True)
        return True

    def stop(self) -> None:
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._close_serial()
        logger.info("[CANInterface] Stopped")
        self.connection_changed.emit(False)

    def is_running(self) -> bool:
        return self._running.is_set()

    def get_frame_count(self) -> int:
        return self._frame_count

    def set_reconnect_attempts(self, attempts: int) -> None:
        self._reconnect_attempts = max(1, attempts)
        logger.debug(f"[CANInterface] Reconnect attempts set to {self._reconnect_attempts}")

    def _open_serial(self) -> bool:
        try:
            with self._serial_lock:
                self._serial = serial.Serial(
                    self.serial_port,
                    self.baudrate,
                    timeout=1,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
            logger.info(f"[CANInterface] Connected to {self.serial_port} @ {self.baudrate}")
            self.connection_changed.emit(True)
            return True
        except serial.SerialException as e:
            logger.error(f"[CANInterface] Failed to open serial: {e}")
            self.connection_changed.emit(False)
            return False

    def _close_serial(self) -> None:
        with self._serial_lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
                self._serial = None
                logger.debug("[CANInterface] Serial port closed")
                self.connection_changed.emit(False)

    def _simulate_frames(self) -> None:
        while self._running.is_set():
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            can_id = f"{random.randint(*self._can_id_range):03X}"
            data = [random.randint(0x00, 0xFF) for _ in range(random.randint(1, self.max_data_bytes))]
            direction = random.choice(list(Direction))
            frame = CANFrame(timestamp, can_id, data, direction)
            self.frame_received.emit(frame)
            self._frame_count += 1
            self._running.wait(timeout=self.sim_interval)

    def simulate_uds_frame(self, sid: int, data: List[int], direction: Direction = Direction.RX) -> None:
        """Simulate a specific UDS frame for testing."""
        if not self.simulate or not self._running.is_set():
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        can_id = f"{random.randint(*self._can_id_range):03X}"
        frame = CANFrame(timestamp, can_id, [sid] + data, direction)
        self.frame_received.emit(frame)
        self._frame_count += 1

    def _serial_read_loop(self) -> None:
        attempt = 0
        while self._running.is_set():
            if not self._serial or not self._serial.is_open:
                if not self.auto_reconnect or attempt >= self._reconnect_attempts:
                    logger.error("[CANInterface] Max reconnect attempts reached or auto-reconnect disabled")
                    self.connection_lost.emit(f"Failed to reconnect to {self.serial_port} after {attempt} attempts")
                    self.stop()
                    break
                self._attempt_reconnect(attempt)
                attempt += 1
                continue
            try:
                line = self._serial.readline().decode().strip()
                if line:
                    frame = self._frame_parser(line)
                    if frame:
                        self.frame_received.emit(frame)
                        self._frame_count += 1
                    attempt = 0  # Reset on successful read
            except (UnicodeDecodeError, serial.SerialException) as e:
                logger.error(f"[CANInterface] Serial error: {e}")
                self._close_serial()
            except Exception as e:
                logger.error(f"[CANInterface] Unexpected error: {e}")

    def _attempt_reconnect(self, attempt: int) -> None:
        delay = min(2 ** attempt, 10)
        logger.info(f"[CANInterface] Reconnect attempt {attempt + 1}/{self._reconnect_attempts} in {delay}s")
        time.sleep(delay)
        self._open_serial()

    def _default_frame_parser(self, line: str) -> Optional[CANFrame]:
        try:
            parts = line.split(",", 3)
            if len(parts) != 4:
                logger.warning(f"[CANInterface] Invalid frame format: {line}")
                return None
            timestamp, can_id, data_hex, direction_str = parts
            can_id = can_id.upper().strip()
            can_id_int = int(can_id, 16)
            if not (0 <= can_id_int <= 0x7FF):
                logger.warning(f"[CANInterface] CAN ID out of range (0-0x7FF): {can_id}")
                return None
            data_length = len(data_hex)
            if data_length % 2 != 0 or data_length > self.max_data_bytes * 2:
                logger.warning(f"[CANInterface] Invalid data length: {data_hex}")
                return None
            data = [int(data_hex[i:i+2], 16) for i in range(0, data_length, 2)]
            direction = Direction(direction_str)
            return CANFrame(timestamp, can_id, data, direction)
        except Exception as e:
            logger.error(f"[CANInterface] Parse error: {e} in line: {line}")
            return None

    def send_frame(self, frame: CANFrame) -> bool:
        if not self._running.is_set():
            logger.warning("[CANInterface] Interface not running")
            return False
        if len(frame.data) > self.max_data_bytes:
            logger.warning(f"[CANInterface] Data exceeds max bytes ({self.max_data_bytes}): {frame.data}")
            return False
        if self.simulate:
            self.frame_received.emit(frame)
            self._frame_count += 1
            logger.debug(f"[CANInterface] Simulated frame sent: {frame}")
            return True
        with self._serial_lock:
            if not self._serial or not self._serial.is_open:
                logger.error("[CANInterface] Serial not open for sending")
                return False
            try:
                data_hex = ''.join(f"{byte:02X}" for byte in frame.data)
                frame_str = f"{frame.timestamp},{frame.can_id},{data_hex},{frame.direction.value}\n"
                self._serial.write(frame_str.encode())
                self._serial.flush()
                logger.debug(f"[CANInterface] Sent frame: {frame_str.strip()}")
                return True
            except serial.SerialException as e:
                logger.error(f"[CANInterface] Send error: {e}")
                return False

    def set_simulation_id_range(self, min_id: int, max_id: int) -> None:
        if 0 <= min_id <= max_id <= 0x7FF:
            self._can_id_range = (min_id, max_id)
            logger.debug(f"[CANInterface] Simulation ID range set to {min_id:03X}-{max_id:03X}")
        else:
            logger.warning(f"[CANInterface] Invalid CAN ID range: {min_id}-{max_id}")

    def set_frame_parser(self, parser: Callable[[str], Optional[CANFrame]]) -> None:
        self._frame_parser = parser
        logger.debug("[CANInterface] Custom frame parser set")

    def __del__(self) -> None:
        self.stop()