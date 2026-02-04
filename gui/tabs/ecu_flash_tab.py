# gui/tabs/ecu_flash_tab.py

"""

                     CYBERNINJA ECU FLASH MODULE                               
                   EEPROM Read/Write • Bench Operations                        


Description:
ECU Flash/Read tab - EEPROM operations, dump reading, backup/restore functionality.
For bench work and advanced locksmith operations.
"""

# ----------------------------------------------------------------------------------
# 1) Imports
# ----------------------------------------------------------------------------------
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QMessageBox, QTabWidget, QGridLayout, QFileDialog,
    QSpinBox, QCheckBox, QFrame, QSplitter, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.QtGui import QFont, QColor

from backend.can_interface import CANInterface, CANFrame, Direction

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# 2) ECU Chip Definitions
# ----------------------------------------------------------------------------------
@dataclass
class ChipProfile:
    name: str
    manufacturer: str
    flash_size: int
    eeprom_size: int
    page_size: int
    read_cmd: List[int]
    write_cmd: List[int]
    notes: str = ""

CHIP_PROFILES = {
    "MPC5606B (FCA 2011-2018)": ChipProfile(
        name="MPC5606B",
        manufacturer="Freescale",
        flash_size=1024 * 1024,
        eeprom_size=64 * 1024,
        page_size=256,
        read_cmd=[0x23],
        write_cmd=[0x3D],
        notes="Common in Dodge/Jeep/Chrysler BCM. DFLASH contains VIN, keys, PIN."
    ),
    "MPC5646C (FCA 2018+)": ChipProfile(
        name="MPC5646C",
        manufacturer="Freescale",
        flash_size=2 * 1024 * 1024,
        eeprom_size=128 * 1024,
        page_size=256,
        read_cmd=[0x23],
        write_cmd=[0x3D],
        notes="Newer FCA vehicles. Enhanced security. Requires proper seed/key."
    ),
    "RH850 (FCA 2019+ RF Hub)": ChipProfile(
        name="RH850",
        manufacturer="Renesas",
        flash_size=512 * 1024,
        eeprom_size=32 * 1024,
        page_size=128,
        read_cmd=[0x23],
        write_cmd=[0x3D],
        notes="RF Hub module. Contains fob pairing data and rolling codes."
    ),
    "S12XE (GM BCM)": ChipProfile(
        name="S12XE",
        manufacturer="Freescale",
        flash_size=512 * 1024,
        eeprom_size=4 * 1024,
        page_size=128,
        read_cmd=[0x23],
        write_cmd=[0x3D],
        notes="GM Body Control Module. Smaller EEPROM."
    ),
    "TC1797 (VW/Audi)": ChipProfile(
        name="TC1797",
        manufacturer="Infineon",
        flash_size=4 * 1024 * 1024,
        eeprom_size=256 * 1024,
        page_size=256,
        read_cmd=[0x23],
        write_cmd=[0x3D],
        notes="VAG group modules. TriCore architecture."
    ),
    "Custom": ChipProfile(
        name="Custom",
        manufacturer="Custom",
        flash_size=256 * 1024,
        eeprom_size=8 * 1024,
        page_size=256,
        read_cmd=[0x23],
        write_cmd=[0x3D],
        notes="User-defined chip parameters."
    ),
}

# ----------------------------------------------------------------------------------
# 3) ECUFlashTab Class
# ----------------------------------------------------------------------------------
class ECUFlashTab(QWidget):
    """
    
      ECU Flash Interface - CyberNinja Style                                   
    
    """
    
    status_updated = pyqtSignal(str, str)
    progress_updated = pyqtSignal(int)
    
    # CyberNinja Color Palette
    COLORS = {
        "bg_dark": "#0a0a0f",
        "bg_panel": "#12121a",
        "bg_input": "#08080c",
        "cyan": "#00f0ff",
        "magenta": "#ff00aa",
        "green": "#00ff66",
        "yellow": "#f0ff00",
        "orange": "#ff6600",
        "red": "#ff3366",
        "text": "#e0e0e0",
        "text_dim": "#666666",
        "border": "#00f0ff33",
    }
    
    def __init__(self, can_interface: Optional[CANInterface] = None):
        super().__init__()
        self.can_interface = can_interface or CANInterface(simulate=True)
        self.current_chip: Optional[ChipProfile] = None
        self.read_buffer: bytearray = bytearray()
        self.write_buffer: bytearray = bytearray()
        self.operation_in_progress = False
        self.current_address = 0
        self.end_address = 0
        
        self._init_ui()
        self._connect_signals()
        self._apply_cyberninja_theme()
        self._on_chip_changed(self.chip_combo.currentText())
        
        logger.info("[ECUFlashTab] Initialized - CyberNinja Mode Active")
    
    def _init_ui(self):
        """Initialize the CyberNinja UI."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 
        # Header with Warning
        # 
        header = self._create_header()
        main_layout.addWidget(header)
        
        # 
        # Chip Configuration Panel
        # 
        chip_panel = self._create_chip_panel()
        main_layout.addWidget(chip_panel)
        
        # 
        # Main Tabs
        # 
        tabs = QTabWidget()
        tabs.addTab(self._create_read_tab(), "[Read] READ EEPROM")
        tabs.addTab(self._create_write_tab(), "[Edit] WRITE EEPROM")
        tabs.addTab(self._create_compare_tab(), "[Search] COMPARE")
        tabs.addTab(self._create_checksum_tab(), "🧮 CHECKSUM")
        tabs.addTab(self._create_log_tab(), "[List] LOG")
        main_layout.addWidget(tabs)
        
        # 
        # Progress Bar
        # 
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v / %m bytes")
        main_layout.addWidget(self.progress_bar)
        
        # 
        # Status Bar
        # 
        self.status_bar = QLabel(" READY  Select chip profile and operation")
        main_layout.addWidget(self.status_bar)
        
        self.setLayout(main_layout)
    
    def _create_header(self) -> QWidget:
        """Create CyberNinja header with warning."""
        frame = QFrame()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QLabel(" CYBERNINJA ECU FLASH ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {self.COLORS['cyan']};
            padding: 10px;
            letter-spacing: 3px;
        """)
        layout.addWidget(title)
        
        # Warning Banner
        warning = QLabel("[!] CAUTION: Flash operations can permanently damage ECU. ALWAYS backup first!")
        warning.setAlignment(Qt.AlignCenter)
        warning.setStyleSheet(f"""
            background-color: {self.COLORS['red']}20;
            color: {self.COLORS['red']};
            padding: 10px;
            border: 1px solid {self.COLORS['red']}80;
            border-radius: 5px;
            font-weight: bold;
        """)
        layout.addWidget(warning)
        
        frame.setLayout(layout)
        return frame
    
    def _create_chip_panel(self) -> QGroupBox:
        """Create chip configuration panel."""
        group = QGroupBox("> CHIP CONFIGURATION")
        layout = QGridLayout()
        
        # Row 0: Chip selection
        layout.addWidget(QLabel("Chip Profile:"), 0, 0)
        self.chip_combo = QComboBox()
        self.chip_combo.addItems(CHIP_PROFILES.keys())
        self.chip_combo.currentTextChanged.connect(self._on_chip_changed)
        layout.addWidget(self.chip_combo, 0, 1)
        
        layout.addWidget(QLabel("Manufacturer:"), 0, 2)
        self.manufacturer_label = QLabel("--")
        self.manufacturer_label.setStyleSheet(f"color: {self.COLORS['cyan']};")
        layout.addWidget(self.manufacturer_label, 0, 3)
        
        # Row 1: Sizes
        layout.addWidget(QLabel("Flash Size:"), 1, 0)
        self.flash_size_label = QLabel("--")
        self.flash_size_label.setStyleSheet(f"color: {self.COLORS['green']};")
        layout.addWidget(self.flash_size_label, 1, 1)
        
        layout.addWidget(QLabel("EEPROM Size:"), 1, 2)
        self.eeprom_size_label = QLabel("--")
        self.eeprom_size_label.setStyleSheet(f"color: {self.COLORS['magenta']};")
        layout.addWidget(self.eeprom_size_label, 1, 3)
        
        layout.addWidget(QLabel("Page Size:"), 1, 4)
        self.page_size_label = QLabel("--")
        self.page_size_label.setStyleSheet(f"color: {self.COLORS['yellow']};")
        layout.addWidget(self.page_size_label, 1, 5)
        
        # Row 2: Notes
        layout.addWidget(QLabel("Notes:"), 2, 0)
        self.chip_notes = QLabel("--")
        self.chip_notes.setWordWrap(True)
        self.chip_notes.setStyleSheet(f"color: {self.COLORS['text_dim']}; font-style: italic;")
        layout.addWidget(self.chip_notes, 2, 1, 1, 5)
        
        group.setLayout(layout)
        return group
    
    def _create_read_tab(self) -> QWidget:
        """Create EEPROM read interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Address Range
        addr_group = QGroupBox("> ADDRESS RANGE")
        addr_layout = QHBoxLayout()
        
        addr_layout.addWidget(QLabel("Start Address:"))
        self.read_start = QLineEdit("0x0000")
        self.read_start.setMaximumWidth(120)
        addr_layout.addWidget(self.read_start)
        
        addr_layout.addWidget(QLabel("End Address:"))
        self.read_end = QLineEdit("0xFFFF")
        self.read_end.setMaximumWidth(120)
        addr_layout.addWidget(self.read_end)
        
        addr_layout.addWidget(QLabel("Length:"))
        self.read_length = QLabel("65536 bytes")
        self.read_length.setStyleSheet(f"color: {self.COLORS['cyan']}; font-weight: bold;")
        addr_layout.addWidget(self.read_length)
        
        self.read_full_btn = QPushButton("[List] Full EEPROM")
        self.read_full_btn.clicked.connect(self._set_full_eeprom_range)
        addr_layout.addWidget(self.read_full_btn)
        
        addr_layout.addStretch()
        addr_group.setLayout(addr_layout)
        layout.addWidget(addr_group)
        
        # Read Controls
        control_group = QGroupBox("> READ CONTROLS")
        control_layout = QHBoxLayout()
        
        self.read_btn = QPushButton("> START READ")
        self.read_btn.setMinimumHeight(50)
        self.read_btn.clicked.connect(self._start_read)
        control_layout.addWidget(self.read_btn)
        
        self.stop_btn = QPushButton("[Stop] STOP")
        self.stop_btn.setMinimumHeight(50)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_operation)
        control_layout.addWidget(self.stop_btn)
        
        self.save_btn = QPushButton("[Save] SAVE DUMP")
        self.save_btn.setMinimumHeight(50)
        self.save_btn.clicked.connect(self._save_dump)
        control_layout.addWidget(self.save_btn)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Preview
        preview_group = QGroupBox("> DATA PREVIEW")
        preview_layout = QVBoxLayout()
        
        self.read_preview = QTextEdit()
        self.read_preview.setReadOnly(True)
        self.read_preview.setFont(QFont("Consolas", 10))
        self.read_preview.setPlaceholderText("Read data will appear here...")
        preview_layout.addWidget(self.read_preview)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        widget.setLayout(layout)
        return widget
    
    def _create_write_tab(self) -> QWidget:
        """Create EEPROM write interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # File Selection
        file_group = QGroupBox("> FILE SELECTION")
        file_layout = QHBoxLayout()
        
        self.write_file_path = QLineEdit()
        self.write_file_path.setPlaceholderText("Select .bin file to write...")
        self.write_file_path.setReadOnly(True)
        file_layout.addWidget(self.write_file_path)
        
        self.browse_btn = QPushButton("[Folder] Browse")
        self.browse_btn.clicked.connect(self._browse_write_file)
        file_layout.addWidget(self.browse_btn)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # File Info
        info_group = QGroupBox("> FILE INFO")
        info_layout = QGridLayout()
        
        info_layout.addWidget(QLabel("File Size:"), 0, 0)
        self.write_file_size = QLabel("--")
        self.write_file_size.setStyleSheet(f"color: {self.COLORS['cyan']};")
        info_layout.addWidget(self.write_file_size, 0, 1)
        
        info_layout.addWidget(QLabel("Checksum:"), 0, 2)
        self.write_file_checksum = QLabel("--")
        self.write_file_checksum.setStyleSheet(f"color: {self.COLORS['magenta']};")
        info_layout.addWidget(self.write_file_checksum, 0, 3)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Write Options
        options_group = QGroupBox("> WRITE OPTIONS")
        options_layout = QVBoxLayout()
        
        self.verify_check = QCheckBox("Verify after write")
        self.verify_check.setChecked(True)
        options_layout.addWidget(self.verify_check)
        
        self.backup_check = QCheckBox("Create backup before write")
        self.backup_check.setChecked(True)
        options_layout.addWidget(self.backup_check)
        
        self.erase_check = QCheckBox("Erase before write")
        self.erase_check.setChecked(False)
        options_layout.addWidget(self.erase_check)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Write Controls
        control_group = QGroupBox("> WRITE CONTROLS")
        control_layout = QHBoxLayout()
        
        self.write_btn = QPushButton("[Edit] START WRITE")
        self.write_btn.setMinimumHeight(50)
        self.write_btn.setStyleSheet(f"background-color: {self.COLORS['orange']}40;")
        self.write_btn.clicked.connect(self._start_write)
        control_layout.addWidget(self.write_btn)
        
        self.write_stop_btn = QPushButton("[Stop] STOP")
        self.write_stop_btn.setMinimumHeight(50)
        self.write_stop_btn.setEnabled(False)
        self.write_stop_btn.clicked.connect(self._stop_operation)
        control_layout.addWidget(self.write_stop_btn)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_compare_tab(self) -> QWidget:
        """Create dump comparison interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # File Selection
        files_group = QGroupBox("> SELECT FILES TO COMPARE")
        files_layout = QGridLayout()
        
        files_layout.addWidget(QLabel("File A (Original):"), 0, 0)
        self.compare_file_a = QLineEdit()
        self.compare_file_a.setReadOnly(True)
        files_layout.addWidget(self.compare_file_a, 0, 1)
        self.browse_a_btn = QPushButton("[Folder]")
        self.browse_a_btn.clicked.connect(lambda: self._browse_compare_file('a'))
        files_layout.addWidget(self.browse_a_btn, 0, 2)
        
        files_layout.addWidget(QLabel("File B (Modified):"), 1, 0)
        self.compare_file_b = QLineEdit()
        self.compare_file_b.setReadOnly(True)
        files_layout.addWidget(self.compare_file_b, 1, 1)
        self.browse_b_btn = QPushButton("[Folder]")
        self.browse_b_btn.clicked.connect(lambda: self._browse_compare_file('b'))
        files_layout.addWidget(self.browse_b_btn, 1, 2)
        
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)
        
        # Compare button
        self.compare_btn = QPushButton("[Search] COMPARE FILES")
        self.compare_btn.setMinimumHeight(40)
        self.compare_btn.clicked.connect(self._compare_files)
        layout.addWidget(self.compare_btn)
        
        # Results
        results_group = QGroupBox("> COMPARISON RESULTS")
        results_layout = QVBoxLayout()
        
        self.compare_table = QTableWidget()
        self.compare_table.setColumnCount(4)
        self.compare_table.setHorizontalHeaderLabels(["Offset", "File A", "File B", "Difference"])
        self.compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        results_layout.addWidget(self.compare_table)
        
        # Summary
        summary_layout = QHBoxLayout()
        self.diff_count_label = QLabel("Differences: 0")
        self.diff_count_label.setStyleSheet(f"color: {self.COLORS['cyan']}; font-weight: bold;")
        summary_layout.addWidget(self.diff_count_label)
        
        self.export_diff_btn = QPushButton("[Save] Export Diff")
        self.export_diff_btn.clicked.connect(self._export_diff)
        summary_layout.addWidget(self.export_diff_btn)
        
        summary_layout.addStretch()
        results_layout.addLayout(summary_layout)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        widget.setLayout(layout)
        return widget
    
    def _create_checksum_tab(self) -> QWidget:
        """Create checksum calculation interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # File Selection
        file_group = QGroupBox("> SELECT FILE")
        file_layout = QHBoxLayout()
        
        self.checksum_file = QLineEdit()
        self.checksum_file.setReadOnly(True)
        self.checksum_file.setPlaceholderText("Select file for checksum calculation...")
        file_layout.addWidget(self.checksum_file)
        
        self.checksum_browse_btn = QPushButton("[Folder] Browse")
        self.checksum_browse_btn.clicked.connect(self._browse_checksum_file)
        file_layout.addWidget(self.checksum_browse_btn)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Checksum Types
        types_group = QGroupBox("> CHECKSUM ALGORITHMS")
        types_layout = QGridLayout()
        
        checksums = [
            ("CRC-16:", "crc16"),
            ("CRC-32:", "crc32"),
            ("MD5:", "md5"),
            ("SHA-1:", "sha1"),
            ("SHA-256:", "sha256"),
            ("Simple Sum:", "sum"),
        ]
        
        self.checksum_fields = {}
        for i, (label, key) in enumerate(checksums):
            row = i // 2
            col = (i % 2) * 2
            types_layout.addWidget(QLabel(label), row, col)
            field = QLineEdit()
            field.setReadOnly(True)
            self.checksum_fields[key] = field
            types_layout.addWidget(field, row, col + 1)
        
        types_group.setLayout(types_layout)
        layout.addWidget(types_group)
        
        # Calculate button
        self.calc_checksum_btn = QPushButton("🧮 CALCULATE ALL CHECKSUMS")
        self.calc_checksum_btn.setMinimumHeight(40)
        self.calc_checksum_btn.clicked.connect(self._calculate_checksums)
        layout.addWidget(self.calc_checksum_btn)
        
        # CKS Correction (FCA specific)
        cks_group = QGroupBox("> FCA CKS CORRECTION")
        cks_layout = QVBoxLayout()
        
        cks_info = QLabel("For FCA BCM dumps, calculate and correct the CKS (Checksum) block.")
        cks_info.setStyleSheet(f"color: {self.COLORS['text_dim']}; font-style: italic;")
        cks_info.setWordWrap(True)
        cks_layout.addWidget(cks_info)
        
        cks_btn_layout = QHBoxLayout()
        self.verify_cks_btn = QPushButton("[OK] Verify CKS")
        self.verify_cks_btn.clicked.connect(self._verify_cks)
        cks_btn_layout.addWidget(self.verify_cks_btn)
        
        self.fix_cks_btn = QPushButton("🔧 Fix CKS")
        self.fix_cks_btn.clicked.connect(self._fix_cks)
        cks_btn_layout.addWidget(self.fix_cks_btn)
        
        cks_btn_layout.addStretch()
        cks_layout.addLayout(cks_btn_layout)
        
        self.cks_result = QLabel("CKS Status: --")
        self.cks_result.setStyleSheet(f"color: {self.COLORS['cyan']};")
        cks_layout.addWidget(self.cks_result)
        
        cks_group.setLayout(cks_layout)
        layout.addWidget(cks_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_log_tab(self) -> QWidget:
        """Create operation log interface."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Controls
        controls = QHBoxLayout()
        
        self.clear_log_btn = QPushButton("[Clear] Clear Log")
        self.clear_log_btn.clicked.connect(self._clear_log)
        controls.addWidget(self.clear_log_btn)
        
        self.export_log_btn = QPushButton("[Save] Export Log")
        self.export_log_btn.clicked.connect(self._export_log)
        controls.addWidget(self.export_log_btn)
        
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
        """Connect signals."""
        self.read_start.textChanged.connect(self._update_read_length)
        self.read_end.textChanged.connect(self._update_read_length)
        
        if self.can_interface:
            self.can_interface.frame_received.connect(self._handle_frame)
    
    def _apply_cyberninja_theme(self):
        """Apply CyberNinja dark theme."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.COLORS['bg_dark']};
                color: {self.COLORS['text']};
                font-family: Consolas, 'Courier New', monospace;
            }}
            QGroupBox {{
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                color: {self.COLORS['cyan']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            QPushButton {{
                background-color: {self.COLORS['bg_panel']};
                border: 1px solid {self.COLORS['cyan']}60;
                border-radius: 5px;
                padding: 8px 15px;
                color: {self.COLORS['cyan']};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.COLORS['cyan']};
                color: {self.COLORS['bg_dark']};
            }}
            QPushButton:disabled {{
                background-color: #333;
                color: #555;
                border-color: #444;
            }}
            QLineEdit {{
                background-color: {self.COLORS['bg_input']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                padding: 6px;
                color: {self.COLORS['text']};
            }}
            QLineEdit:focus {{
                border-color: {self.COLORS['cyan']};
            }}
            QLineEdit:read-only {{
                background-color: {self.COLORS['bg_panel']};
            }}
            QComboBox {{
                background-color: {self.COLORS['bg_input']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                padding: 6px;
                color: {self.COLORS['cyan']};
            }}
            QComboBox:hover {{
                border-color: {self.COLORS['cyan']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {self.COLORS['bg_panel']};
                color: {self.COLORS['text']};
                selection-background-color: {self.COLORS['cyan']};
                selection-color: {self.COLORS['bg_dark']};
            }}
            QTextEdit {{
                background-color: {self.COLORS['bg_input']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                color: {self.COLORS['text']};
            }}
            QTableWidget {{
                background-color: {self.COLORS['bg_input']};
                gridline-color: {self.COLORS['cyan']}30;
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
            }}
            QTableWidget::item {{
                padding: 5px;
            }}
            QHeaderView::section {{
                background-color: {self.COLORS['bg_panel']};
                color: {self.COLORS['cyan']};
                border: none;
                padding: 8px;
                font-weight: bold;
            }}
            QProgressBar {{
                border: 1px solid {self.COLORS['cyan']}60;
                border-radius: 5px;
                text-align: center;
                background-color: {self.COLORS['bg_panel']};
                color: {self.COLORS['text']};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {self.COLORS['cyan']}, stop:1 {self.COLORS['magenta']});
                border-radius: 4px;
            }}
            QTabWidget::pane {{
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {self.COLORS['bg_panel']};
                color: {self.COLORS['text']};
                padding: 10px 20px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {self.COLORS['cyan']}40, stop:1 {self.COLORS['magenta']}40);
                color: {self.COLORS['cyan']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {self.COLORS['cyan']}20;
            }}
            QCheckBox {{
                color: {self.COLORS['text']};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {self.COLORS['cyan']}60;
                border-radius: 3px;
                background-color: {self.COLORS['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.COLORS['cyan']};
            }}
            QLabel {{
                color: {self.COLORS['text']};
            }}
        """)
        
        # Status bar special styling
        self.status_bar.setStyleSheet(f"""
            background-color: {self.COLORS['bg_panel']};
            color: {self.COLORS['cyan']};
            padding: 8px;
            border: 1px solid {self.COLORS['cyan']}40;
            border-radius: 4px;
            font-weight: bold;
        """)
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    def _on_chip_changed(self, chip_name: str):
        """Handle chip profile change."""
        self.current_chip = CHIP_PROFILES.get(chip_name)
        if self.current_chip:
            self.manufacturer_label.setText(self.current_chip.manufacturer)
            self.flash_size_label.setText(self._format_size(self.current_chip.flash_size))
            self.eeprom_size_label.setText(self._format_size(self.current_chip.eeprom_size))
            self.page_size_label.setText(f"{self.current_chip.page_size} bytes")
            self.chip_notes.setText(self.current_chip.notes)
            
            # Update default read range to EEPROM size
            self.read_end.setText(f"0x{self.current_chip.eeprom_size - 1:04X}")
            
            self._log(f"Chip profile changed: {chip_name}")
    
    def _update_read_length(self):
        """Update read length display."""
        try:
            start = int(self.read_start.text(), 16)
            end = int(self.read_end.text(), 16)
            length = end - start + 1
            self.read_length.setText(f"{length:,} bytes")
        except ValueError:
            self.read_length.setText("Invalid range")
    
    def _set_full_eeprom_range(self):
        """Set address range to full EEPROM."""
        if self.current_chip:
            self.read_start.setText("0x0000")
            self.read_end.setText(f"0x{self.current_chip.eeprom_size - 1:04X}")
    
    def _handle_frame(self, frame: CANFrame):
        """Handle incoming CAN frame during read/write operations."""
        # Process UDS responses for read/write operations
        if frame.data and len(frame.data) > 0:
            sid = frame.data[0]
            
            # Read Memory response (0x63 = positive response to 0x23)
            if sid == 0x63 and self.operation_in_progress:
                self._process_read_response(frame.data[1:])
            
            # Write Memory response (0x7D = positive response to 0x3D)
            elif sid == 0x7D and self.operation_in_progress:
                self._process_write_response(frame.data)
            
            # Negative response
            elif sid == 0x7F:
                self._handle_negative_response(frame.data)
    
    # =========================================================================
    # Read Operations
    # =========================================================================
    def _start_read(self):
        """Start EEPROM read operation."""
        try:
            start = int(self.read_start.text(), 16)
            end = int(self.read_end.text(), 16)
        except ValueError:
            self._log("Invalid address format", "error")
            return
        
        if start >= end:
            self._log("Start address must be less than end address", "error")
            return
        
        self.read_buffer = bytearray()
        self.current_address = start
        self.end_address = end
        self.operation_in_progress = True
        
        self.read_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(end - start + 1)
        self.progress_bar.setValue(0)
        
        self._log(f"Starting read: 0x{start:04X} to 0x{end:04X}")
        self._update_status(f"Reading from 0x{start:04X}...")
        
        # Start read loop (simulated for now)
        self._simulate_read()
    
    def _simulate_read(self):
        """Simulate read operation for testing."""
        import random
        
        # Simulate reading data
        length = self.end_address - int(self.read_start.text(), 16) + 1
        self.read_buffer = bytearray([random.randint(0, 255) for _ in range(length)])
        
        self._display_read_data()
        self._read_complete()
    
    def _process_read_response(self, data: List[int]):
        """Process read memory response."""
        self.read_buffer.extend(data)
        self.current_address += len(data)
        
        progress = len(self.read_buffer)
        self.progress_bar.setValue(progress)
        
        if self.current_address > self.end_address:
            self._read_complete()
        else:
            # Request next chunk
            self._request_next_chunk()
    
    def _request_next_chunk(self):
        """Request next chunk of data."""
        if not self.operation_in_progress:
            return
        
        chunk_size = min(self.current_chip.page_size if self.current_chip else 256,
                        self.end_address - self.current_address + 1)
        
        # Send read memory request: 0x23 + address (3 bytes) + length (1 byte)
        addr_hi = (self.current_address >> 16) & 0xFF
        addr_mid = (self.current_address >> 8) & 0xFF
        addr_lo = self.current_address & 0xFF
        
        data = [0x23, addr_hi, addr_mid, addr_lo, chunk_size]
        self._send_frame(data)
    
    def _read_complete(self):
        """Handle read completion."""
        self.operation_in_progress = False
        self.read_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        self._log(f"Read complete: {len(self.read_buffer)} bytes", "success")
        self._update_status(f" READ COMPLETE  {len(self.read_buffer)} bytes")
        self._display_read_data()
    
    def _display_read_data(self):
        """Display read data in preview."""
        if not self.read_buffer:
            return
        
        # Format as hex dump
        lines = []
        for i in range(0, min(len(self.read_buffer), 512), 16):  # Show first 512 bytes
            offset = f"{i:06X}"
            hex_bytes = ' '.join(f"{b:02X}" for b in self.read_buffer[i:i+16])
            ascii_chars = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in self.read_buffer[i:i+16])
            lines.append(f"{offset}  {hex_bytes:<48}  {ascii_chars}")
        
        if len(self.read_buffer) > 512:
            lines.append(f"\n... [{len(self.read_buffer) - 512} more bytes] ...")
        
        self.read_preview.setText('\n'.join(lines))
    
    def _save_dump(self):
        """Save read buffer to file."""
        if not self.read_buffer:
            self._log("No data to save", "warning")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"dump_{timestamp}.bin"
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Dump", default_name, "Binary Files (*.bin);;All Files (*)"
        )
        
        if path:
            with open(path, 'wb') as f:
                f.write(self.read_buffer)
            self._log(f"Dump saved: {path}", "success")
    
    def _stop_operation(self):
        """Stop current operation."""
        self.operation_in_progress = False
        self.read_btn.setEnabled(True)
        self.write_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.write_stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self._log("Operation stopped by user", "warning")
        self._update_status(" STOPPED ")
    
    # =========================================================================
    # Write Operations
    # =========================================================================
    def _browse_write_file(self):
        """Browse for file to write."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", "Binary Files (*.bin);;All Files (*)"
        )
        
        if path:
            self.write_file_path.setText(path)
            
            # Read file and update info
            with open(path, 'rb') as f:
                self.write_buffer = bytearray(f.read())
            
            self.write_file_size.setText(self._format_size(len(self.write_buffer)))
            
            # Calculate checksum
            checksum = sum(self.write_buffer) & 0xFFFFFFFF
            self.write_file_checksum.setText(f"0x{checksum:08X}")
            
            self._log(f"Loaded file: {path} ({len(self.write_buffer)} bytes)")
    
    def _start_write(self):
        """Start EEPROM write operation."""
        if not self.write_buffer:
            self._log("No file loaded", "error")
            return
        
        # Confirm
        result = QMessageBox.warning(
            self, "[!] Confirm Write",
            f"You are about to write {len(self.write_buffer)} bytes to EEPROM.\n\n"
            "This operation can damage the ECU if interrupted.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        self._log("Write operation started (SIMULATED)", "warning")
        self._update_status(" WRITE SIMULATED  No actual write performed")
        
        # In real implementation, would send write commands here
    
    # =========================================================================
    # Compare Operations
    # =========================================================================
    def _browse_compare_file(self, which: str):
        """Browse for comparison file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", "Binary Files (*.bin);;All Files (*)"
        )
        
        if path:
            if which == 'a':
                self.compare_file_a.setText(path)
            else:
                self.compare_file_b.setText(path)
    
    def _compare_files(self):
        """Compare two binary files."""
        path_a = self.compare_file_a.text()
        path_b = self.compare_file_b.text()
        
        if not path_a or not path_b:
            self._log("Please select both files", "error")
            return
        
        try:
            with open(path_a, 'rb') as f:
                data_a = f.read()
            with open(path_b, 'rb') as f:
                data_b = f.read()
        except Exception as e:
            self._log(f"Error reading files: {e}", "error")
            return
        
        # Find differences
        self.compare_table.setRowCount(0)
        diff_count = 0
        max_len = max(len(data_a), len(data_b))
        
        for i in range(max_len):
            byte_a = data_a[i] if i < len(data_a) else None
            byte_b = data_b[i] if i < len(data_b) else None
            
            if byte_a != byte_b:
                row = self.compare_table.rowCount()
                self.compare_table.insertRow(row)
                
                self.compare_table.setItem(row, 0, QTableWidgetItem(f"0x{i:06X}"))
                self.compare_table.setItem(row, 1, QTableWidgetItem(f"{byte_a:02X}" if byte_a is not None else "--"))
                self.compare_table.setItem(row, 2, QTableWidgetItem(f"{byte_b:02X}" if byte_b is not None else "--"))
                self.compare_table.setItem(row, 3, QTableWidgetItem("DIFF"))
                
                # Highlight
                for col in range(4):
                    item = self.compare_table.item(row, col)
                    if item:
                        item.setBackground(QColor(self.COLORS['red'] + "40"))
                
                diff_count += 1
                
                if diff_count >= 1000:  # Limit display
                    break
        
        self.diff_count_label.setText(f"Differences: {diff_count}" + (" (showing first 1000)" if diff_count >= 1000 else ""))
        self._log(f"Comparison complete: {diff_count} differences found", "success" if diff_count == 0 else "warning")
    
    def _export_diff(self):
        """Export differences to file."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Diff", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w') as f:
                f.write("Offset,File A,File B,Status\n")
                for row in range(self.compare_table.rowCount()):
                    line = []
                    for col in range(4):
                        item = self.compare_table.item(row, col)
                        line.append(item.text() if item else "")
                    f.write(",".join(line) + "\n")
            self._log(f"Diff exported to {path}", "success")
    
    # =========================================================================
    # Checksum Operations
    # =========================================================================
    def _browse_checksum_file(self):
        """Browse for checksum file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", "Binary Files (*.bin);;All Files (*)"
        )
        if path:
            self.checksum_file.setText(path)
    
    def _calculate_checksums(self):
        """Calculate all checksums for file."""
        path = self.checksum_file.text()
        if not path:
            self._log("No file selected", "error")
            return
        
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except Exception as e:
            self._log(f"Error reading file: {e}", "error")
            return
        
        import hashlib
        
        # Simple sum
        simple_sum = sum(data) & 0xFFFFFFFF
        self.checksum_fields['sum'].setText(f"0x{simple_sum:08X}")
        
        # CRC-16 (simple implementation)
        crc16 = 0xFFFF
        for byte in data:
            crc16 ^= byte
            for _ in range(8):
                if crc16 & 1:
                    crc16 = (crc16 >> 1) ^ 0xA001
                else:
                    crc16 >>= 1
        self.checksum_fields['crc16'].setText(f"0x{crc16:04X}")
        
        # CRC-32
        import binascii
        crc32 = binascii.crc32(data) & 0xFFFFFFFF
        self.checksum_fields['crc32'].setText(f"0x{crc32:08X}")
        
        # MD5
        md5 = hashlib.md5(data).hexdigest().upper()
        self.checksum_fields['md5'].setText(md5)
        
        # SHA-1
        sha1 = hashlib.sha1(data).hexdigest().upper()
        self.checksum_fields['sha1'].setText(sha1)
        
        # SHA-256
        sha256 = hashlib.sha256(data).hexdigest().upper()
        self.checksum_fields['sha256'].setText(sha256)
        
        self._log("Checksums calculated", "success")
    
    def _verify_cks(self):
        """Verify FCA CKS block."""
        path = self.checksum_file.text()
        if not path:
            self._log("No file selected", "error")
            return
        
        self._log("CKS verification: Feature requires specific FCA algorithm", "warning")
        self.cks_result.setText("CKS Status: Verification not implemented")
    
    def _fix_cks(self):
        """Fix FCA CKS block."""
        self._log("CKS fix: Feature requires specific FCA algorithm", "warning")
        QMessageBox.information(self, "CKS Fix",
            "CKS correction requires manufacturer-specific algorithms.\n\n"
            "This feature would recalculate the checksum block for FCA BCM dumps.")
    
    # =========================================================================
    # Helper Functions
    # =========================================================================
    def _format_size(self, size: int) -> str:
        """Format byte size to human readable."""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size} bytes"
    
    def _send_frame(self, data: List[int]):
        """Send CAN frame."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        frame = CANFrame(timestamp, "7E0", data, Direction.TX)
        self.can_interface.send_frame(frame)
    
    def _handle_negative_response(self, data: List[int]):
        """Handle negative UDS response."""
        if len(data) >= 3:
            service = data[1]
            nrc = data[2]
            self._log(f"Negative response: Service 0x{service:02X}, NRC 0x{nrc:02X}", "error")
    
    def _log(self, message: str, level: str = "info"):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        colors = {
            "info": self.COLORS['text'],
            "success": self.COLORS['green'],
            "warning": self.COLORS['yellow'],
            "error": self.COLORS['red'],
        }
        color = colors.get(level, self.COLORS['text'])
        
        html = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.log_display.append(html)
    
    def _update_status(self, message: str):
        """Update status bar."""
        self.status_bar.setText(message)
    
    def _clear_log(self):
        """Clear log display."""
        self.log_display.clear()
    
    def _export_log(self):
        """Export log to file."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt)")
        if path:
            with open(path, 'w') as f:
                f.write(self.log_display.toPlainText())
            self._log(f"Log exported to {path}", "success")
    
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
    tab = ECUFlashTab()
    tab.resize(1100, 800)
    tab.show()
    sys.exit(app.exec_())
