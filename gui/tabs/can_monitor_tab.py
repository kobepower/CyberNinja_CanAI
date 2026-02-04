# -*- coding: utf-8 -*-
# gui/tabs/can_monitor_tab.py


"""
Description:
Implements the CAN monitoring tab with real-time frame display, filtering, and transmission capabilities.
"""

# ----------------------------------------------------------------------------------
# 1) Imports & Initialization
# ----------------------------------------------------------------------------------
import os
import json
import logging
import re
import time
import csv
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

import serial.tools.list_ports

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QGroupBox, QFormLayout, QLineEdit,
    QPushButton, QComboBox, QHBoxLayout, QLabel, QStatusBar, QFileDialog,
    QMessageBox, QAbstractItemView, QStyledItemDelegate, QDialog, QSpinBox,
    QDoubleSpinBox, QDialogButtonBox, QCheckBox, QTextEdit, QSplitter, QShortcut
)
from PyQt5.QtCore import Qt, QSortFilterProxyModel, QAbstractTableModel, QModelIndex, pyqtSignal, QTimer, QObject
from PyQt5.QtGui import QKeySequence, QColor, QBrush, QFont, QValidator

from backend.can_interface import CANInterface, CANFrame, Direction
from utils.uds_decoder import decode_uds, DID_LOOKUP, load_did_config
from utils.hex_validator import HexValidator, HexBytesValidator


# Configure logging
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------------
# 2) Custom Models & Delegates
# ----------------------------------------------------------------------------------
class HexDelegate(QStyledItemDelegate):
    """Formats hex bytes for display in table cells."""
    def displayText(self, value, locale):
        if isinstance(value, list):
            return ' '.join(f"{b:02X}" for b in value)
        return str(value)


class CANTableModel(QAbstractTableModel):
    """Data model for storing and formatting CAN frames."""
    _headers = ["Timestamp", "CAN ID", "Data Bytes", "Direction", "UDS Decode"]
    
    def __init__(self, max_rows=1000):
        super().__init__()
        self.frames: List[Tuple[CANFrame, float, QColor]] = []
        self.max_rows = max_rows

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.frames)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Optional[object]:
        if not index.isValid():
            return None
        frame, frequency, color = self.frames[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 4:
                return decode_uds(frame) or ""
            return [frame.timestamp, frame.can_id, frame.data, frame.direction.value, ""][col]
        if role == Qt.UserRole:
            return frame
        if role == Qt.BackgroundRole:
            if frequency > CANMonitorTab.NOISY_THRESHOLD:
                return QBrush(QColor("orange"))
            return QBrush(color)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Optional[str]:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._headers[section]
        return None

    def add_frames(self, frames_with_freq_color: List[Tuple[CANFrame, float, QColor]]) -> None:
        if frames_with_freq_color:
            self.beginInsertRows(QModelIndex(), 0, len(frames_with_freq_color) - 1)
            self.frames[0:0] = frames_with_freq_color
            if len(self.frames) > self.max_rows:
                self.frames[self.max_rows:] = []
            self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self.frames.clear()
        self.endResetModel()


# ----------------------------------------------------------------------------------
# 3) Filter Proxy Model
# ----------------------------------------------------------------------------------
class CANFilterProxyModel(QSortFilterProxyModel):
    """Handles row filtering based on CAN ID, direction, and search text."""
    def __init__(self):
        super().__init__()
        self.id_filter = ""
        self.dir_filter: Optional[Direction] = None
        self.search_text = ""
        self._id_regex: Optional[re.Pattern] = None

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        frame = source_model.data(source_model.index(source_row, 0), Qt.UserRole)
        if self.id_filter and (not self._id_regex or not self._id_regex.match(frame.can_id)):
            return False
        if self.dir_filter and frame.direction != self.dir_filter:
            return False
        if self.search_text:
            data_str = ' '.join(f"{b:02X}" for b in frame.data)
            return self.search_text.lower() in data_str.lower()
        return True

    def set_id_filter(self, text: str) -> None:
        self.id_filter = text.strip().upper()
        try:
            self._id_regex = re.compile(self.id_filter, re.IGNORECASE) if self.id_filter else None
        except re.error:
            self._id_regex = None
        self.invalidateFilter()

    def set_dir_filter(self, direction: Optional[Direction]) -> None:
        self.dir_filter = direction
        self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        self.search_text = text.strip()
        self.invalidateFilter()


# ----------------------------------------------------------------------------------
# 4) Dialog Classes
# ----------------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, can_interface: CANInterface, parent=None):
        super().__init__(parent)
        self.can_interface = can_interface
        self.setWindowTitle("CAN Interface Settings")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QFormLayout()
        self.reconnect_spin = QSpinBox()
        self.reconnect_spin.setRange(1, 20)
        self.reconnect_spin.setValue(self.can_interface._reconnect_attempts)
        self.sim_interval_spin = QDoubleSpinBox()
        self.sim_interval_spin.setRange(0.01, 10.0)
        self.sim_interval_spin.setSingleStep(0.1)
        self.sim_interval_spin.setValue(self.can_interface.sim_interval)
        self.auto_reconnect_check = QCheckBox("Auto-Reconnect on Disconnect")
        self.auto_reconnect_check.setChecked(getattr(self.can_interface, 'auto_reconnect', False))
        layout.addRow("Reconnect Attempts:", self.reconnect_spin)
        layout.addRow("Simulation Interval (s):", self.sim_interval_spin)
        layout.addRow("", self.auto_reconnect_check)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.setLayout(layout)

    def accept(self) -> None:
        self.can_interface.set_reconnect_attempts(self.reconnect_spin.value())
        self.can_interface.sim_interval = self.sim_interval_spin.value()
        self.can_interface.auto_reconnect = self.auto_reconnect_check.isChecked()
        super().accept()

class ExportDialog(QDialog):
    def __init__(self, headers: List[str], parent=None):
        super().__init__(parent)
        self.headers = headers
        self.setWindowTitle("Export Options")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QFormLayout()
        self.delimiter_edit = QLineEdit(",")
        self.delimiter_edit.setToolTip("Delimiter for CSV (e.g., ',', ';', 'tab')")
        self.columns_checkboxes = {h: QCheckBox(h) for h in self.headers}
        for cb in self.columns_checkboxes.values():
            cb.setChecked(True)
        layout.addRow("Delimiter:", self.delimiter_edit)
        for label, cb in self.columns_checkboxes.items():
            layout.addRow(label, cb)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.setLayout(layout)

    def get_options(self) -> Tuple[str, List[str]]:
        delimiter = self.delimiter_edit.text() or ","
        if delimiter.lower() == "tab":
            delimiter = "\t"
        columns = [h for h, cb in self.columns_checkboxes.items() if cb.isChecked()]
        return delimiter, columns

class FrameTemplateDialog(QDialog):
    def __init__(self, templates: Dict[str, CANFrame], parent=None):
        super().__init__(parent)
        self.templates = templates
        self.setWindowTitle("Frame Templates")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        self.template_list = QComboBox()
        self.template_list.addItems(self.templates.keys())
        layout.addWidget(self.template_list)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Template Name")
        layout.addWidget(self.name_edit)
        buttons = QHBoxLayout()
        save_btn = QPushButton("Save Current")
        save_btn.clicked.connect(self.save_template)
        load_btn = QPushButton("Load Selected")
        load_btn.clicked.connect(self.accept)
        buttons.addWidget(save_btn)
        buttons.addWidget(load_btn)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def save_template(self) -> None:
        name = self.name_edit.text().strip()
        if name and hasattr(self.parent(), '_create_frame_from_ui'):
            try:
                frame = self.parent()._create_frame_from_ui()
                self.templates[name] = frame
                self.template_list.addItem(name)
                self.name_edit.clear()
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))

    def get_selected_frame(self) -> Optional[CANFrame]:
        return self.templates.get(self.template_list.currentText())


# ----------------------------------------------------------------------------------
# 5) CANMonitorTab Class
# ----------------------------------------------------------------------------------
class CANMonitorTab(QWidget):
    """Main CAN monitoring interface with connection controls and real-time display."""
    frame_received = pyqtSignal(CANFrame)
    connection_lost = pyqtSignal()
    connection_status = pyqtSignal(str)
    connection_error = pyqtSignal(str)
    connection_success = pyqtSignal(str)
    connection_reconnect = pyqtSignal(str)
    connection_disconnected = pyqtSignal(str)
    connection_connected = pyqtSignal(str)
    connection_failed = pyqtSignal(str)
    connection_reconnect_failed = pyqtSignal(str)
    connection_reconnect_success = pyqtSignal(str)
    status_updated = pyqtSignal(str, str)
    log_message_received = pyqtSignal(str)

    NOISY_THRESHOLD = 10
    COLORS = [QColor("#FFDDDD"), QColor("#DDFFDD"), QColor("#DDDDFF"), QColor("#FFDDBB")]

    def __init__(self):
        super().__init__()
        # Create interface but DON'T start simulation automatically
        self.can_interface = CANInterface(simulate=True, reconnect_attempts=3, sim_interval=2.0)
        self.can_interface.auto_reconnect = False
        self.paused = True  # Start paused
        self.frame_buffer: List[Tuple[CANFrame, float, QColor]] = []
        self.frame_times: List[float] = []
        self.id_timestamps: Dict[str, List[float]] = defaultdict(list)
        self.id_colors: Dict[str, QColor] = {}
        self.unique_ids: Set[str] = set()
        self.rx_count = 0
        self.tx_count = 0
        self.data_length_counts: Dict[int, int] = defaultdict(int)
        self.templates: Dict[str, CANFrame] = {}
        self.dark_mode = False
        self.log_viewer: QTextEdit = None
        self.table_model: CANTableModel = None
        self.proxy_model: CANFilterProxyModel = None
        self.table_view: QTableView = None
        self.port_select: QComboBox = None
        self.connect_btn: QPushButton = None
        self.status_indicator: QLabel = None
        self.frame_count_label: QLabel = None

        # Slower update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._flush_frame_buffer)
        self.update_timer.start(500)

        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start(1000)

        self._init_ui()
        self._connect_signals()
        
        # Call refresh_ports AFTER UI is created
        self.refresh_ports()

        # DON'T auto-start - user clicks Connect or use simulation button
        # self.can_interface.start()
        logger.info("CANMonitorTab initialized - simulation paused")

    def _init_ui(self):
        """Set up all UI components."""
        self.layout = QVBoxLayout()
        self._init_serial_ui()
        self._init_filter_ui()
        self._init_main_ui()
        self._init_transmit_ui()
        self._init_controls()
        self._init_stats_ui()
        self._init_status_bar()
        self.setLayout(self.layout)
        QShortcut(QKeySequence("Ctrl+P"), self, self.toggle_pause)
        QShortcut(QKeySequence("Ctrl+S"), self, self.export_table_to_csv)
        
        # Apply CyberNinja dark theme
        self._apply_dark_theme()
    
    def _apply_dark_theme(self):
        """Apply CyberNinja dark theme to match other tabs."""
        self.setStyleSheet("""
            QWidget {
                background-color: #0a0a0f;
                color: #e0e0e0;
                font-family: Consolas, monospace;
            }
            QGroupBox {
                border: 1px solid #00f0ff40;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                color: #00f0ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
            QPushButton {
                background-color: #12121a;
                border: 1px solid #00f0ff60;
                border-radius: 5px;
                padding: 8px 15px;
                color: #00f0ff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00f0ff;
                color: #0a0a0f;
            }
            QLineEdit, QComboBox {
                background-color: #08080c;
                border: 1px solid #00f0ff40;
                border-radius: 4px;
                padding: 6px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #00f0ff;
            }
            QTableView {
                background-color: #08080c;
                gridline-color: #00f0ff30;
                border: 1px solid #00f0ff40;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QTableView::item {
                padding: 5px;
            }
            QTableView::item:selected {
                background-color: #00f0ff40;
            }
            QHeaderView::section {
                background-color: #12121a;
                color: #00f0ff;
                border: none;
                padding: 8px;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #08080c;
                border: 1px solid #00f0ff40;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QStatusBar {
                background-color: #12121a;
                color: #00f0ff;
            }
        """)

    def _init_serial_ui(self):
        group = QGroupBox("Interface Connection")
        layout = QHBoxLayout()
        
        # Interface type selector
        layout.addWidget(QLabel("Type:"))
        self.interface_type_combo = QComboBox()
        self.interface_type_combo.addItems([
            "Simulation",
            "SLCAN (SavvyCAN/CANtact)",
            "MCP2515 (Arduino)",
            "LIN Bus"
        ])
        self.interface_type_combo.setToolTip("Select interface type")
        self.interface_type_combo.currentTextChanged.connect(self._on_interface_type_changed)
        layout.addWidget(self.interface_type_combo)
        
        # Port selector
        layout.addWidget(QLabel("Port:"))
        self.port_select = QComboBox()
        self.port_select.setToolTip("Select serial port")
        self.port_select.setMinimumWidth(100)
        layout.addWidget(self.port_select)
        
        refresh_btn = QPushButton("[Refresh]")
        refresh_btn.clicked.connect(self.refresh_ports)
        refresh_btn.setToolTip("Refresh available serial ports")
        layout.addWidget(refresh_btn)
        
        # CAN Bitrate selector
        layout.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems([
            "500 kbps (OBD-II)",
            "250 kbps (J1939)",
            "125 kbps (Trucks)",
            "1 Mbps (CAN-FD)",
            "33.3 kbps (GM SW-CAN)",
        ])
        self.bitrate_combo.setToolTip("CAN bus bitrate")
        layout.addWidget(self.bitrate_combo)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setToolTip("Connect/disconnect")
        self.connect_btn.setMinimumWidth(100)
        layout.addWidget(self.connect_btn)
        
        # Status indicator
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(20, 20)
        self.status_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        self.status_indicator.setToolTip("Connection status")
        layout.addWidget(self.status_indicator)
        
        group.setLayout(layout)
        self.layout.addWidget(group)
        
        # Initial port refresh
        self.refresh_ports()
    
    def _on_interface_type_changed(self, interface_type: str):
        """Handle interface type change."""
        is_simulation = "Simulation" in interface_type
        self.port_select.setEnabled(not is_simulation)
        self.bitrate_combo.setEnabled(not is_simulation and "LIN" not in interface_type)
        
        # Update bitrate options for LIN
        if "LIN" in interface_type:
            self.bitrate_combo.clear()
            self.bitrate_combo.addItems(["19200 baud", "9600 baud"])
        elif "SLCAN" in interface_type or "MCP2515" in interface_type:
            self.bitrate_combo.clear()
            self.bitrate_combo.addItems([
                "500 kbps (OBD-II)",
                "250 kbps (J1939)", 
                "125 kbps (Trucks)",
                "1 Mbps (CAN-FD)",
                "33.3 kbps (GM SW-CAN)",
            ])

    def _init_filter_ui(self):
        group = QGroupBox("Filters")
        layout = QFormLayout()
        self.filter_id = QLineEdit()
        self.filter_id.setPlaceholderText("CAN ID regex (e.g., ^1A[0-2]$)")
        self.filter_dir = QComboBox()
        self.filter_dir.addItem("All", None)
        for d in Direction:
            self.filter_dir.addItem(d.value, d)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search hex bytes (e.g., DE AD)")
        layout.addRow("CAN ID:", self.filter_id)
        layout.addRow("Direction:", self.filter_dir)
        layout.addRow("Search:", self.search_box)
        reset_btn = QPushButton("Reset Filters")
        reset_btn.clicked.connect(self.reset_filters)
        reset_btn.setToolTip("Clear all filters")
        layout.addRow(reset_btn)
        group.setLayout(layout)
        self.layout.addWidget(group)

    def _init_main_ui(self):
        splitter = QSplitter(Qt.Vertical)
        self.table_model = CANTableModel()
        self.proxy_model = CANFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setItemDelegateForColumn(2, HexDelegate())
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSortingEnabled(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.resizeColumnsToContents()
        splitter.addWidget(self.table_view)
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMinimumHeight(100)
        splitter.addWidget(self.log_viewer)
        splitter.setSizes([400, 100])
        self.layout.addWidget(splitter)

    def _init_transmit_ui(self):
        group = QGroupBox("Transmit CAN Frame")
        layout = QFormLayout()
        self.input_id = QLineEdit()
        self.input_id.setValidator(HexValidator(self))
        self.input_id.setPlaceholderText("HEX ID (e.g., 1A2)")
        self.input_data = QLineEdit()
        self.input_data.setValidator(HexBytesValidator(self))
        self.input_data.setPlaceholderText("HEX bytes (e.g., DE AD BE EF)")
        self.input_dir = QComboBox()
        self.input_dir.addItems([d.value for d in Direction])
        self.send_btn = QPushButton("Send Frame")
        self.template_btn = QPushButton("[List] Templates")
        layout.addRow("CAN ID:", self.input_id)
        layout.addRow("Data Bytes:", self.input_data)
        layout.addRow("Direction:", self.input_dir)
        layout.addRow(self.send_btn)
        layout.addRow(self.template_btn)
        group.setLayout(layout)
        self.layout.addWidget(group)

    def _init_controls(self):
        layout = QHBoxLayout()
        self.pause_btn = QPushButton("|| Pause")
        self.settings_btn = QPushButton("[Settings]")
        self.load_did_btn = QPushButton("[Load DID Config]")
        buttons = [
            (self.pause_btn, self.toggle_pause, "Pause/resume frame updates (Ctrl+P)"),
            (self.settings_btn, self._open_settings_dialog, "Configure CAN interface"),
            (self.load_did_btn, self._load_did_config, "Load DID configuration file"),
            ("[Clear]", self.clear_table, "Clear all frames"),
            ("🔁 Replay", self.replay_frame, "Replay selected frame"),
            ("[Export]", self.export_table_to_csv, "Export table to CSV (Ctrl+S)"),
        ]
        for btn, handler, tooltip in buttons:
            if isinstance(btn, str):
                btn = QPushButton(btn)
            btn.clicked.connect(handler)
            btn.setToolTip(tooltip)
            layout.addWidget(btn)
        self.layout.addLayout(layout)

    def _init_stats_ui(self):
        group = QGroupBox("CAN Statistics")
        layout = QFormLayout()
        self.unique_ids_label = QLabel("0")
        self.rx_tx_label = QLabel("RX: 0, TX: 0")
        self.data_length_label = QLabel("")
        layout.addRow("Unique IDs:", self.unique_ids_label)
        layout.addRow("RX/TX:", self.rx_tx_label)
        layout.addRow("Data Lengths:", self.data_length_label)
        self.plot_btn = QPushButton("[Plot Histogram]")
        self.plot_btn.clicked.connect(self.plot_histogram)
        layout.addRow(self.plot_btn)
        group.setLayout(layout)
        self.layout.addWidget(group)

    def _init_status_bar(self):
        self.status_bar = QStatusBar()
        self.frame_count_label = QLabel("Frames: 0 | FPS: 0.0")
        self.status_bar.addPermanentWidget(self.frame_count_label)
        self.layout.addWidget(self.status_bar)

    def _connect_signals(self):
        self.can_interface.frame_received.connect(self.handle_frame)
        self.can_interface.connection_lost.connect(self.handle_connection_lost)
        self.can_interface.connection_changed.connect(self._handle_connection_changed)
        self.filter_id.textChanged.connect(self.proxy_model.set_id_filter)
        self.filter_dir.currentIndexChanged.connect(
            lambda: self.proxy_model.set_dir_filter(self.filter_dir.currentData()))
        self.search_box.textChanged.connect(self.proxy_model.set_search_text)
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.send_btn.clicked.connect(self.send_frame)
        self.template_btn.clicked.connect(self._open_template_dialog)
        self.status_updated.connect(self._handle_status_update)

    def handle_frame(self, frame: CANFrame) -> None:
        if not self.paused:
            # Strict buffer limit to prevent UI freeze
            if len(self.frame_buffer) > 20:
                return  # Skip frames if buffer is getting full
            
            current_time = time.time()
            self.id_timestamps[frame.can_id].append(current_time)
            self.id_timestamps[frame.can_id] = [t for t in self.id_timestamps[frame.can_id] if current_time - t < 1.0]
            frequency = len(self.id_timestamps[frame.can_id])
            if frame.can_id not in self.id_colors:
                self.id_colors[frame.can_id] = self.COLORS[len(self.id_colors) % len(self.COLORS)]
            color = self.id_colors[frame.can_id]
            self.frame_buffer.append((frame, frequency, color))
            self.unique_ids.add(frame.can_id)
            if frame.direction == Direction.RX:
                self.rx_count += 1
            else:
                self.tx_count += 1
            self.data_length_counts[len(frame.data)] += 1

    def _flush_frame_buffer(self) -> None:
        if self.frame_buffer:
            # Only add up to 10 frames at a time to keep UI responsive
            frames_to_add = self.frame_buffer[:10]
            self.table_model.add_frames(frames_to_add)
            self.frame_buffer = self.frame_buffer[10:]

    def handle_connection_lost(self, message: str) -> None:
        self.status_updated.emit(f"[!] {message}", "error")
        self.connect_btn.setText("🔌 Connect")
        self.status_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
        if self.can_interface.auto_reconnect:
            self.connect_serial()
        else:
            self.can_interface = CANInterface(simulate=True)
            self._connect_signals()
            self.can_interface.start()

    def _handle_connection_changed(self, connected: bool) -> None:
        if connected:
            self.status_updated.emit("🔌 Connected", "success")
            self.connect_btn.setText("[Disconnect]")
            self.status_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
        else:
            self.status_updated.emit("🔌 Disconnected", "info")
            self.connect_btn.setText("🔌 Connect")
            self.status_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")

    def send_frame(self) -> None:
        try:
            frame = self._create_frame_from_ui()
            if self.can_interface.send_frame(frame):
                self.status_updated.emit("[OK] Frame sent", "success")
            else:
                self.status_updated.emit("[X] Send failed", "error")
        except ValueError as e:
            self.status_updated.emit(f"[!] {str(e)}", "warning")
        except Exception as e:
            logger.error(f"Send error: {e}")
            self.status_updated.emit("[X] Send failed", "error")

    def _create_frame_from_ui(self) -> CANFrame:
        can_id = self.input_id.text().strip().upper()
        data_str = self.input_data.text().strip().upper()
        direction = Direction(self.input_dir.currentText())
        if not can_id:
            raise ValueError("CAN ID is required")
        if not data_str:
            raise ValueError("Data bytes are required")
        try:
            data = [int(b, 16) for b in data_str.split()]
            if not (1 <= len(data) <= 8):
                raise ValueError("Data must be 1-8 bytes")
        except ValueError as e:
            raise ValueError(f"Invalid hex data: {str(e)}")
        return CANFrame(
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            can_id=can_id,
            data=data,
            direction=direction
        )

    def toggle_connection(self) -> None:
        """Toggle connection based on current state."""
        if self.can_interface.is_running():
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self) -> None:
        """Connect to selected interface."""
        interface_type = self.interface_type_combo.currentText()
        port = self.port_select.currentText()
        bitrate_text = self.bitrate_combo.currentText()
        
        # Parse bitrate
        bitrate = 500000  # default
        if "500" in bitrate_text:
            bitrate = 500000
        elif "250" in bitrate_text:
            bitrate = 250000
        elif "125" in bitrate_text:
            bitrate = 125000
        elif "1 M" in bitrate_text:
            bitrate = 1000000
        elif "33" in bitrate_text:
            bitrate = 33333
        elif "19200" in bitrate_text:
            bitrate = 19200
        elif "9600" in bitrate_text:
            bitrate = 9600
        
        # Handle simulation mode
        if "Simulation" in interface_type:
            self.can_interface.stop()
            self.can_interface = CANInterface(simulate=True, sim_interval=2.0)
            self._connect_signals()
            self.can_interface.start()
            self.connect_btn.setText("Disconnect")
            self.status_indicator.setStyleSheet("background-color: #00ff66; border-radius: 10px;")
            self.status_updated.emit("Simulation mode started", "success")
            return
        
        # Validate port selection
        if not port:
            self.status_updated.emit("[!] No port selected", "warning")
            return
        
        # Stop existing connection
        self.can_interface.stop()
        
        # Create new interface with selected settings
        self.can_interface = CANInterface(
            simulate=False, 
            serial_port=port,
            baudrate=115200  # Serial baud rate
        )
        self.can_interface.auto_reconnect = False
        
        # Store interface type for protocol handling
        self._current_interface_type = interface_type
        self._current_can_bitrate = bitrate
        
        self._connect_signals()
        
        if self.can_interface.start():
            self.connect_btn.setText("Disconnect")
            self.status_indicator.setStyleSheet("background-color: #00ff66; border-radius: 10px;")
            self.status_updated.emit(f"Connected to {port} ({interface_type}) @ {bitrate_text}", "success")
            
            # Send SLCAN init commands if applicable
            if "SLCAN" in interface_type:
                self._init_slcan(bitrate)
        else:
            self.status_indicator.setStyleSheet("background-color: #ff3366; border-radius: 10px;")
            self.status_updated.emit("[X] Connection failed", "error")
    
    def _init_slcan(self, bitrate: int):
        """Initialize SLCAN adapter with proper commands."""
        try:
            # Map bitrate to SLCAN command
            slcan_cmds = {
                10000: 'S0', 20000: 'S1', 50000: 'S2', 100000: 'S3',
                125000: 'S4', 250000: 'S5', 500000: 'S6', 800000: 'S7', 1000000: 'S8'
            }
            cmd = slcan_cmds.get(bitrate, 'S6')
            
            if hasattr(self.can_interface, '_serial') and self.can_interface._serial:
                import time
                self.can_interface._serial.write(b'C\r')  # Close first
                time.sleep(0.1)
                self.can_interface._serial.write(f'{cmd}\r'.encode())  # Set bitrate
                time.sleep(0.1)
                self.can_interface._serial.write(b'O\r')  # Open channel
                time.sleep(0.1)
                logger.info(f"SLCAN initialized with {cmd}")
        except Exception as e:
            logger.error(f"SLCAN init error: {e}")

    def disconnect_serial(self) -> None:
        """Disconnect from current interface."""
        # Send SLCAN close if applicable
        if hasattr(self, '_current_interface_type') and "SLCAN" in self._current_interface_type:
            try:
                if hasattr(self.can_interface, '_serial') and self.can_interface._serial:
                    self.can_interface._serial.write(b'C\r')
            except:
                pass
        
        self.can_interface.stop()
        self.connect_btn.setText("Connect")
        self.status_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        self.status_updated.emit("Disconnected", "info")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_btn.setText("> Resume" if self.paused else "|| Pause")
        self.status_updated.emit(f"{'Paused' if self.paused else 'Resumed'}", "info")

    def clear_table(self) -> None:
        self.table_model.clear()
        self.unique_ids.clear()
        self.rx_count = 0
        self.tx_count = 0
        self.data_length_counts.clear()
        self.status_updated.emit("Table cleared", "info")

    def replay_frame(self) -> None:
        selected = self.table_view.selectionModel().selectedRows()
        if not selected:
            self.status_updated.emit("[!] No frame selected", "warning")
            return
        index = self.proxy_model.mapToSource(selected[0])
        frame, _, _ = self.table_model.frames[index.row()]
        if self.can_interface.send_frame(frame):
            self.status_updated.emit("🔁 Frame replayed", "success")
        else:
            self.status_updated.emit("[X] Replay failed", "error")

    def export_table_to_csv(self) -> None:
        dialog = ExportDialog(self.table_model._headers, self)
        if not dialog.exec_():
            return
        delimiter, columns = dialog.get_options()
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f, delimiter=delimiter)
                writer.writerow(columns)
                for frame, _, _ in self.table_model.frames:
                    row = []
                    if "Timestamp" in columns:
                        row.append(frame.timestamp)
                    if "CAN ID" in columns:
                        row.append(frame.can_id)
                    if "Data Bytes" in columns:
                        row.append(' '.join(f"{b:02X}" for b in frame.data))
                    if "Direction" in columns:
                        row.append(frame.direction.value)
                    if "UDS Decode" in columns:
                        row.append(decode_uds(frame) or "")
                    writer.writerow(row)
            self.status_updated.emit(f"[OK] Exported {len(self.table_model.frames)} frames", "success")
        except Exception as e:
            logger.error(f"Export error: {e}")
            self.status_updated.emit("[X] Export failed", "error")

    def reset_filters(self) -> None:
        self.filter_id.clear()
        self.filter_dir.setCurrentIndex(0)
        self.search_box.clear()
        self.status_updated.emit("[Refresh] Filters reset", "info")

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self.can_interface, self)
        if dialog.exec_():
            self.status_updated.emit("[OK] Settings updated", "success")

    def _open_template_dialog(self) -> None:
        dialog = FrameTemplateDialog(self.templates, self)
        if dialog.exec_():
            frame = dialog.get_selected_frame()
            if frame:
                self.input_id.setText(frame.can_id)
                self.input_data.setText(' '.join(f"{b:02X}" for b in frame.data))
                self.input_dir.setCurrentText(frame.direction.value)
                self.status_updated.emit("[List] Template loaded", "info")

    def _load_did_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load DID Config", "", "JSON Files (*.json)")
        if path:
            global DID_LOOKUP
            DID_LOOKUP = load_did_config(path)
            self.table_model.dataChanged.emit(QModelIndex(), QModelIndex())  # Refresh table
            self.status_updated.emit(f"[Loaded] DID config from {path}", "success")

    def toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.setStyleSheet("""
                QWidget { background-color: #2D2D2D; color: #DCDCDC; }
                QTableView { background-color: #1E1E1E; alternate-background-color: #252526; }
                QHeaderView::section { background-color: #3C3C3C; color: #FFFFFF; }
                QLineEdit, QComboBox, QPushButton { background-color: #333333; border: 1px solid #454545; padding: 3px; }
                QPushButton:hover { background-color: #404040; }
                QGroupBox { border: 1px solid #454545; }
                QStatusBar { background-color: #2D2D2D; }
                QTextEdit { background-color: #1E1E1E; color: #DCDCDC; }
            """)
        else:
            self.setStyleSheet("")
        self.status_updated.emit(f"{'Dark' if self.dark_mode else 'Light'} theme applied", "info")

    def refresh_ports(self) -> None:
        if self.port_select is None:
            return
        self.port_select.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_select.addItems(ports)
        self.status_updated.emit(f"Found {len(ports)} ports", "info")

    def _update_stats(self) -> None:
        self.unique_ids_label.setText(str(len(self.unique_ids)))
        total = self.rx_count + self.tx_count
        if total > 0:
            rx_percent = self.rx_count / total * 100
            tx_percent = self.tx_count / total * 100
            self.rx_tx_label.setText(f"RX: {self.rx_count} ({rx_percent:.1f}%), TX: {self.tx_count} ({tx_percent:.1f}%)")
        else:
            self.rx_tx_label.setText("RX: 0, TX: 0")
        data_lengths = ', '.join(f"{k}: {v}" for k, v in sorted(self.data_length_counts.items()))
        self.data_length_label.setText(data_lengths)

    def plot_histogram(self) -> None:
        try:
            import matplotlib.pyplot as plt
            lengths = [len(frame.data) for frame, _, _ in self.table_model.frames]
            plt.hist(lengths, bins=range(9), align='left', rwidth=0.8)
            plt.xlabel("Data Length (bytes)")
            plt.ylabel("Frequency")
            plt.title("CAN Frame Data Length Distribution")
            plt.show()
        except ImportError:
            self.status_updated.emit("[!] Matplotlib not installed", "warning")

    def _handle_status_update(self, message: str, style_class: str) -> None:
        styles = {
            "success": "color: #00C853;",
            "warning": "color: #FFD600;",
            "error": "color: #D50000;",
            "info": "color: #FFFFFF;"
        }
        self.status_bar.setStyleSheet(styles.get(style_class, ""))
        self.status_bar.showMessage(message, 3000)

    def closeEvent(self, event) -> None:
        self.can_interface.stop()
        super().closeEvent(event)


# ----------------------------------------------------------------------------------
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    tab = CANMonitorTab()
    tab.show()
    sys.exit(app.exec_())