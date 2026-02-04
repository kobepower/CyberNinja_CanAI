# gui/tabs/settings_tab.py

"""

                     CYBERNINJA SETTINGS                                       
                   Configuration • Preferences • Database                      

"""

import logging
import json
import os
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTabWidget, QFileDialog, QMessageBox, QTextEdit,
    QGridLayout, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from backend.can_interface import CANInterface

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    """Application Settings - CyberNinja Style"""
    
    settings_changed = pyqtSignal(dict)
    
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
    }
    
    DEFAULT_SETTINGS = {
        "interface": {"baudrate": 500000, "timeout": 1.0, "reconnect_attempts": 5,
                     "auto_reconnect": True, "simulation_interval": 0.5},
        "display": {"dark_mode": True, "auto_scroll": True, "max_frames": 1000,
                   "show_ascii": True, "highlight_uds": True},
        "paths": {"did_database": "", "dump_folder": "", "log_folder": ""},
        "uds": {"default_tx_id": "7E0", "default_rx_id": "7E8",
               "tester_present_interval": 2000, "response_timeout": 3000}
    }
    
    def __init__(self, can_interface: Optional[CANInterface] = None):
        super().__init__()
        self.can_interface = can_interface
        self.settings = self.DEFAULT_SETTINGS.copy()
        self.settings_file = os.path.expanduser("~/.canai_pro_settings.json")
        
        self._load_settings()
        self._init_ui()
        self._apply_theme()
        self._populate_fields()
    
    def _init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        
        header = QLabel(" CYBERNINJA SETTINGS ")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {self.COLORS['cyan']}; padding: 15px;")
        main_layout.addWidget(header)
        
        tabs = QTabWidget()
        tabs.addTab(self._create_interface_tab(), "🔌 INTERFACE")
        tabs.addTab(self._create_display_tab(), "🖥️ DISPLAY")
        tabs.addTab(self._create_about_tab(), "[Info] ABOUT")
        main_layout.addWidget(tabs)
        
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("[Save] SAVE SETTINGS")
        self.save_btn.setMinimumHeight(45)
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)
        
        self.reset_btn = QPushButton("[Refresh] RESET TO DEFAULTS")
        self.reset_btn.setMinimumHeight(45)
        self.reset_btn.clicked.connect(self._reset_settings)
        btn_layout.addWidget(self.reset_btn)
        main_layout.addLayout(btn_layout)
        
        self.status_label = QLabel("Settings loaded")
        self.status_label.setStyleSheet(f"color: {self.COLORS['cyan']}; padding: 8px; background-color: {self.COLORS['bg_panel']}; border-radius: 4px;")
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)
    
    def _create_interface_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        
        serial_group = QGroupBox("> SERIAL INTERFACE")
        serial_layout = QFormLayout()
        
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(["115200", "250000", "500000", "1000000"])
        serial_layout.addRow("Baudrate:", self.baudrate_combo)
        
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 10.0)
        self.timeout_spin.setValue(1.0)
        self.timeout_spin.setSuffix(" sec")
        serial_layout.addRow("Timeout:", self.timeout_spin)
        
        self.reconnect_spin = QSpinBox()
        self.reconnect_spin.setRange(1, 20)
        self.reconnect_spin.setValue(5)
        serial_layout.addRow("Reconnect Attempts:", self.reconnect_spin)
        
        self.auto_reconnect_check = QCheckBox("Auto-reconnect on disconnect")
        self.auto_reconnect_check.setChecked(True)
        serial_layout.addRow("", self.auto_reconnect_check)
        
        serial_group.setLayout(serial_layout)
        layout.addWidget(serial_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_display_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        
        theme_group = QGroupBox("> DISPLAY OPTIONS")
        theme_layout = QFormLayout()
        
        self.dark_mode_check = QCheckBox("Dark Mode (CyberNinja)")
        self.dark_mode_check.setChecked(True)
        theme_layout.addRow("", self.dark_mode_check)
        
        self.auto_scroll_check = QCheckBox("Auto-scroll to new frames")
        self.auto_scroll_check.setChecked(True)
        theme_layout.addRow("", self.auto_scroll_check)
        
        self.max_frames_spin = QSpinBox()
        self.max_frames_spin.setRange(100, 10000)
        self.max_frames_spin.setValue(1000)
        theme_layout.addRow("Max Frames:", self.max_frames_spin)
        
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_about_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        
        logo = QLabel(" CANAI PRO ")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {self.COLORS['cyan']}; padding: 20px;")
        layout.addWidget(logo)
        
        subtitle = QLabel("CyberNinja Edition • Version 1.0.0")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {self.COLORS['magenta']};")
        layout.addWidget(subtitle)
        
        desc = QLabel("Professional CAN bus diagnostic and key programming tool\\nfor automotive locksmiths.\\n\\nBuilt with love by Kobe's Keys\\n\\n MAMBA MENTALITY ")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"color: {self.COLORS['text']}; padding: 30px;")
        layout.addWidget(desc)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _apply_theme(self):
        self.setStyleSheet(f"""
            QWidget {{ background-color: {self.COLORS['bg_dark']}; color: {self.COLORS['text']}; font-family: Consolas; }}
            QGroupBox {{ border: 1px solid {self.COLORS['cyan']}40; border-radius: 8px; margin-top: 12px; padding-top: 10px; color: {self.COLORS['cyan']}; font-weight: bold; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
            QPushButton {{ background-color: {self.COLORS['bg_panel']}; border: 1px solid {self.COLORS['cyan']}60; border-radius: 5px; padding: 8px 15px; color: {self.COLORS['cyan']}; font-weight: bold; }}
            QPushButton:hover {{ background-color: {self.COLORS['cyan']}; color: {self.COLORS['bg_dark']}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: {self.COLORS['bg_input']}; border: 1px solid {self.COLORS['cyan']}40; border-radius: 4px; padding: 6px; color: {self.COLORS['text']}; }}
            QCheckBox {{ color: {self.COLORS['text']}; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {self.COLORS['cyan']}60; border-radius: 3px; background-color: {self.COLORS['bg_input']}; }}
            QCheckBox::indicator:checked {{ background-color: {self.COLORS['cyan']}; }}
            QTabWidget::pane {{ border: 1px solid {self.COLORS['cyan']}40; }}
            QTabBar::tab {{ background-color: {self.COLORS['bg_panel']}; color: {self.COLORS['text']}; padding: 10px 20px; }}
            QTabBar::tab:selected {{ background-color: {self.COLORS['cyan']}40; color: {self.COLORS['cyan']}; }}
        """)
    
    def _populate_fields(self):
        baud_idx = self.baudrate_combo.findText(str(self.settings["interface"]["baudrate"]))
        if baud_idx >= 0: self.baudrate_combo.setCurrentIndex(baud_idx)
        self.timeout_spin.setValue(self.settings["interface"]["timeout"])
        self.reconnect_spin.setValue(self.settings["interface"]["reconnect_attempts"])
        self.auto_reconnect_check.setChecked(self.settings["interface"]["auto_reconnect"])
        self.dark_mode_check.setChecked(self.settings["display"]["dark_mode"])
        self.auto_scroll_check.setChecked(self.settings["display"]["auto_scroll"])
        self.max_frames_spin.setValue(self.settings["display"]["max_frames"])
    
    def _load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                for key in self.DEFAULT_SETTINGS:
                    if key in loaded:
                        self.settings[key].update(loaded[key])
            except: pass
    
    def _save_settings(self):
        self.settings["interface"]["baudrate"] = int(self.baudrate_combo.currentText())
        self.settings["interface"]["timeout"] = self.timeout_spin.value()
        self.settings["interface"]["reconnect_attempts"] = self.reconnect_spin.value()
        self.settings["interface"]["auto_reconnect"] = self.auto_reconnect_check.isChecked()
        self.settings["display"]["dark_mode"] = self.dark_mode_check.isChecked()
        self.settings["display"]["auto_scroll"] = self.auto_scroll_check.isChecked()
        self.settings["display"]["max_frames"] = self.max_frames_spin.value()
        
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            self.status_label.setText("[OK] Settings saved successfully")
            self.settings_changed.emit(self.settings)
        except Exception as e:
            self.status_label.setText(f"[X] Failed to save: {e}")
    
    def _reset_settings(self):
        if QMessageBox.question(self, "Confirm", "Reset all settings?") == QMessageBox.Yes:
            self.settings = self.DEFAULT_SETTINGS.copy()
            self._populate_fields()
            self.status_label.setText("[Refresh] Settings reset to defaults")
    
    def set_can_interface(self, interface: CANInterface):
        self.can_interface = interface


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    tab = SettingsTab()
    tab.resize(800, 600)
    tab.show()
    sys.exit(app.exec_())
