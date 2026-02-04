# gui/tabs/key_tools_tab.py

"""
Description:
Key programming tools for locksmiths - Security Access, Key Slot reading, 
Seed/Key workflows for FCA, GM, Toyota, and other supported vehicles.
"""

# ----------------------------------------------------------------------------------
# 1) Imports
# ----------------------------------------------------------------------------------
import logging
from datetime import datetime
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
from enum import Enum

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QMessageBox, QSpinBox, QTabWidget, QFrame, QGridLayout,
    QHeaderView, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.QtGui import QFont, QColor

from backend.can_interface import CANInterface, CANFrame, Direction

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# 2) Data Structures
# ----------------------------------------------------------------------------------
class SecurityLevel(Enum):
    LEVEL_01 = 0x01  # Standard diagnostic
    LEVEL_03 = 0x03  # Programming
    LEVEL_05 = 0x05  # Extended
    LEVEL_07 = 0x07  # Development
    LEVEL_11 = 0x11  # FCA specific
    LEVEL_21 = 0x21  # GM specific

@dataclass
class VehicleProfile:
    name: str
    manufacturer: str
    tx_id: int
    rx_id: int
    security_levels: List[int]
    key_did: int
    key_count_did: int
    vin_did: int = 0xF190
    session_type: int = 0x03  # Programming session

# Vehicle profiles database
VEHICLE_PROFILES: Dict[str, VehicleProfile] = {
    "FCA 2011-2018 (MPC5606B)": VehicleProfile(
        name="FCA 2011-2018",
        manufacturer="FCA",
        tx_id=0x7E0,
        rx_id=0x7E8,
        security_levels=[0x01, 0x03, 0x11],
        key_did=0xF195,
        key_count_did=0xF196,
    ),
    "FCA 2018+ (MPC5646C)": VehicleProfile(
        name="FCA 2018+",
        manufacturer="FCA",
        tx_id=0x7E0,
        rx_id=0x7E8,
        security_levels=[0x01, 0x03, 0x11, 0x21],
        key_did=0xF195,
        key_count_did=0xF196,
    ),
    "GM 2010-2020": VehicleProfile(
        name="GM 2010-2020",
        manufacturer="GM",
        tx_id=0x7E0,
        rx_id=0x7E8,
        security_levels=[0x01, 0x03, 0x21],
        key_did=0x00B4,
        key_count_did=0x00B5,
    ),
    "Toyota 2012+": VehicleProfile(
        name="Toyota 2012+",
        manufacturer="Toyota",
        tx_id=0x7E0,
        rx_id=0x7E8,
        security_levels=[0x01, 0x03, 0x05],
        key_did=0xE102,
        key_count_did=0xE103,
    ),
    "Honda 2016+": VehicleProfile(
        name="Honda 2016+",
        manufacturer="Honda",
        tx_id=0x18DA30F1,
        rx_id=0x18DAF130,
        security_levels=[0x01, 0x61],
        key_did=0xF195,
        key_count_did=0xF196,
    ),
    "Ford 2015+": VehicleProfile(
        name="Ford 2015+",
        manufacturer="Ford",
        tx_id=0x7E0,
        rx_id=0x7E8,
        security_levels=[0x01, 0x03, 0x07],
        key_did=0xF195,
        key_count_did=0xF196,
    ),
    "Custom": VehicleProfile(
        name="Custom",
        manufacturer="Custom",
        tx_id=0x7E0,
        rx_id=0x7E8,
        security_levels=[0x01, 0x03],
        key_did=0xF195,
        key_count_did=0xF196,
    ),
}

# UDS Service IDs
class UDS:
    DIAGNOSTIC_SESSION = 0x10
    ECU_RESET = 0x11
    SECURITY_ACCESS = 0x27
    READ_DATA = 0x22
    WRITE_DATA = 0x2E
    ROUTINE_CONTROL = 0x31
    TESTER_PRESENT = 0x3E
    NEGATIVE_RESPONSE = 0x7F

# NRC (Negative Response Codes)
NRC_DESCRIPTIONS = {
    0x10: "General Reject",
    0x11: "Service Not Supported",
    0x12: "Sub-Function Not Supported",
    0x13: "Invalid Format",
    0x14: "Response Too Long",
    0x22: "Conditions Not Correct",
    0x24: "Request Sequence Error",
    0x25: "No Response From Subnet",
    0x31: "Request Out Of Range",
    0x33: "Security Access Denied",
    0x35: "Invalid Key",
    0x36: "Exceeded Number Of Attempts",
    0x37: "Required Time Delay Not Expired",
    0x70: "Upload/Download Not Accepted",
    0x71: "Transfer Data Suspended",
    0x72: "General Programming Failure",
    0x78: "Request Correctly Received - Response Pending",
}

# ----------------------------------------------------------------------------------
# 3) KeyToolsTab Class
# ----------------------------------------------------------------------------------
class KeyToolsTab(QWidget):
    """Key programming and security access tools for locksmiths."""
    
    status_updated = pyqtSignal(str, str)  # message, style
    
    # Color scheme (CyberNinja theme)
    COLORS = {
        "bg_dark": "#0a0a0f",
        "bg_panel": "#12121a",
        "cyan": "#00f0ff",
        "magenta": "#ff00aa",
        "green": "#00ff66",
        "yellow": "#f0ff00",
        "orange": "#ff6600",
        "red": "#ff3366",
        "text": "#e0e0e0",
    }
    
    def __init__(self, can_interface: Optional[CANInterface] = None):
        super().__init__()
        self.can_interface = can_interface or CANInterface(simulate=True)
        self.current_profile: Optional[VehicleProfile] = None
        self.current_seed: List[int] = []
        self.session_active = False
        self.security_unlocked = False
        self.pending_response = False
        self.response_timeout = QTimer()
        self.response_timeout.timeout.connect(self._handle_timeout)
        self.tester_present_timer = QTimer()
        self.tester_present_timer.timeout.connect(self._send_tester_present)
        
        self._init_ui()
        self._connect_signals()
        self._apply_theme()
        
        logger.info("KeyToolsTab initialized")
    
    def _init_ui(self):
        """Initialize the UI layout."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        
        # Header
        header = self._create_header()
        main_layout.addWidget(header)
        
        # Main content with sub-tabs
        content_tabs = QTabWidget()
        content_tabs.addTab(self._create_security_access_tab(), "[Lock] Security Access")
        content_tabs.addTab(self._create_key_programming_tab(), "[Key] Key Programming")
        content_tabs.addTab(self._create_quick_functions_tab(), "[Flash] Quick Functions")
        content_tabs.addTab(self._create_log_tab(), "[List] Log")
        main_layout.addWidget(content_tabs)
        
        # Status bar
        self.status_bar = QLabel("Ready")
        self.status_bar.setStyleSheet(f"color: {self.COLORS['cyan']}; padding: 5px;")
        main_layout.addWidget(self.status_bar)
        
        self.setLayout(main_layout)
    
    def _create_header(self) -> QWidget:
        """Create the header with vehicle selection."""
        group = QGroupBox("Vehicle Selection")
        layout = QHBoxLayout()
        
        # Vehicle profile selector
        layout.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(VEHICLE_PROFILES.keys())
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        layout.addWidget(self.profile_combo)
        
        # TX/RX ID display
        layout.addWidget(QLabel("TX:"))
        self.tx_id_edit = QLineEdit("7E0")
        self.tx_id_edit.setMaximumWidth(80)
        layout.addWidget(self.tx_id_edit)
        
        layout.addWidget(QLabel("RX:"))
        self.rx_id_edit = QLineEdit("7E8")
        self.rx_id_edit.setMaximumWidth(80)
        layout.addWidget(self.rx_id_edit)
        
        # Connection status
        self.connection_indicator = QLabel("o")
        self.connection_indicator.setToolTip("Connection Status")
        layout.addWidget(self.connection_indicator)
        
        layout.addStretch()
        group.setLayout(layout)
        return group
    
    def _create_security_access_tab(self) -> QWidget:
        """Create the security access workflow tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Session Control
        session_group = QGroupBox("Session Control")
        session_layout = QHBoxLayout()
        
        self.session_combo = QComboBox()
        self.session_combo.addItems([
            "01 - Default Session",
            "02 - Programming Session",
            "03 - Extended Diagnostic",
        ])
        self.session_combo.setCurrentIndex(1)
        session_layout.addWidget(QLabel("Session:"))
        session_layout.addWidget(self.session_combo)
        
        self.start_session_btn = QPushButton("▶ Start Session")
        self.start_session_btn.clicked.connect(self._start_diagnostic_session)
        session_layout.addWidget(self.start_session_btn)
        
        self.session_status = QLabel("o No Session")
        session_layout.addWidget(self.session_status)
        
        session_layout.addStretch()
        session_group.setLayout(session_layout)
        layout.addWidget(session_group)
        
        # Security Access
        security_group = QGroupBox("Security Access (0x27)")
        security_layout = QGridLayout()
        
        # Security level selector
        security_layout.addWidget(QLabel("Security Level:"), 0, 0)
        self.security_level_combo = QComboBox()
        self.security_level_combo.addItems([
            "01 - Standard",
            "03 - Programming", 
            "05 - Extended",
            "11 - FCA Specific",
            "21 - GM Specific",
        ])
        security_layout.addWidget(self.security_level_combo, 0, 1)
        
        # Request Seed button
        self.request_seed_btn = QPushButton("1. Request Seed")
        self.request_seed_btn.clicked.connect(self._request_seed)
        security_layout.addWidget(self.request_seed_btn, 0, 2)
        
        # Seed display
        security_layout.addWidget(QLabel("Seed Received:"), 1, 0)
        self.seed_display = QLineEdit()
        self.seed_display.setReadOnly(True)
        self.seed_display.setPlaceholderText("Waiting for seed...")
        security_layout.addWidget(self.seed_display, 1, 1)
        
        # Key input
        security_layout.addWidget(QLabel("Key to Send:"), 2, 0)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Enter calculated key (hex)")
        security_layout.addWidget(self.key_input, 2, 1)
        
        # Send Key button
        self.send_key_btn = QPushButton("2. Send Key")
        self.send_key_btn.clicked.connect(self._send_key)
        self.send_key_btn.setEnabled(False)
        security_layout.addWidget(self.send_key_btn, 2, 2)
        
        # Security status
        self.security_status = QLabel("[Locked] Locked")
        self.security_status.setStyleSheet(f"color: {self.COLORS['red']}; font-weight: bold;")
        security_layout.addWidget(self.security_status, 3, 0, 1, 3)
        
        security_group.setLayout(security_layout)
        layout.addWidget(security_group)
        
        # Common Security Algorithms Info
        algo_group = QGroupBox("Security Algorithm Reference")
        algo_layout = QVBoxLayout()
        algo_info = QTextEdit()
        algo_info.setReadOnly(True)
        algo_info.setMaximumHeight(150)
        algo_info.setHtml("""
            <style>body { font-family: Consolas; font-size: 11px; }</style>
            <b>Common Seed/Key Algorithms:</b><br><br>
            <b>FCA (Chrysler/Dodge/Jeep):</b> XOR-based, varies by model year<br>
            <b>GM:</b> Usually XOR with rolling addition<br>
            <b>Toyota:</b> Bitwise operations with lookup tables<br>
            <b>Ford:</b> CRC-based calculations<br><br>
            <i>Note: Actual algorithms require manufacturer-specific tools or documentation.
            This tool displays the seed for use with external key calculators.</i>
        """)
        algo_layout.addWidget(algo_info)
        algo_group.setLayout(algo_layout)
        layout.addWidget(algo_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_key_programming_tab(self) -> QWidget:
        """Create the key programming interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Key Slot Status
        slot_group = QGroupBox("Key Slot Status")
        slot_layout = QVBoxLayout()
        
        # Key count display
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Programmed Keys:"))
        self.key_count_label = QLabel("--")
        self.key_count_label.setStyleSheet(f"color: {self.COLORS['cyan']}; font-size: 24px; font-weight: bold;")
        count_layout.addWidget(self.key_count_label)
        count_layout.addWidget(QLabel("/ 8 slots"))
        
        self.read_key_count_btn = QPushButton("[Refresh] Read Key Count")
        self.read_key_count_btn.clicked.connect(self._read_key_count)
        count_layout.addWidget(self.read_key_count_btn)
        count_layout.addStretch()
        slot_layout.addLayout(count_layout)
        
        # Key slots table
        self.key_slots_table = QTableWidget(8, 4)
        self.key_slots_table.setHorizontalHeaderLabels(["Slot", "Status", "Transponder ID", "Last Seen"])
        self.key_slots_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.key_slots_table.setMaximumHeight(250)
        for i in range(8):
            self.key_slots_table.setItem(i, 0, QTableWidgetItem(f"Key {i+1}"))
            self.key_slots_table.setItem(i, 1, QTableWidgetItem("Unknown"))
            self.key_slots_table.setItem(i, 2, QTableWidgetItem("--"))
            self.key_slots_table.setItem(i, 3, QTableWidgetItem("--"))
        slot_layout.addWidget(self.key_slots_table)
        
        slot_group.setLayout(slot_layout)
        layout.addWidget(slot_group)
        
        # Key Programming Actions
        action_group = QGroupBox("Programming Actions")
        action_layout = QGridLayout()
        
        self.add_key_btn = QPushButton("[+] Add New Key")
        self.add_key_btn.clicked.connect(self._add_key)
        action_layout.addWidget(self.add_key_btn, 0, 0)
        
        self.delete_key_btn = QPushButton("[Del] Delete Key")
        self.delete_key_btn.clicked.connect(self._delete_key)
        action_layout.addWidget(self.delete_key_btn, 0, 1)
        
        self.delete_all_btn = QPushButton("[!] Delete All Keys")
        self.delete_all_btn.clicked.connect(self._delete_all_keys)
        self.delete_all_btn.setStyleSheet(f"background-color: {self.COLORS['red']};")
        action_layout.addWidget(self.delete_all_btn, 0, 2)
        
        self.read_immo_btn = QPushButton("[Read] Read IMMO Data")
        self.read_immo_btn.clicked.connect(self._read_immo_data)
        action_layout.addWidget(self.read_immo_btn, 1, 0)
        
        self.backup_btn = QPushButton("[Save] Backup Key Data")
        self.backup_btn.clicked.connect(self._backup_key_data)
        action_layout.addWidget(self.backup_btn, 1, 1)
        
        self.restore_btn = QPushButton("[Open] Restore Key Data")
        self.restore_btn.clicked.connect(self._restore_key_data)
        action_layout.addWidget(self.restore_btn, 1, 2)
        
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_quick_functions_tab(self) -> QWidget:
        """Create quick access functions tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # VIN Functions
        vin_group = QGroupBox("VIN Functions")
        vin_layout = QHBoxLayout()
        
        self.read_vin_btn = QPushButton("[Read] Read VIN")
        self.read_vin_btn.clicked.connect(self._read_vin)
        vin_layout.addWidget(self.read_vin_btn)
        
        self.vin_display = QLineEdit()
        self.vin_display.setReadOnly(True)
        self.vin_display.setPlaceholderText("VIN will appear here...")
        vin_layout.addWidget(self.vin_display)
        
        vin_group.setLayout(vin_layout)
        layout.addWidget(vin_group)
        
        # Quick UDS Commands
        quick_group = QGroupBox("Quick UDS Commands")
        quick_layout = QGridLayout()
        
        commands = [
            ("[Refresh] ECU Reset (Soft)", self._ecu_reset_soft),
            ("[Flash] ECU Reset (Hard)", self._ecu_reset_hard),
            ("[Heart] Tester Present", self._send_tester_present_once),
            ("[Search] Read All DIDs", self._read_all_dids),
            ("[List] Read DTCs", self._read_dtcs),
            ("[Clear] Clear DTCs", self._clear_dtcs),
        ]
        
        for i, (text, callback) in enumerate(commands):
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            quick_layout.addWidget(btn, i // 3, i % 3)
        
        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)
        
        # Custom UDS Frame
        custom_group = QGroupBox("Send Custom UDS Frame")
        custom_layout = QHBoxLayout()
        
        custom_layout.addWidget(QLabel("Data (hex):"))
        self.custom_frame_input = QLineEdit()
        self.custom_frame_input.setPlaceholderText("e.g., 22 F1 90 (Read VIN)")
        custom_layout.addWidget(self.custom_frame_input)
        
        self.send_custom_btn = QPushButton("[Up] Send")
        self.send_custom_btn.clicked.connect(self._send_custom_frame)
        custom_layout.addWidget(self.send_custom_btn)
        
        custom_group.setLayout(custom_layout)
        layout.addWidget(custom_group)
        
        # Response display
        response_group = QGroupBox("Response")
        response_layout = QVBoxLayout()
        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)
        self.response_display.setMaximumHeight(150)
        response_layout.addWidget(self.response_display)
        response_group.setLayout(response_layout)
        layout.addWidget(response_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_log_tab(self) -> QWidget:
        """Create the communication log tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Log controls
        controls = QHBoxLayout()
        
        self.clear_log_btn = QPushButton("[Clear] Clear Log")
        self.clear_log_btn.clicked.connect(self._clear_log)
        controls.addWidget(self.clear_log_btn)
        
        self.export_log_btn = QPushButton("[Save] Export Log")
        self.export_log_btn.clicked.connect(self._export_log)
        controls.addWidget(self.export_log_btn)
        
        self.auto_scroll_check = QPushButton("📜 Auto-Scroll: ON")
        self.auto_scroll_check.setCheckable(True)
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.clicked.connect(self._toggle_auto_scroll)
        controls.addWidget(self.auto_scroll_check)
        
        controls.addStretch()
        layout.addLayout(controls)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_display)
        
        widget.setLayout(layout)
        return widget
    
    def _connect_signals(self):
        """Connect signals to slots."""
        if self.can_interface:
            self.can_interface.frame_received.connect(self._handle_frame)
            self.can_interface.connection_changed.connect(self._update_connection_status)
    
    def _apply_theme(self):
        """Apply CyberNinja dark theme."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.COLORS['bg_dark']};
                color: {self.COLORS['text']};
                font-family: Consolas, monospace;
            }}
            QGroupBox {{
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                color: {self.COLORS['cyan']};
                subcontrol-origin: margin;
                left: 10px;
            }}
            QPushButton {{
                background-color: {self.COLORS['bg_panel']};
                border: 1px solid {self.COLORS['cyan']}60;
                border-radius: 5px;
                padding: 8px 15px;
                color: {self.COLORS['cyan']};
            }}
            QPushButton:hover {{
                background-color: {self.COLORS['cyan']};
                color: {self.COLORS['bg_dark']};
            }}
            QPushButton:disabled {{
                background-color: #333;
                color: #666;
                border-color: #444;
            }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: {self.COLORS['bg_panel']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                padding: 5px;
                color: {self.COLORS['text']};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {self.COLORS['cyan']};
            }}
            QTableWidget {{
                background-color: {self.COLORS['bg_panel']};
                gridline-color: {self.COLORS['cyan']}30;
                border: 1px solid {self.COLORS['cyan']}40;
            }}
            QTableWidget::item {{
                padding: 5px;
            }}
            QHeaderView::section {{
                background-color: {self.COLORS['bg_dark']};
                color: {self.COLORS['cyan']};
                border: none;
                padding: 5px;
            }}
            QTextEdit {{
                background-color: {self.COLORS['bg_panel']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
            }}
            QProgressBar {{
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {self.COLORS['cyan']};
            }}
            QTabWidget::pane {{
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: {self.COLORS['bg_panel']};
                color: {self.COLORS['text']};
                padding: 8px 15px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {self.COLORS['cyan']};
                color: {self.COLORS['bg_dark']};
            }}
        """)
    
    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------
    def _on_profile_changed(self, profile_name: str):
        """Handle vehicle profile change."""
        self.current_profile = VEHICLE_PROFILES.get(profile_name)
        if self.current_profile:
            self.tx_id_edit.setText(f"{self.current_profile.tx_id:03X}")
            self.rx_id_edit.setText(f"{self.current_profile.rx_id:03X}")
            self._log(f"Profile changed: {profile_name}")
    
    def _handle_frame(self, frame: CANFrame):
        """Handle incoming CAN frame."""
        rx_id = self.rx_id_edit.text().upper()
        if frame.can_id.upper() != rx_id:
            return
        
        self._log(f"RX: {frame.can_id} [{' '.join(f'{b:02X}' for b in frame.data)}]", "rx")
        
        if not frame.data:
            return
        
        sid = frame.data[0]
        
        # Handle positive responses
        if sid == UDS.SECURITY_ACCESS + 0x40:  # 0x67
            self._handle_security_response(frame.data)
        elif sid == UDS.DIAGNOSTIC_SESSION + 0x40:  # 0x50
            self._handle_session_response(frame.data)
        elif sid == UDS.READ_DATA + 0x40:  # 0x62
            self._handle_read_response(frame.data)
        elif sid == UDS.NEGATIVE_RESPONSE:  # 0x7F
            self._handle_negative_response(frame.data)
    
    def _handle_security_response(self, data: List[int]):
        """Handle security access response."""
        if len(data) < 2:
            return
        
        sub_func = data[1]
        
        # Seed response (odd sub-function)
        if sub_func % 2 == 1 and len(data) >= 4:
            self.current_seed = data[2:]
            seed_hex = ' '.join(f'{b:02X}' for b in self.current_seed)
            self.seed_display.setText(seed_hex)
            self.send_key_btn.setEnabled(True)
            self._log(f"Seed received: {seed_hex}", "success")
        
        # Key accepted (even sub-function)
        elif sub_func % 2 == 0:
            self.security_unlocked = True
            self.security_status.setText("[Unlock] UNLOCKED")
            self.security_status.setStyleSheet(f"color: {self.COLORS['green']}; font-weight: bold;")
            self._log("Security access GRANTED!", "success")
    
    def _handle_session_response(self, data: List[int]):
        """Handle diagnostic session response."""
        self.session_active = True
        self.session_status.setText("* Session Active")
        self.session_status.setStyleSheet(f"color: {self.COLORS['green']};")
        
        # Start tester present timer
        self.tester_present_timer.start(2000)  # Send every 2 seconds
        self._log("Diagnostic session started", "success")
    
    def _handle_read_response(self, data: List[int]):
        """Handle read data response."""
        if len(data) < 4:
            return
        
        did = (data[1] << 8) | data[2]
        payload = data[3:]
        
        # VIN response
        if did == 0xF190:
            vin = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload)
            self.vin_display.setText(vin)
            self._log(f"VIN: {vin}", "success")
        
        # Key count response
        elif did in [0xF195, 0xF196, 0x00B5]:
            if payload:
                count = payload[0]
                self.key_count_label.setText(str(count))
                self._log(f"Key count: {count}", "success")
        
        # Generic response
        else:
            hex_data = ' '.join(f'{b:02X}' for b in payload)
            self.response_display.append(f"DID {did:04X}: {hex_data}")
    
    def _handle_negative_response(self, data: List[int]):
        """Handle negative response."""
        if len(data) < 3:
            return
        
        service = data[1]
        nrc = data[2]
        nrc_desc = NRC_DESCRIPTIONS.get(nrc, f"Unknown (0x{nrc:02X})")
        
        self._log(f"Negative Response: Service 0x{service:02X}, NRC: {nrc_desc}", "error")
        
        # Handle specific NRCs
        if nrc == 0x35:  # Invalid key
            self.security_status.setText("[Locked] Invalid Key!")
            self.security_status.setStyleSheet(f"color: {self.COLORS['red']}; font-weight: bold;")
        elif nrc == 0x36:  # Exceeded attempts
            self.security_status.setText("[Locked] Locked Out!")
            self.security_status.setStyleSheet(f"color: {self.COLORS['red']}; font-weight: bold;")
            QMessageBox.warning(self, "Security Lockout", 
                "Maximum security access attempts exceeded.\nWait or cycle ignition.")
    
    def _handle_timeout(self):
        """Handle response timeout."""
        self.response_timeout.stop()
        self.pending_response = False
        self._log("Response timeout", "warning")
    
    def _update_connection_status(self, connected: bool):
        """Update connection indicator."""
        if connected:
            self.connection_indicator.setText("*")
            self.connection_indicator.setStyleSheet(f"color: {self.COLORS['green']};")
        else:
            self.connection_indicator.setText("*")
            self.connection_indicator.setStyleSheet(f"color: {self.COLORS['red']};")
    
    # -------------------------------------------------------------------------
    # UDS Command Functions
    # -------------------------------------------------------------------------
    def _send_uds_frame(self, data: List[int]):
        """Send a UDS frame."""
        try:
            tx_id = self.tx_id_edit.text().upper()
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            frame = CANFrame(timestamp, tx_id, data, Direction.TX)
            
            self._log(f"TX: {tx_id} [{' '.join(f'{b:02X}' for b in data)}]", "tx")
            
            if self.can_interface.send_frame(frame):
                self.response_timeout.start(3000)  # 3 second timeout
                self.pending_response = True
            else:
                self._log("Failed to send frame", "error")
        except Exception as e:
            self._log(f"Error sending frame: {e}", "error")
    
    def _start_diagnostic_session(self):
        """Start a diagnostic session."""
        session_type = self.session_combo.currentIndex() + 1
        self._send_uds_frame([UDS.DIAGNOSTIC_SESSION, session_type])
    
    def _request_seed(self):
        """Request security seed."""
        level_text = self.security_level_combo.currentText()
        level = int(level_text.split(" - ")[0], 16)
        self._send_uds_frame([UDS.SECURITY_ACCESS, level])
    
    def _send_key(self):
        """Send security key."""
        key_text = self.key_input.text().replace(" ", "")
        try:
            key_bytes = [int(key_text[i:i+2], 16) for i in range(0, len(key_text), 2)]
            level_text = self.security_level_combo.currentText()
            level = int(level_text.split(" - ")[0], 16) + 1  # Key level is seed level + 1
            self._send_uds_frame([UDS.SECURITY_ACCESS, level] + key_bytes)
        except ValueError:
            self._log("Invalid key format", "error")
    
    def _read_key_count(self):
        """Read number of programmed keys."""
        if self.current_profile:
            did = self.current_profile.key_count_did
        else:
            did = 0xF196
        self._send_uds_frame([UDS.READ_DATA, (did >> 8) & 0xFF, did & 0xFF])
    
    def _read_vin(self):
        """Read vehicle VIN."""
        self._send_uds_frame([UDS.READ_DATA, 0xF1, 0x90])
    
    def _send_tester_present(self):
        """Send tester present to keep session alive."""
        if self.session_active:
            self._send_uds_frame([UDS.TESTER_PRESENT, 0x00])
    
    def _send_tester_present_once(self):
        """Send single tester present."""
        self._send_uds_frame([UDS.TESTER_PRESENT, 0x00])
    
    def _ecu_reset_soft(self):
        """Perform soft ECU reset."""
        self._send_uds_frame([UDS.ECU_RESET, 0x01])
    
    def _ecu_reset_hard(self):
        """Perform hard ECU reset."""
        if QMessageBox.question(self, "Confirm", "Hard reset will disconnect. Continue?") == QMessageBox.Yes:
            self._send_uds_frame([UDS.ECU_RESET, 0x03])
    
    def _read_all_dids(self):
        """Read common DIDs."""
        common_dids = [0xF190, 0xF187, 0xF18B, 0xF191, 0xF195]
        for did in common_dids:
            self._send_uds_frame([UDS.READ_DATA, (did >> 8) & 0xFF, did & 0xFF])
    
    def _read_dtcs(self):
        """Read diagnostic trouble codes."""
        self._send_uds_frame([0x19, 0x02, 0xFF])  # Read all DTCs
    
    def _clear_dtcs(self):
        """Clear diagnostic trouble codes."""
        if QMessageBox.question(self, "Confirm", "Clear all DTCs?") == QMessageBox.Yes:
            self._send_uds_frame([0x14, 0xFF, 0xFF, 0xFF])
    
    def _send_custom_frame(self):
        """Send custom UDS frame."""
        hex_text = self.custom_frame_input.text().replace(" ", "")
        try:
            data = [int(hex_text[i:i+2], 16) for i in range(0, len(hex_text), 2)]
            self._send_uds_frame(data)
        except ValueError:
            self._log("Invalid hex format", "error")
    
    # -------------------------------------------------------------------------
    # Key Programming Functions (Placeholders)
    # -------------------------------------------------------------------------
    def _add_key(self):
        """Add new key - requires security access."""
        if not self.security_unlocked:
            QMessageBox.warning(self, "Security Required", 
                "Please unlock security access first.")
            return
        self._log("Add key: Feature requires manufacturer-specific implementation", "warning")
    
    def _delete_key(self):
        """Delete selected key."""
        if not self.security_unlocked:
            QMessageBox.warning(self, "Security Required", 
                "Please unlock security access first.")
            return
        self._log("Delete key: Feature requires manufacturer-specific implementation", "warning")
    
    def _delete_all_keys(self):
        """Delete all keys - dangerous operation."""
        QMessageBox.warning(self, "Not Implemented", 
            "This dangerous operation requires manufacturer-specific implementation.")
    
    def _read_immo_data(self):
        """Read immobilizer data."""
        self._log("Reading IMMO data...", "info")
        # Read common IMMO-related DIDs
        immo_dids = [0xF195, 0xF196, 0xF197, 0xF198]
        for did in immo_dids:
            self._send_uds_frame([UDS.READ_DATA, (did >> 8) & 0xFF, did & 0xFF])
    
    def _backup_key_data(self):
        """Backup key programming data."""
        self._log("Backup: Feature requires security access and specific DID support", "warning")
    
    def _restore_key_data(self):
        """Restore key programming data."""
        self._log("Restore: Feature requires security access and specific DID support", "warning")
    
    # -------------------------------------------------------------------------
    # Log Functions
    # -------------------------------------------------------------------------
    def _log(self, message: str, level: str = "info"):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        colors = {
            "info": self.COLORS['text'],
            "success": self.COLORS['green'],
            "warning": self.COLORS['yellow'],
            "error": self.COLORS['red'],
            "tx": self.COLORS['magenta'],
            "rx": self.COLORS['cyan'],
        }
        color = colors.get(level, self.COLORS['text'])
        
        html = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.log_display.append(html)
        
        if self.auto_scroll_check.isChecked():
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()
            )
        
        # Update status bar
        self.status_bar.setText(message)
        self.status_bar.setStyleSheet(f"color: {color}; padding: 5px;")
    
    def _clear_log(self):
        """Clear the log display."""
        self.log_display.clear()
    
    def _export_log(self):
        """Export log to file."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt)")
        if path:
            with open(path, 'w') as f:
                f.write(self.log_display.toPlainText())
            self._log(f"Log exported to {path}", "success")
    
    def _toggle_auto_scroll(self):
        """Toggle auto-scroll."""
        if self.auto_scroll_check.isChecked():
            self.auto_scroll_check.setText("📜 Auto-Scroll: ON")
        else:
            self.auto_scroll_check.setText("📜 Auto-Scroll: OFF")
    
    def set_can_interface(self, interface: CANInterface):
        """Set the CAN interface (called from main window)."""
        self.can_interface = interface
        self._connect_signals()


# ----------------------------------------------------------------------------------
# Test
# ----------------------------------------------------------------------------------
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    tab = KeyToolsTab()
    tab.resize(1000, 700)
    tab.show()
    sys.exit(app.exec_())
