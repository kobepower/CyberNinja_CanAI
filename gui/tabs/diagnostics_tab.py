# gui/tabs/diagnostics_tab.py

"""
Description:
Vehicle diagnostics tab - DTC reading/clearing, VIN scanning, module discovery,
and general diagnostic functions for locksmiths.
"""

# ----------------------------------------------------------------------------------
# 1) Imports
# ----------------------------------------------------------------------------------
import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QMessageBox, QTabWidget, QGridLayout, QHeaderView,
    QTreeWidget, QTreeWidgetItem, QSplitter, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

from backend.can_interface import CANInterface, CANFrame, Direction

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# 2) DTC Database
# ----------------------------------------------------------------------------------
DTC_DATABASE = {
    # Powertrain (P codes)
    "P0000": "No Fault",
    "P0100": "Mass Air Flow Circuit",
    "P0101": "MAF Circuit Range/Performance",
    "P0102": "MAF Circuit Low",
    "P0103": "MAF Circuit High",
    "P0110": "Intake Air Temperature Circuit",
    "P0115": "Engine Coolant Temperature Circuit",
    "P0120": "Throttle Position Sensor A Circuit",
    "P0130": "O2 Sensor Circuit Bank 1 Sensor 1",
    "P0171": "System Too Lean Bank 1",
    "P0172": "System Too Rich Bank 1",
    "P0300": "Random/Multiple Cylinder Misfire",
    "P0301": "Cylinder 1 Misfire Detected",
    "P0302": "Cylinder 2 Misfire Detected",
    "P0303": "Cylinder 3 Misfire Detected",
    "P0304": "Cylinder 4 Misfire Detected",
    "P0420": "Catalyst System Efficiency Below Threshold",
    "P0440": "Evaporative Emission System",
    "P0500": "Vehicle Speed Sensor A",
    "P0505": "Idle Air Control System",
    "P0600": "Serial Communication Link",
    "P0700": "Transmission Control System",
    
    # Body (B codes)
    "B0001": "Driver Frontal Stage 1 Deployment Control",
    "B0100": "Electronic Frontal Sensor 1",
    "B1000": "ECU Malfunction",
    "B1200": "Climate Control Circuit",
    "B1318": "Battery Voltage Low",
    "B1342": "ECU Damaged/Defective",
    "B1600": "PATS Received Incorrect Key",
    "B1601": "PATS Received Invalid Format",
    "B1602": "PATS Invalid Key Detected",
    "B2139": "Key In Ignition Input Circuit Short",
    "B2431": "Key In Ignition Input Circuit Failure",
    
    # Chassis (C codes)
    "C0000": "Vehicle Speed Information Circuit",
    "C0035": "Left Front Wheel Speed Sensor",
    "C0040": "Right Front Wheel Speed Sensor",
    "C0045": "Left Rear Wheel Speed Sensor",
    "C0050": "Right Rear Wheel Speed Sensor",
    "C1095": "ABS Hydraulic Pump Motor Circuit",
    
    # Network (U codes)
    "U0001": "High Speed CAN Communication Bus",
    "U0100": "Lost Communication With ECM/PCM",
    "U0101": "Lost Communication With TCM",
    "U0121": "Lost Communication With ABS",
    "U0140": "Lost Communication With BCM",
    "U0155": "Lost Communication With Cluster",
    "U0164": "Lost Communication With HVAC",
    "U0184": "Lost Communication With Radio",
    "U0401": "Invalid Data Received From ECM",
    "U1000": "CAN Bus Off",
}

# Common ECU addresses
ECU_ADDRESSES = {
    "Engine (PCM/ECM)": (0x7E0, 0x7E8),
    "Transmission (TCM)": (0x7E1, 0x7E9),
    "ABS/ESP": (0x7E2, 0x7EA),
    "Airbag (SRS)": (0x7E3, 0x7EB),
    "Body Control (BCM)": (0x7E4, 0x7EC),
    "Instrument Cluster": (0x7E5, 0x7ED),
    "HVAC": (0x7E6, 0x7EE),
    "Steering (EPS)": (0x7E7, 0x7EF),
}

# ----------------------------------------------------------------------------------
# 3) DiagnosticsTab Class
# ----------------------------------------------------------------------------------
class DiagnosticsTab(QWidget):
    """Vehicle diagnostics interface for reading DTCs and module scanning."""
    
    status_updated = pyqtSignal(str, str)
    
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
        self.discovered_modules: Dict[str, dict] = {}
        self.stored_dtcs: List[dict] = []
        self.scan_in_progress = False
        self.current_scan_index = 0
        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self._scan_next_module)
        
        self._init_ui()
        self._connect_signals()
        self._apply_theme()
        
        logger.info("DiagnosticsTab initialized")
    
    def _init_ui(self):
        """Initialize UI components."""
        main_layout = QVBoxLayout()
        
        # Create sub-tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_dtc_tab(), "[Search] DTC Reader")
        tabs.addTab(self._create_module_scan_tab(), "[Signal] Module Scanner")
        tabs.addTab(self._create_vehicle_info_tab(), "🚗 Vehicle Info")
        tabs.addTab(self._create_live_data_tab(), "[Chart] Live Data")
        main_layout.addWidget(tabs)
        
        # Status bar
        self.status_bar = QLabel("Ready")
        self.status_bar.setStyleSheet(f"color: {self.COLORS['cyan']}; padding: 5px;")
        main_layout.addWidget(self.status_bar)
        
        self.setLayout(main_layout)
    
    def _create_dtc_tab(self) -> QWidget:
        """Create DTC reading/clearing interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Controls
        control_group = QGroupBox("DTC Controls")
        control_layout = QHBoxLayout()
        
        control_layout.addWidget(QLabel("Module:"))
        self.module_combo = QComboBox()
        self.module_combo.addItems(ECU_ADDRESSES.keys())
        control_layout.addWidget(self.module_combo)
        
        self.read_dtc_btn = QPushButton("[Search] Read DTCs")
        self.read_dtc_btn.clicked.connect(self._read_dtcs)
        control_layout.addWidget(self.read_dtc_btn)
        
        self.read_all_btn = QPushButton("[List] Read All Modules")
        self.read_all_btn.clicked.connect(self._read_all_dtcs)
        control_layout.addWidget(self.read_all_btn)
        
        self.clear_dtc_btn = QPushButton("[Clear] Clear DTCs")
        self.clear_dtc_btn.clicked.connect(self._clear_dtcs)
        control_layout.addWidget(self.clear_dtc_btn)
        
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # DTC type selector
        type_layout = QHBoxLayout()
        self.dtc_stored_check = QCheckBox("Stored")
        self.dtc_stored_check.setChecked(True)
        self.dtc_pending_check = QCheckBox("Pending")
        self.dtc_pending_check.setChecked(True)
        self.dtc_permanent_check = QCheckBox("Permanent")
        type_layout.addWidget(QLabel("DTC Types:"))
        type_layout.addWidget(self.dtc_stored_check)
        type_layout.addWidget(self.dtc_pending_check)
        type_layout.addWidget(self.dtc_permanent_check)
        type_layout.addStretch()
        layout.addLayout(type_layout)
        
        # Progress bar
        self.dtc_progress = QProgressBar()
        self.dtc_progress.setVisible(False)
        layout.addWidget(self.dtc_progress)
        
        # DTC results table
        result_group = QGroupBox("Diagnostic Trouble Codes")
        result_layout = QVBoxLayout()
        
        self.dtc_table = QTableWidget()
        self.dtc_table.setColumnCount(5)
        self.dtc_table.setHorizontalHeaderLabels(["Module", "DTC", "Description", "Status", "Freeze Frame"])
        self.dtc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dtc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dtc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        result_layout.addWidget(self.dtc_table)
        
        # Summary
        summary_layout = QHBoxLayout()
        self.dtc_count_label = QLabel("Total DTCs: 0")
        self.dtc_count_label.setStyleSheet(f"color: {self.COLORS['cyan']}; font-weight: bold;")
        summary_layout.addWidget(self.dtc_count_label)
        
        self.export_dtc_btn = QPushButton("[Save] Export")
        self.export_dtc_btn.clicked.connect(self._export_dtcs)
        summary_layout.addWidget(self.export_dtc_btn)
        
        summary_layout.addStretch()
        result_layout.addLayout(summary_layout)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        widget.setLayout(layout)
        return widget
    
    def _create_module_scan_tab(self) -> QWidget:
        """Create module scanner interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Scan controls
        scan_group = QGroupBox("Module Scanner")
        scan_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("[Search] Scan All Modules")
        self.scan_btn.clicked.connect(self._start_module_scan)
        scan_layout.addWidget(self.scan_btn)
        
        self.quick_scan_btn = QPushButton("[Flash] Quick Scan (Common)")
        self.quick_scan_btn.clicked.connect(self._quick_scan)
        scan_layout.addWidget(self.quick_scan_btn)
        
        self.stop_scan_btn = QPushButton("[Stop] Stop")
        self.stop_scan_btn.clicked.connect(self._stop_scan)
        self.stop_scan_btn.setEnabled(False)
        scan_layout.addWidget(self.stop_scan_btn)
        
        scan_layout.addStretch()
        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)
        
        # Scan range
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("Scan Range:"))
        self.scan_start = QLineEdit("700")
        self.scan_start.setMaximumWidth(80)
        range_layout.addWidget(self.scan_start)
        range_layout.addWidget(QLabel("to"))
        self.scan_end = QLineEdit("7FF")
        self.scan_end.setMaximumWidth(80)
        range_layout.addWidget(self.scan_end)
        range_layout.addStretch()
        layout.addLayout(range_layout)
        
        # Progress
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        layout.addWidget(self.scan_progress)
        
        # Results tree
        result_group = QGroupBox("Discovered Modules")
        result_layout = QVBoxLayout()
        
        self.module_tree = QTreeWidget()
        self.module_tree.setHeaderLabels(["Module", "TX ID", "RX ID", "Response", "Info"])
        self.module_tree.setColumnCount(5)
        self.module_tree.itemClicked.connect(self._on_module_selected)
        result_layout.addWidget(self.module_tree)
        
        # Module details
        self.module_details = QTextEdit()
        self.module_details.setReadOnly(True)
        self.module_details.setMaximumHeight(150)
        result_layout.addWidget(self.module_details)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        widget.setLayout(layout)
        return widget
    
    def _create_vehicle_info_tab(self) -> QWidget:
        """Create vehicle information display."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Read controls
        control_group = QGroupBox("Read Vehicle Information")
        control_layout = QHBoxLayout()
        
        self.read_info_btn = QPushButton("[Read] Read All Info")
        self.read_info_btn.clicked.connect(self._read_vehicle_info)
        control_layout.addWidget(self.read_info_btn)
        
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Vehicle info display
        info_group = QGroupBox("Vehicle Information")
        info_layout = QGridLayout()
        
        info_fields = [
            ("VIN:", "vin"),
            ("Make:", "make"),
            ("Model:", "model"),
            ("Year:", "year"),
            ("ECU Part Number:", "ecu_part"),
            ("ECU Serial:", "ecu_serial"),
            ("Software Version:", "sw_version"),
            ("Hardware Version:", "hw_version"),
            ("Calibration ID:", "cal_id"),
            ("Odometer:", "odometer"),
        ]
        
        self.info_fields = {}
        for i, (label, key) in enumerate(info_fields):
            row = i // 2
            col = (i % 2) * 2
            info_layout.addWidget(QLabel(label), row, col)
            field = QLineEdit()
            field.setReadOnly(True)
            self.info_fields[key] = field
            info_layout.addWidget(field, row, col + 1)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Raw data display
        raw_group = QGroupBox("Raw Data")
        raw_layout = QVBoxLayout()
        self.raw_display = QTextEdit()
        self.raw_display.setReadOnly(True)
        self.raw_display.setFont(QFont("Consolas", 10))
        raw_layout.addWidget(self.raw_display)
        raw_group.setLayout(raw_layout)
        layout.addWidget(raw_group)
        
        widget.setLayout(layout)
        return widget
    
    def _create_live_data_tab(self) -> QWidget:
        """Create live data monitoring interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Controls
        control_group = QGroupBox("Live Data")
        control_layout = QHBoxLayout()
        
        self.start_live_btn = QPushButton("> Start Monitoring")
        self.start_live_btn.clicked.connect(self._toggle_live_data)
        control_layout.addWidget(self.start_live_btn)
        
        control_layout.addWidget(QLabel("Refresh Rate:"))
        self.refresh_rate = QComboBox()
        self.refresh_rate.addItems(["100ms", "250ms", "500ms", "1000ms"])
        self.refresh_rate.setCurrentIndex(2)
        control_layout.addWidget(self.refresh_rate)
        
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Live data table
        self.live_table = QTableWidget()
        self.live_table.setColumnCount(5)
        self.live_table.setHorizontalHeaderLabels(["PID", "Name", "Value", "Unit", "Min/Max"])
        self.live_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.live_table)
        
        # Add some common PIDs
        pids = [
            ("0x05", "Coolant Temp", "--", "°C", "-40/215"),
            ("0x0C", "Engine RPM", "--", "rpm", "0/16383"),
            ("0x0D", "Vehicle Speed", "--", "km/h", "0/255"),
            ("0x0F", "Intake Air Temp", "--", "°C", "-40/215"),
            ("0x11", "Throttle Position", "--", "%", "0/100"),
            ("0x2F", "Fuel Level", "--", "%", "0/100"),
            ("0x42", "Battery Voltage", "--", "V", "0/65.535"),
        ]
        
        self.live_table.setRowCount(len(pids))
        for i, (pid, name, value, unit, range_str) in enumerate(pids):
            self.live_table.setItem(i, 0, QTableWidgetItem(pid))
            self.live_table.setItem(i, 1, QTableWidgetItem(name))
            self.live_table.setItem(i, 2, QTableWidgetItem(value))
            self.live_table.setItem(i, 3, QTableWidgetItem(unit))
            self.live_table.setItem(i, 4, QTableWidgetItem(range_str))
        
        widget.setLayout(layout)
        return widget
    
    def _connect_signals(self):
        """Connect CAN interface signals."""
        if self.can_interface:
            self.can_interface.frame_received.connect(self._handle_frame)
    
    def _apply_theme(self):
        """Apply dark theme."""
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
            QLineEdit, QComboBox {{
                background-color: {self.COLORS['bg_panel']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                padding: 5px;
                color: {self.COLORS['text']};
            }}
            QTableWidget, QTreeWidget {{
                background-color: {self.COLORS['bg_panel']};
                gridline-color: {self.COLORS['cyan']}30;
                border: 1px solid {self.COLORS['cyan']}40;
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
            }}
            QTabBar::tab {{
                background-color: {self.COLORS['bg_panel']};
                color: {self.COLORS['text']};
                padding: 8px 15px;
            }}
            QTabBar::tab:selected {{
                background-color: {self.COLORS['cyan']};
                color: {self.COLORS['bg_dark']};
            }}
            QCheckBox {{
                color: {self.COLORS['text']};
            }}
            QCheckBox::indicator {{
                border: 1px solid {self.COLORS['cyan']}60;
                background-color: {self.COLORS['bg_panel']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.COLORS['cyan']};
            }}
        """)
    
    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------
    def _handle_frame(self, frame: CANFrame):
        """Handle incoming CAN frame."""
        if not frame.data:
            return
        
        sid = frame.data[0]
        
        # DTC response (0x59 = positive response to 0x19)
        if sid == 0x59 and len(frame.data) >= 4:
            self._parse_dtc_response(frame)
        
        # Read data response (0x62)
        elif sid == 0x62 and len(frame.data) >= 4:
            self._parse_read_response(frame)
        
        # Tester present response (module alive)
        elif sid == 0x7E:
            self._handle_module_response(frame)
        
        # Session response
        elif sid == 0x50:
            self._handle_module_response(frame)
    
    def _parse_dtc_response(self, frame: CANFrame):
        """Parse DTC response frame."""
        data = frame.data
        # Format: 59 02 FF [DTC1_HI] [DTC1_LO] [STATUS] ...
        if len(data) < 6:
            return
        
        # Parse DTCs (3 bytes each: 2 bytes code + 1 byte status)
        for i in range(3, len(data) - 2, 3):
            dtc_hi = data[i]
            dtc_lo = data[i + 1]
            status = data[i + 2]
            
            # Convert to standard DTC format
            dtc_code = self._decode_dtc(dtc_hi, dtc_lo)
            description = DTC_DATABASE.get(dtc_code, "Unknown")
            status_text = self._decode_dtc_status(status)
            
            row = self.dtc_table.rowCount()
            self.dtc_table.insertRow(row)
            self.dtc_table.setItem(row, 0, QTableWidgetItem(self.module_combo.currentText()))
            self.dtc_table.setItem(row, 1, QTableWidgetItem(dtc_code))
            self.dtc_table.setItem(row, 2, QTableWidgetItem(description))
            self.dtc_table.setItem(row, 3, QTableWidgetItem(status_text))
            self.dtc_table.setItem(row, 4, QTableWidgetItem("--"))
            
            # Color code by status
            if "Active" in status_text:
                for col in range(5):
                    item = self.dtc_table.item(row, col)
                    if item:
                        item.setBackground(QColor(self.COLORS['red'] + "40"))
        
        self.dtc_count_label.setText(f"Total DTCs: {self.dtc_table.rowCount()}")
    
    def _decode_dtc(self, hi: int, lo: int) -> str:
        """Decode DTC bytes to standard format."""
        # First nibble determines type
        type_map = {0: 'P', 1: 'C', 2: 'B', 3: 'U'}
        dtc_type = type_map.get((hi >> 6) & 0x03, 'P')
        
        # Remaining is the number
        num = ((hi & 0x3F) << 8) | lo
        return f"{dtc_type}{num:04X}"
    
    def _decode_dtc_status(self, status: int) -> str:
        """Decode DTC status byte."""
        flags = []
        if status & 0x01:
            flags.append("Test Failed")
        if status & 0x02:
            flags.append("Pending")
        if status & 0x08:
            flags.append("Confirmed")
        if status & 0x20:
            flags.append("Active")
        return ", ".join(flags) if flags else "Inactive"
    
    def _parse_read_response(self, frame: CANFrame):
        """Parse read data response."""
        data = frame.data
        did = (data[1] << 8) | data[2]
        payload = data[3:]
        
        # VIN
        if did == 0xF190 and len(payload) >= 17:
            vin = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload[:17])
            self.info_fields['vin'].setText(vin)
        
        # ECU Part Number
        elif did == 0xF187:
            part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload)
            self.info_fields['ecu_part'].setText(part.strip())
        
        # Software Version
        elif did == 0xF189:
            sw = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload)
            self.info_fields['sw_version'].setText(sw.strip())
        
        # Display raw
        hex_data = ' '.join(f'{b:02X}' for b in payload)
        self.raw_display.append(f"DID 0x{did:04X}: {hex_data}")
    
    def _handle_module_response(self, frame: CANFrame):
        """Handle module response during scanning."""
        tx_id = int(frame.can_id, 16) - 8  # Response ID is usually TX + 8
        
        if self.scan_in_progress:
            # Module responded
            module_name = f"Module 0x{tx_id:03X}"
            for name, (tx, rx) in ECU_ADDRESSES.items():
                if tx == tx_id:
                    module_name = name
                    break
            
            item = QTreeWidgetItem([
                module_name,
                f"0x{tx_id:03X}",
                frame.can_id,
                "OK",
                ""
            ])
            self.module_tree.addTopLevelItem(item)
    
    def _on_module_selected(self, item: QTreeWidgetItem, column: int):
        """Handle module selection in tree."""
        tx_id = item.text(1)
        rx_id = item.text(2)
        self.module_details.setText(f"Selected: {item.text(0)}\nTX: {tx_id}\nRX: {rx_id}")
    
    # -------------------------------------------------------------------------
    # DTC Functions
    # -------------------------------------------------------------------------
    def _read_dtcs(self):
        """Read DTCs from selected module."""
        self.dtc_table.setRowCount(0)
        module_name = self.module_combo.currentText()
        tx_id, rx_id = ECU_ADDRESSES.get(module_name, (0x7E0, 0x7E8))
        
        # Send Read DTC Information request
        # Service 0x19, Sub-function 0x02 = reportDTCByStatusMask
        self._send_frame(tx_id, [0x19, 0x02, 0xFF])  # 0xFF = all DTCs
        self._update_status(f"Reading DTCs from {module_name}...")
    
    def _read_all_dtcs(self):
        """Read DTCs from all modules."""
        self.dtc_table.setRowCount(0)
        self.dtc_progress.setVisible(True)
        self.dtc_progress.setMaximum(len(ECU_ADDRESSES))
        self.dtc_progress.setValue(0)
        
        for i, (name, (tx_id, rx_id)) in enumerate(ECU_ADDRESSES.items()):
            self._send_frame(tx_id, [0x19, 0x02, 0xFF])
            self.dtc_progress.setValue(i + 1)
        
        self.dtc_progress.setVisible(False)
        self._update_status("DTC scan complete")
    
    def _clear_dtcs(self):
        """Clear DTCs from selected module."""
        if QMessageBox.question(self, "Confirm", "Clear all DTCs from selected module?") != QMessageBox.Yes:
            return
        
        module_name = self.module_combo.currentText()
        tx_id, rx_id = ECU_ADDRESSES.get(module_name, (0x7E0, 0x7E8))
        
        # Service 0x14 = Clear Diagnostic Information
        self._send_frame(tx_id, [0x14, 0xFF, 0xFF, 0xFF])
        self._update_status(f"Clearing DTCs from {module_name}...")
    
    def _export_dtcs(self):
        """Export DTC list to file."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export DTCs", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w') as f:
                f.write("Module,DTC,Description,Status,Freeze Frame\n")
                for row in range(self.dtc_table.rowCount()):
                    line = []
                    for col in range(5):
                        item = self.dtc_table.item(row, col)
                        line.append(item.text() if item else "")
                    f.write(",".join(line) + "\n")
            self._update_status(f"Exported to {path}")
    
    # -------------------------------------------------------------------------
    # Module Scan Functions
    # -------------------------------------------------------------------------
    def _start_module_scan(self):
        """Start full module scan."""
        self.module_tree.clear()
        self.scan_in_progress = True
        self.scan_btn.setEnabled(False)
        self.stop_scan_btn.setEnabled(True)
        
        try:
            start = int(self.scan_start.text(), 16)
            end = int(self.scan_end.text(), 16)
        except ValueError:
            start, end = 0x700, 0x7FF
        
        self.scan_range = list(range(start, end + 1))
        self.current_scan_index = 0
        
        self.scan_progress.setVisible(True)
        self.scan_progress.setMaximum(len(self.scan_range))
        self.scan_progress.setValue(0)
        
        self.scan_timer.start(50)  # 50ms between requests
    
    def _scan_next_module(self):
        """Scan next module in range."""
        if self.current_scan_index >= len(self.scan_range) or not self.scan_in_progress:
            self._stop_scan()
            return
        
        tx_id = self.scan_range[self.current_scan_index]
        self._send_frame(tx_id, [0x3E, 0x00])  # Tester Present
        
        self.scan_progress.setValue(self.current_scan_index + 1)
        self.current_scan_index += 1
    
    def _quick_scan(self):
        """Scan common ECU addresses only."""
        self.module_tree.clear()
        
        for name, (tx_id, rx_id) in ECU_ADDRESSES.items():
            self._send_frame(tx_id, [0x3E, 0x00])
        
        self._update_status("Quick scan complete")
    
    def _stop_scan(self):
        """Stop module scanning."""
        self.scan_timer.stop()
        self.scan_in_progress = False
        self.scan_btn.setEnabled(True)
        self.stop_scan_btn.setEnabled(False)
        self.scan_progress.setVisible(False)
        self._update_status("Scan stopped")
    
    # -------------------------------------------------------------------------
    # Vehicle Info Functions
    # -------------------------------------------------------------------------
    def _read_vehicle_info(self):
        """Read vehicle information DIDs."""
        tx_id = 0x7E0  # Engine ECU
        
        dids = [
            0xF190,  # VIN
            0xF187,  # Part Number
            0xF189,  # Software Version
            0xF18A,  # System Supplier ID
            0xF18B,  # ECU Manufacturing Date
            0xF191,  # Hardware Version
        ]
        
        for did in dids:
            self._send_frame(tx_id, [0x22, (did >> 8) & 0xFF, did & 0xFF])
        
        self._update_status("Reading vehicle info...")
    
    # -------------------------------------------------------------------------
    # Live Data Functions
    # -------------------------------------------------------------------------
    def _toggle_live_data(self):
        """Toggle live data monitoring."""
        # Placeholder - would need continuous polling
        self._update_status("Live data monitoring not yet implemented")
    
    # -------------------------------------------------------------------------
    # Helper Functions
    # -------------------------------------------------------------------------
    def _send_frame(self, tx_id: int, data: list):
        """Send a CAN frame."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        frame = CANFrame(timestamp, f"{tx_id:03X}", data, Direction.TX)
        self.can_interface.send_frame(frame)
    
    def _update_status(self, message: str):
        """Update status bar."""
        self.status_bar.setText(message)
    
    def set_can_interface(self, interface: CANInterface):
        """Set CAN interface from main window."""
        self.can_interface = interface
        self._connect_signals()


# ----------------------------------------------------------------------------------
# Test
# ----------------------------------------------------------------------------------
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    tab = DiagnosticsTab()
    tab.resize(1000, 700)
    tab.show()
    sys.exit(app.exec_())
