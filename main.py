#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CANAI PRO - CyberNinja Edition
Professional CAN Bus Diagnostic and Key Programming Tool
Built by Kobe's Keys
"""

# ----------------------------------------------------------------------------------
# 1) Imports
# ----------------------------------------------------------------------------------
import os
import sys
import logging
import traceback

print("[DEBUG] Starting imports...")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QMessageBox,
    QAction, QDesktopWidget, QStatusBar, QLabel, QHBoxLayout,
    QVBoxLayout, QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

print("[DEBUG] PyQt5 imported OK")

# Import tabs with individual try/except
print("[DEBUG] Importing CANMonitorTab...")
try:
    from gui.tabs.can_monitor_tab import CANMonitorTab
    print("[DEBUG] CANMonitorTab imported OK")
except Exception as e:
    print(f"[ERROR] CANMonitorTab import failed: {e}")
    import traceback
    traceback.print_exc()
    CANMonitorTab = None

print("[DEBUG] Importing KeyToolsTab...")
try:
    from gui.tabs.key_tools_tab import KeyToolsTab
    print("[DEBUG] KeyToolsTab imported OK")
except Exception as e:
    print(f"[ERROR] KeyToolsTab import failed: {e}")
    import traceback
    traceback.print_exc()
    KeyToolsTab = None

print("[DEBUG] Importing DiagnosticsTab...")
try:
    from gui.tabs.diagnostics_tab import DiagnosticsTab
    print("[DEBUG] DiagnosticsTab imported OK")
except Exception as e:
    print(f"[ERROR] DiagnosticsTab import failed: {e}")
    import traceback
    traceback.print_exc()
    DiagnosticsTab = None

print("[DEBUG] Importing ECUFlashTab...")
try:
    from gui.tabs.ecu_flash_tab import ECUFlashTab
    print("[DEBUG] ECUFlashTab imported OK")
except Exception as e:
    print(f"[ERROR] ECUFlashTab import failed: {e}")
    import traceback
    traceback.print_exc()
    ECUFlashTab = None

print("[DEBUG] Importing HexAnalyzerTab...")
try:
    from gui.tabs.hex_analyzer_tab import HexAnalyzerTab
    print("[DEBUG] HexAnalyzerTab imported OK")
except Exception as e:
    print(f"[ERROR] HexAnalyzerTab import failed: {e}")
    import traceback
    traceback.print_exc()
    HexAnalyzerTab = None

print("[DEBUG] Importing SettingsTab...")
try:
    from gui.tabs.settings_tab import SettingsTab
    print("[DEBUG] SettingsTab imported OK")
except Exception as e:
    print(f"[ERROR] SettingsTab import failed: {e}")
    import traceback
    traceback.print_exc()
    SettingsTab = None

# Import backend
from backend.can_interface import CANInterface
print("[DEBUG] CANInterface imported OK")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# 2) CyberNinja Theme Colors
# ----------------------------------------------------------------------------------
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

# ----------------------------------------------------------------------------------
# 3) MainWindow Class
# ----------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    """CyberNinja Main Window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CANAI PRO - CyberNinja Edition")
        
        # Create shared CAN interface - slow simulation for stability
        self.can_interface = CANInterface(simulate=True, reconnect_attempts=3, sim_interval=1.0)
        
        # Tab references
        self.can_monitor_tab = None
        self.key_tools_tab = None
        self.diagnostics_tab = None
        self.ecu_flash_tab = None
        self.hex_analyzer_tab = None
        self.settings_tab = None
        
        self._init_ui()
        self._init_menu()
        self._center_window()
        self._apply_theme()
        
        # DON'T auto-start simulation - prevents UI freeze
        # self.can_interface.start()
        
        logger.info("[MainWindow] CyberNinja CanAI Pro initialized")
    
    def _init_ui(self):
        """Initialize the main UI."""
        print("[DEBUG] Initializing UI...")
        
        # Central widget
        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        print("[DEBUG] Creating header...")
        header = self._create_header()
        main_layout.addWidget(header)
        
        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(True)
        
        # Create tabs with error handling
        print("[DEBUG] Creating CAN Monitor tab...")
        try:
            self.can_monitor_tab = CANMonitorTab()
            print("[DEBUG] CAN Monitor tab OK")
        except Exception as e:
            print(f"[ERROR] CAN Monitor tab failed: {e}")
            traceback.print_exc()
            self.can_monitor_tab = QWidget()
        
        print("[DEBUG] Creating Key Tools tab...")
        try:
            self.key_tools_tab = KeyToolsTab(self.can_interface)
            print("[DEBUG] Key Tools tab OK")
        except Exception as e:
            print(f"[ERROR] Key Tools tab failed: {e}")
            traceback.print_exc()
            self.key_tools_tab = QWidget()
        
        print("[DEBUG] Creating Diagnostics tab...")
        try:
            self.diagnostics_tab = DiagnosticsTab(self.can_interface)
            print("[DEBUG] Diagnostics tab OK")
        except Exception as e:
            print(f"[ERROR] Diagnostics tab failed: {e}")
            traceback.print_exc()
            self.diagnostics_tab = QWidget()
        
        print("[DEBUG] Creating ECU Flash tab...")
        try:
            self.ecu_flash_tab = ECUFlashTab(self.can_interface)
            print("[DEBUG] ECU Flash tab OK")
        except Exception as e:
            print(f"[ERROR] ECU Flash tab failed: {e}")
            traceback.print_exc()
            self.ecu_flash_tab = QWidget()
        
        print("[DEBUG] Creating HEX Analyzer tab...")
        try:
            self.hex_analyzer_tab = HexAnalyzerTab()
            print("[DEBUG] HEX Analyzer tab OK")
        except Exception as e:
            print(f"[ERROR] HEX Analyzer tab failed: {e}")
            traceback.print_exc()
            self.hex_analyzer_tab = QWidget()
        
        print("[DEBUG] Creating Settings tab...")
        try:
            self.settings_tab = SettingsTab(self.can_interface)
            print("[DEBUG] Settings tab OK")
        except Exception as e:
            print(f"[ERROR] Settings tab failed: {e}")
            traceback.print_exc()
            self.settings_tab = QWidget()
        
        # Add tabs
        print("[DEBUG] Adding tabs to widget...")
        self.tabs.addTab(self.can_monitor_tab, "CAN MONITOR")
        self.tabs.addTab(self.key_tools_tab, "KEY TOOLS")
        self.tabs.addTab(self.diagnostics_tab, "DIAGNOSTICS")
        self.tabs.addTab(self.ecu_flash_tab, "ECU FLASH")
        self.tabs.addTab(self.hex_analyzer_tab, "HEX ANALYZER")
        self.tabs.addTab(self.settings_tab, "SETTINGS")
        
        main_layout.addWidget(self.tabs)
        
        # Status bar
        print("[DEBUG] Creating status bar...")
        self.status_bar = QStatusBar()
        self._init_status_bar()
        self.setStatusBar(self.status_bar)
        
        central.setLayout(main_layout)
        self.setCentralWidget(central)
        print("[DEBUG] UI initialization complete")
    
    def _create_header(self):
        """Create the header bar."""
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['bg_dark']}, 
                    stop:0.5 {COLORS['bg_panel']},
                    stop:1 {COLORS['bg_dark']});
                border-bottom: 1px solid {COLORS['cyan']}40;
            }}
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 0, 20, 0)
        
        # Logo
        logo = QLabel("CANAI PRO")
        logo.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {COLORS['cyan']};
            letter-spacing: 3px;
        """)
        layout.addWidget(logo)
        
        layout.addStretch()
        
        # Version
        version = QLabel("CyberNinja Edition v1.0")
        version.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        layout.addWidget(version)
        
        # Connection indicator
        self.conn_indicator = QLabel("SIMULATION")
        self.conn_indicator.setStyleSheet(f"""
            color: {COLORS['yellow']};
            font-weight: bold;
            padding: 5px 10px;
            background-color: {COLORS['yellow']}20;
            border-radius: 4px;
        """)
        layout.addWidget(self.conn_indicator)
        
        header.setLayout(layout)
        return header
    
    def _init_menu(self):
        """Create menu bar."""
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text']};
                border-bottom: 1px solid {COLORS['cyan']}30;
            }}
            QMenuBar::item:selected {{
                background-color: {COLORS['cyan']}40;
            }}
            QMenu {{
                background-color: {COLORS['bg_panel']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['cyan']}40;
            }}
            QMenu::item:selected {{
                background-color: {COLORS['cyan']};
                color: {COLORS['bg_dark']};
            }}
        """)
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_action = QAction("&New Session", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_session)
        file_menu.addAction(new_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        sim_action = QAction("&Simulation Mode", self)
        sim_action.setShortcut("Ctrl+Shift+S")
        sim_action.triggered.connect(self._toggle_simulation)
        tools_menu.addAction(sim_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _init_status_bar(self):
        """Initialize status bar."""
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {COLORS['bg_panel']};
                color: {COLORS['text']};
                border-top: 1px solid {COLORS['cyan']}30;
            }}
        """)
        
        # Frame count
        self.frame_count_label = QLabel("Frames: 0")
        self.frame_count_label.setStyleSheet(f"color: {COLORS['cyan']}; padding: 0 10px;")
        self.status_bar.addPermanentWidget(self.frame_count_label)
        
        # Interface status
        self.interface_label = QLabel("Interface: Simulation")
        self.interface_label.setStyleSheet(f"color: {COLORS['green']}; padding: 0 10px;")
        self.status_bar.addPermanentWidget(self.interface_label)
        
        # Update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)
    
    def _apply_theme(self):
        """Apply CyberNinja dark theme."""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['bg_dark']};
            }}
            QTabWidget::pane {{
                border: none;
                background-color: {COLORS['bg_dark']};
            }}
            QTabBar {{
                background-color: {COLORS['bg_dark']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_panel']};
                color: {COLORS['text']};
                padding: 12px 25px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-family: Consolas, monospace;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['cyan']}50, stop:1 {COLORS['magenta']}50);
                color: {COLORS['cyan']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {COLORS['cyan']}20;
            }}
        """)
    
    def _center_window(self):
        """Center window on screen."""
        screen = QDesktopWidget().screenGeometry()
        self.setGeometry(
            (screen.width() - 1400) // 2,
            (screen.height() - 900) // 2,
            1400, 900
        )
    
    def _update_status(self):
        """Update status bar info."""
        if self.can_interface:
            count = self.can_interface.get_frame_count()
            self.frame_count_label.setText(f"Frames: {count:,}")
    
    def _new_session(self):
        """Start new session."""
        if QMessageBox.question(self, "New Session",
            "Clear all data and start a new session?") == QMessageBox.Yes:
            if hasattr(self.can_monitor_tab, 'clear_table'):
                self.can_monitor_tab.clear_table()
            logger.info("New session started")
    
    def _toggle_simulation(self):
        """Toggle simulation mode."""
        self.can_interface.stop()
        self.can_interface = CANInterface(simulate=True)
        self.can_interface.start()
        self.conn_indicator.setText("SIMULATION")
        self.interface_label.setText("Interface: Simulation")
        logger.info("Simulation mode activated")
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(self, "About CanAI Pro",
            "CANAI PRO - CyberNinja Edition\n"
            "Version 1.0.0\n\n"
            "Professional CAN bus diagnostic and\n"
            "key programming tool for automotive locksmiths.\n\n"
            "Built by Kobe's Keys\n"
            "MAMBA MENTALITY")
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.can_interface:
            self.can_interface.stop()
        
        if self.can_monitor_tab and hasattr(self.can_monitor_tab, 'can_interface'):
            self.can_monitor_tab.can_interface.stop()
        
        logger.info("[MainWindow] CanAI Pro closed")
        event.accept()


# ----------------------------------------------------------------------------------
# 4) Main Function
# ----------------------------------------------------------------------------------
def main():
    """Application entry point."""
    print("[DEBUG] Starting CanAI Pro...")
    
    # Create application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set application font
    font = QFont("Consolas", 10)
    app.setFont(font)
    
    # Global exception handler
    def exception_hook(exctype, value, tb):
        print(f"[ERROR] Unhandled exception: {exctype.__name__}: {value}")
        logger.error("Unhandled exception:", exc_info=(exctype, value, tb))
        tb_str = ''.join(traceback.format_tb(tb))
        error_msg = f"{exctype.__name__}: {value}\n\nTraceback:\n{tb_str}"
        print(error_msg)
        QMessageBox.critical(None, "Error", error_msg)
        sys.exit(1)
    
    sys.excepthook = exception_hook
    
    # Create main window
    print("[DEBUG] Creating main window...")
    logger.info("=" * 60)
    logger.info("  CANAI PRO - CyberNinja Edition")
    logger.info("  Starting application...")
    logger.info("=" * 60)
    
    try:
        window = MainWindow()
        print("[DEBUG] Main window created successfully")
    except Exception as e:
        print(f"[ERROR] Failed to create main window: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # Show window
    window.show()
    print("[DEBUG] Window shown, entering event loop...")
    
    # Run event loop
    sys.exit(app.exec_())


# ----------------------------------------------------------------------------------
# 5) Entry Point
# ----------------------------------------------------------------------------------
print("[DEBUG] All imports complete")

if __name__ == "__main__":
    print("[DEBUG] Running main()...")
    main()
