# gui/tabs/hex_analyzer_tab.py

"""

                     CYBERNINJA HEX ANALYZER                                   
              Educational BCM Dump Viewer • Read-Only Analysis                 
                                                                               
  [!]  LEGAL DISCLAIMER - EDUCATIONAL USE ONLY [!]                               
  This tool is READ-ONLY and does NOT modify any data.                         
  Users are solely responsible for compliance with all applicable laws.        

"""

# ----------------------------------------------------------------------------------
# 1) Imports
# ----------------------------------------------------------------------------------
import logging
import os
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QGridLayout, QHeaderView, QSplitter, QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter, QTextDocument

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# 2) Module Offset Definitions (Educational Reference)
# ----------------------------------------------------------------------------------
MODULE_OFFSETS = {
    "Generic / Auto-Detect": {
        "chip": "Unknown",
        "offsets": [
            {"name": "Full File Scan", "start": 0x0000, "end": 0xFFFF, "type": "vin", 
             "note": "Will search entire file for VIN patterns"},
        ]
    },
    "VAG (Audi/VW/Skoda) 24C02": {
        "chip": "24C02 EEPROM (256 bytes)",
        "offsets": [
            {"name": "Cluster Data", "start": 0x0000, "end": 0x00FF, "type": "key", 
             "note": "Instrument cluster EEPROM - mileage, VIN, settings"},
            {"name": "Immo Data", "start": 0x0000, "end": 0x0040, "type": "pin", 
             "note": "Immobilizer data area"},
            {"name": "SKC Area", "start": 0x0010, "end": 0x0020, "type": "pin", 
             "note": "Secret Key Code region"},
        ]
    },
    "VAG (Audi/VW) NEC+24C64": {
        "chip": "NEC MCU + 24C64 EEPROM",
        "offsets": [
            {"name": "VIN Area", "start": 0x0000, "end": 0x0020, "type": "vin", 
             "note": "Vehicle ID storage"},
            {"name": "Key Data", "start": 0x0080, "end": 0x0100, "type": "key", 
             "note": "Transponder key area"},
            {"name": "PIN/CS", "start": 0x0040, "end": 0x0060, "type": "pin", 
             "note": "PIN and component security"},
            {"name": "Mileage", "start": 0x0100, "end": 0x0110, "type": "checksum", 
             "note": "Odometer storage"},
        ]
    },
    "MPC5606B (FCA BCM 2011-2018)": {
        "chip": "Freescale MPC5606B",
        "offsets": [
            {"name": "VIN Primary", "start": 0x0000, "end": 0x0011, "type": "vin", 
             "note": "17-char VIN, often at start of DFLASH"},
            {"name": "VIN Mirror 1", "start": 0x0800, "end": 0x0811, "type": "vin", 
             "note": "Backup VIN location"},
            {"name": "VIN Mirror 2", "start": 0x1000, "end": 0x1011, "type": "vin", 
             "note": "Second backup location"},
            {"name": "PIN Area", "start": 0x0100, "end": 0x0110, "type": "pin", 
             "note": "Security PIN region (encrypted)"},
            {"name": "Key Slots", "start": 0x0200, "end": 0x0280, "type": "key", 
             "note": "Transponder key data area"},
            {"name": "CKS Block", "start": 0x7FF0, "end": 0x8000, "type": "checksum", 
             "note": "Checksum validation block"},
        ]
    },
    "MPC5646C (FCA BCM 2018+)": {
        "chip": "Freescale MPC5646C",
        "offsets": [
            {"name": "VIN Primary", "start": 0x0000, "end": 0x0011, "type": "vin", 
             "note": "Primary VIN storage"},
            {"name": "VIN Mirror", "start": 0x2000, "end": 0x2011, "type": "vin", 
             "note": "Mirrored VIN"},
            {"name": "Security Zone", "start": 0x0080, "end": 0x0100, "type": "pin", 
             "note": "PIN/Security data (encrypted)"},
            {"name": "Key Data", "start": 0x0400, "end": 0x0500, "type": "key", 
             "note": "Key programming area"},
            {"name": "Checksum", "start": 0xFFF0, "end": 0x10000, "type": "checksum", 
             "note": "CKS area at end"},
        ]
    },
    "RH850 (FCA 2019+ RF Hub)": {
        "chip": "Renesas RH850",
        "offsets": [
            {"name": "VIN Storage", "start": 0x0010, "end": 0x0021, "type": "vin", 
             "note": "VIN in RF Hub"},
            {"name": "Fob Data", "start": 0x0100, "end": 0x0200, "type": "key", 
             "note": "Key fob pairing data"},
            {"name": "Rolling Code", "start": 0x0300, "end": 0x0340, "type": "pin", 
             "note": "Rolling code counters"},
            {"name": "CKS", "start": 0x0FF0, "end": 0x1000, "type": "checksum", 
             "note": "Checksum block"},
        ]
    },
    "S12XE (GM BCM)": {
        "chip": "Freescale S12XE",
        "offsets": [
            {"name": "VIN", "start": 0x0000, "end": 0x0011, "type": "vin", 
             "note": "Vehicle Identification Number"},
            {"name": "Theft Deterrent", "start": 0x0020, "end": 0x0040, "type": "pin", 
             "note": "Anti-theft data"},
            {"name": "Key Info", "start": 0x0100, "end": 0x0140, "type": "key", 
             "note": "Key fob data"},
        ]
    },
    "Generic / Unknown": {
        "chip": "Unknown",
        "offsets": [
            {"name": "Scan Full File", "start": 0x0000, "end": 0x0011, "type": "vin", 
             "note": "Will search entire file for VIN pattern"},
        ]
    }
}

# Highlight colors for different data types
HIGHLIGHT_COLORS = {
    "vin": {"bg": "#00ff6650", "fg": "#00ff66"},
    "pin": {"bg": "#ff00aa50", "fg": "#ff00aa"},
    "key": {"bg": "#00f0ff50", "fg": "#00f0ff"},
    "checksum": {"bg": "#ff660050", "fg": "#ff6600"},
    "search": {"bg": "#f0ff0080", "fg": "#000000"},
}

# ----------------------------------------------------------------------------------
# 3) HexAnalyzerTab Class
# ----------------------------------------------------------------------------------
class HexAnalyzerTab(QWidget):
    """
    
      CyberNinja HEX Analyzer - Educational BCM Dump Viewer                    
    
    """
    
    status_updated = pyqtSignal(str, str)
    
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
    
    def __init__(self):
        super().__init__()
        self.current_data: Optional[bytes] = None
        self.current_file: Optional[str] = None
        self.current_module: str = "MPC5606B (FCA BCM 2011-2018)"
        self.highlights: Dict[int, str] = {}
        
        self._init_ui()
        self._apply_theme()
        self._update_offset_list()
        
        logger.info("[HexAnalyzerTab] CyberNinja HEX Analyzer initialized")
    
    def _init_ui(self):
        """Initialize the UI."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(5)  # Tighter spacing
        main_layout.setContentsMargins(10, 5, 10, 5)  # Smaller margins
        
        # Header + Warning combined in one row
        header = self._create_header()
        main_layout.addWidget(header)
        
        # Main content splitter - takes most space
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - HEX viewer (bigger)
        left_panel = self._create_hex_panel()
        splitter.addWidget(left_panel)
        
        # Right side - Info panel (narrower)
        right_panel = self._create_info_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([750, 300])  # More space for hex dump
        main_layout.addWidget(splitter, stretch=1)  # Give it all available space
        
        # Status bar - compact
        self.status_bar = QLabel(" READY - Load a dump file to begin analysis")
        self.status_bar.setStyleSheet(f"""
            color: {self.COLORS['cyan']};
            background-color: {self.COLORS['bg_panel']};
            padding: 5px;
            border-radius: 3px;
        """)
        main_layout.addWidget(self.status_bar)
        
        self.setLayout(main_layout)
    
    def _create_header(self) -> QWidget:
        """Create compact header with centered red warning."""
        frame = QFrame()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 5)
        
        title = QLabel("CYBERNINJA HEX ANALYZER")
        title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {self.COLORS['cyan']};
            letter-spacing: 2px;
        """)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Centered red neon warning with glow effect
        warning = QLabel("[!] EDUCATIONAL USE ONLY - READ-ONLY - NO MODIFICATION [!]")
        warning.setAlignment(Qt.AlignCenter)
        warning.setStyleSheet(f"""
            color: #ff3366;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 15px;
            text-shadow: 0 0 10px #ff3366, 0 0 20px #ff3366;
        """)
        layout.addWidget(warning)
        
        layout.addStretch()
        
        subtitle = QLabel("READ-ONLY")
        subtitle.setStyleSheet(f"color: {self.COLORS['text_dim']}; font-size: 10px;")
        layout.addWidget(subtitle)
        
        frame.setLayout(layout)
        return frame
    
    def _create_hex_panel(self) -> QWidget:
        """Create the HEX viewer panel."""
        panel = QFrame()
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # File controls - compact single row
        file_row = QHBoxLayout()
        
        self.load_btn = QPushButton("[Load] BIN/HEX FILE")
        self.load_btn.setMinimumHeight(30)
        self.load_btn.clicked.connect(self._load_file)
        file_row.addWidget(self.load_btn)
        
        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet(f"color: {self.COLORS['text_dim']};")
        file_row.addWidget(self.file_label)
        
        file_row.addStretch()
        
        # Search in same row
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search HEX or ASCII...")
        self.search_input.setMaximumWidth(200)
        self.search_input.returnPressed.connect(self._search_hex)
        file_row.addWidget(self.search_input)
        
        self.search_btn = QPushButton("[Search]")
        self.search_btn.clicked.connect(self._search_hex)
        file_row.addWidget(self.search_btn)
        
        layout.addLayout(file_row)
        
        # HEX display - takes most space
        hex_group = QGroupBox("> HEX DUMP")
        hex_layout = QVBoxLayout()
        hex_layout.setContentsMargins(5, 10, 5, 5)
        
        self.hex_display = QTextEdit()
        self.hex_display.setReadOnly(True)
        self.hex_display.setFont(QFont("Consolas", 11))  # Slightly bigger font
        self.hex_display.setLineWrapMode(QTextEdit.NoWrap)
        self.hex_display.setMinimumHeight(400)  # Bigger hex display
        hex_layout.addWidget(self.hex_display, stretch=1)
        
        # Legend - compact
        legend_layout = QHBoxLayout()
        legend_items = [
            ("VIN", self.COLORS['green']),
            ("PIN/Security", self.COLORS['magenta']),
            ("Key Data", self.COLORS['cyan']),
            ("Checksum", self.COLORS['orange']),
        ]
        for name, color in legend_items:
            item = QLabel(f"* {name}")
            item.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10px;")
            legend_layout.addWidget(item)
        legend_layout.addStretch()
        hex_layout.addLayout(legend_layout)
        
        hex_group.setLayout(hex_layout)
        layout.addWidget(hex_group, stretch=1)
        
        panel.setLayout(layout)
        return panel
    
    def _create_info_panel(self) -> QWidget:
        """Create the info/offset panel."""
        panel = QFrame()
        layout = QVBoxLayout()
        
        # Module selector - compact
        module_group = QGroupBox("> MODULE TYPE")
        module_layout = QVBoxLayout()
        module_layout.setContentsMargins(5, 5, 5, 5)
        
        self.module_combo = QComboBox()
        self.module_combo.addItems(MODULE_OFFSETS.keys())
        self.module_combo.currentTextChanged.connect(self._on_module_changed)
        module_layout.addWidget(self.module_combo)
        
        # Stats - compact
        stats_layout = QGridLayout()
        stats_layout.addWidget(QLabel("File Size:"), 0, 0)
        self.size_label = QLabel("--")
        self.size_label.setStyleSheet(f"color: {self.COLORS['cyan']}; font-weight: bold;")
        stats_layout.addWidget(self.size_label, 0, 1)
        
        stats_layout.addWidget(QLabel("Total Bytes:"), 1, 0)
        self.bytes_label = QLabel("--")
        self.bytes_label.setStyleSheet(f"color: {self.COLORS['cyan']}; font-weight: bold;")
        stats_layout.addWidget(self.bytes_label, 1, 1)
        
        module_layout.addLayout(stats_layout)
        module_group.setLayout(module_layout)
        layout.addWidget(module_group)
        
        # Offset list - BIGGER, takes most space
        offset_group = QGroupBox("> COMMON OFFSETS")
        offset_layout = QVBoxLayout()
        
        self.offset_scroll = QScrollArea()
        self.offset_scroll.setWidgetResizable(True)
        self.offset_scroll.setMinimumHeight(250)  # Make it bigger!
        self.offset_container = QWidget()
        self.offset_list_layout = QVBoxLayout()
        self.offset_container.setLayout(self.offset_list_layout)
        self.offset_scroll.setWidget(self.offset_container)
        offset_layout.addWidget(self.offset_scroll)
        
        offset_group.setLayout(offset_layout)
        layout.addWidget(offset_group, stretch=2)  # Give it more space
        
        # Detected data - compact
        detected_group = QGroupBox("> DETECTED DATA")
        detected_layout = QVBoxLayout()
        detected_layout.setContentsMargins(5, 5, 5, 5)
        
        detected_layout.addWidget(QLabel("Possible VIN:"))
        self.vin_label = QLabel("--")
        self.vin_label.setStyleSheet(f"""
            color: {self.COLORS['green']};
            font-size: 14px;
            font-weight: bold;
            padding: 5px;
            background-color: {self.COLORS['bg_input']};
            border-radius: 4px;
        """)
        detected_layout.addWidget(self.vin_label)
        
        detected_layout.addWidget(QLabel("VIN Instances:"))
        self.vin_count_label = QLabel("0")
        self.vin_count_label.setStyleSheet(f"color: {self.COLORS['cyan']}; font-weight: bold;")
        detected_layout.addWidget(self.vin_count_label)
        
        detected_group.setLayout(detected_layout)
        layout.addWidget(detected_group)
        
        layout.addStretch()
        panel.setLayout(layout)
        return panel
    
    def _apply_theme(self):
        """Apply CyberNinja theme."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.COLORS['bg_dark']};
                color: {self.COLORS['text']};
                font-family: Consolas, monospace;
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
            QLineEdit {{
                background-color: {self.COLORS['bg_input']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                padding: 8px;
                color: {self.COLORS['text']};
            }}
            QLineEdit:focus {{
                border-color: {self.COLORS['cyan']};
            }}
            QComboBox {{
                background-color: {self.COLORS['bg_input']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
                padding: 8px;
                color: {self.COLORS['cyan']};
            }}
            QTextEdit {{
                background-color: {self.COLORS['bg_input']};
                border: 1px solid {self.COLORS['cyan']}40;
                border-radius: 4px;
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                background-color: {self.COLORS['bg_panel']};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {self.COLORS['cyan']}60;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {self.COLORS['cyan']};
            }}
        """)
        
        self.status_bar.setStyleSheet(f"""
            background-color: {self.COLORS['bg_panel']};
            color: {self.COLORS['cyan']};
            padding: 8px;
            border: 1px solid {self.COLORS['cyan']}40;
            border-radius: 4px;
            font-weight: bold;
        """)
    
    def _update_offset_list(self):
        """Update offset list for selected module."""
        # Clear existing
        while self.offset_list_layout.count():
            item = self.offset_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        module = MODULE_OFFSETS.get(self.current_module, MODULE_OFFSETS["Generic / Unknown"])
        
        type_colors = {
            "vin": self.COLORS['green'],
            "pin": self.COLORS['magenta'],
            "key": self.COLORS['cyan'],
            "checksum": self.COLORS['orange'],
        }
        
        for offset in module["offsets"]:
            item_frame = QFrame()
            item_frame.setStyleSheet(f"""
                background-color: {self.COLORS['bg_input']};
                border-left: 3px solid {type_colors.get(offset['type'], self.COLORS['cyan'])};
                border-radius: 4px;
                margin-bottom: 5px;
            """)
            
            item_layout = QVBoxLayout()
            item_layout.setContentsMargins(10, 8, 10, 8)
            
            name = QLabel(offset['name'])
            name.setStyleSheet(f"font-weight: bold; color: {self.COLORS['text']};")
            item_layout.addWidget(name)
            
            range_text = f"0x{offset['start']:04X} - 0x{offset['end']:04X}"
            range_label = QLabel(range_text)
            range_label.setStyleSheet(f"color: {type_colors.get(offset['type'], self.COLORS['cyan'])};")
            item_layout.addWidget(range_label)
            
            note = QLabel(offset['note'])
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {self.COLORS['text_dim']}; font-size: 10px;")
            item_layout.addWidget(note)
            
            item_frame.setLayout(item_layout)
            self.offset_list_layout.addWidget(item_frame)
        
        self.offset_list_layout.addStretch()
    
    def _on_module_changed(self, module_name: str):
        """Handle module selection change."""
        self.current_module = module_name
        self._update_offset_list()
        
        if self.current_data:
            self._display_hex()
        
        self._update_status(f"Module: {module_name}")
    
    def _load_file(self):
        """Load a binary dump file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select BCM Dump File",
            "",
            "Binary Files (*.bin *.hex *.eep *.dflash);;All Files (*)"
        )
        
        if path:
            try:
                with open(path, 'rb') as f:
                    self.current_data = f.read()
                self.current_file = os.path.basename(path)
                
                # Update UI
                self.file_label.setText(self.current_file)
                size_kb = len(self.current_data) / 1024
                self.size_label.setText(f"{size_kb:.2f} KB")
                self.bytes_label.setText(f"{len(self.current_data):,}")
                
                # Display hex
                self._display_hex()
                
                # Analyze for VIN
                self._analyze_data()
                
                self._update_status(f" LOADED  {self.current_file}")
                
            except Exception as e:
                self._update_status(f" ERROR  {str(e)}")
    
    def _display_hex(self):
        """Display hex dump with highlighting."""
        if not self.current_data:
            return
        
        module = MODULE_OFFSETS.get(self.current_module, MODULE_OFFSETS["Generic / Unknown"])
        
        # Build highlight map
        self.highlights = {}
        for offset in module["offsets"]:
            for i in range(offset["start"], min(offset["end"], len(self.current_data))):
                self.highlights[i] = offset["type"]
        
        # Build HTML hex display
        html_lines = []
        html_lines.append(f'<pre style="font-family: Consolas; font-size: 10pt; color: {self.COLORS["text"]};">')
        
        for row_start in range(0, len(self.current_data), 16):
            # Offset
            line = f'<span style="color: {self.COLORS["magenta"]};">{row_start:06X}</span>  '
            
            # Hex bytes
            for i in range(16):
                pos = row_start + i
                if pos < len(self.current_data):
                    byte = self.current_data[pos]
                    
                    if pos in self.highlights:
                        color = HIGHLIGHT_COLORS.get(self.highlights[pos], {}).get('fg', self.COLORS['text'])
                        bg = HIGHLIGHT_COLORS.get(self.highlights[pos], {}).get('bg', 'transparent')
                        line += f'<span style="color: {color}; background-color: {bg};">{byte:02X}</span> '
                    else:
                        line += f'{byte:02X} '
                else:
                    line += '   '
                
                if i == 7:
                    line += ' '
            
            # ASCII
            line += ' │ '
            for i in range(16):
                pos = row_start + i
                if pos < len(self.current_data):
                    byte = self.current_data[pos]
                    char = chr(byte) if 32 <= byte <= 126 else '.'
                    
                    if pos in self.highlights:
                        color = HIGHLIGHT_COLORS.get(self.highlights[pos], {}).get('fg', self.COLORS['text'])
                        line += f'<span style="color: {color};">{char}</span>'
                    else:
                        line += char
            
            html_lines.append(line)
        
        html_lines.append('</pre>')
        self.hex_display.setHtml('\n'.join(html_lines))
    
    def _analyze_data(self):
        """Analyze data for VIN patterns."""
        if not self.current_data:
            return
        
        # Convert to string for VIN search
        text = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in self.current_data)
        
        # VIN pattern: 17 alphanumeric (excluding I, O, Q)
        vin_pattern = r'[A-HJ-NPR-Z0-9]{17}'
        matches = re.findall(vin_pattern, text)
        
        if matches:
            self.vin_label.setText(matches[0])
            self.vin_count_label.setText(str(len(matches)))
        else:
            self.vin_label.setText("--")
            self.vin_count_label.setText("0")
    
    def _search_hex(self):
        """Search for hex or ASCII pattern."""
        query = self.search_input.text().strip()
        if not query or not self.current_data:
            return
        
        # Determine if hex or ASCII
        clean_query = query.replace(" ", "").upper()
        is_hex = all(c in "0123456789ABCDEF" for c in clean_query) and len(clean_query) % 2 == 0
        
        found_pos = -1
        
        if is_hex:
            # Search for hex pattern
            try:
                search_bytes = bytes.fromhex(clean_query)
                found_pos = self.current_data.find(search_bytes)
            except ValueError:
                pass
        else:
            # ASCII search
            text = ''.join(chr(b) if 32 <= b <= 126 else '\x00' for b in self.current_data)
            found_pos = text.lower().find(query.lower())
        
        if found_pos >= 0:
            # Scroll to position
            line_num = found_pos // 16
            cursor = self.hex_display.textCursor()
            cursor.movePosition(cursor.Start)
            for _ in range(line_num):
                cursor.movePosition(cursor.Down)
            self.hex_display.setTextCursor(cursor)
            self.hex_display.centerCursor()
            
            self._update_status(f" FOUND  Pattern at offset 0x{found_pos:06X}")
        else:
            self._update_status(" NOT FOUND  Pattern not in dump")
    
    def _clear_search(self):
        """Clear search and reset display."""
        self.search_input.clear()
        if self.current_data:
            self._display_hex()
    
    def _update_status(self, message: str):
        """Update status bar."""
        self.status_bar.setText(message)


# ----------------------------------------------------------------------------------
# Test
# ----------------------------------------------------------------------------------
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    tab = HexAnalyzerTab()
    tab.resize(1100, 700)
    tab.show()
    sys.exit(app.exec_())
