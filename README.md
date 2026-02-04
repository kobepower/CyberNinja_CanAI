# ◢ CANAI PRO ◣
## CyberNinja Edition v1.0

Professional CAN bus diagnostic and key programming tool for automotive locksmiths.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║     ██████╗██╗   ██╗██████╗ ███████╗██████╗ ███╗   ██╗██╗███╗   ██╗     ██╗   ║
║    ██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗████╗  ██║██║████╗  ██║     ██║   ║
║    ██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝██╔██╗ ██║██║██╔██╗ ██║     ██║   ║
║    ██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗██║╚██╗██║██║██║╚██╗██║██   ██║   ║
║    ╚██████╗   ██║   ██████╔╝███████╗██║  ██║██║ ╚████║██║██║ ╚████║╚█████╔╝   ║
║     ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝ ╚════╝    ║
║                                                                               ║
║                         🐍 MAMBA MENTALITY 🐍                                  ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

## Features

### 📡 CAN Monitor
- Real-time CAN frame display
- Filtering by ID, direction, data
- UDS protocol decoding
- Frame replay capability
- CSV export

### 🔑 Key Tools
- Security Access workflows (Seed/Key)
- Key count reading
- Key slot status
- Vehicle profile presets (FCA, GM, Toyota, Ford)
- Custom UDS frame sending

### 🔍 Diagnostics
- DTC (Diagnostic Trouble Code) reading
- DTC clearing
- Module scanner
- Vehicle info reader
- Live data monitoring

### 💾 ECU Flash
- EEPROM read operations
- EEPROM write operations (with safety warnings)
- Dump file comparison
- Checksum calculation (CRC-16, CRC-32, MD5, SHA)
- FCA CKS verification

### 📊 HEX Analyzer
- Educational BCM dump viewer
- VIN/PIN/Key location highlighting
- Module profiles (MPC5606B, MPC5646C, RH850)
- Pattern search
- **READ-ONLY - No modification capability**

### ⚙️ Settings
- Interface configuration
- Display preferences
- Path configuration
- Settings export/import

## Installation

```bash
# Clone or extract the project
cd canai_pro

# Install requirements
pip install -r requirements.txt

# Run
python main.py
```

## Requirements

- Python 3.8+
- PyQt5
- pyserial

## Project Structure

```
canai_pro/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── backend/
│   ├── __init__.py
│   └── can_interface.py    # CAN communication layer
├── gui/
│   ├── __init__.py
│   └── tabs/
│       ├── __init__.py
│       ├── can_monitor_tab.py
│       ├── key_tools_tab.py
│       ├── diagnostics_tab.py
│       ├── ecu_flash_tab.py
│       ├── hex_analyzer_tab.py
│       └── settings_tab.py
├── utils/
│   ├── __init__.py
│   ├── uds_decoder.py
│   └── hex_validator.py
└── data/
    └── dids.json           # DID database
```

## Legal Disclaimer

This software is provided for **EDUCATIONAL PURPOSES ONLY**. 

The HEX Analyzer and ECU Flash tools are designed for legitimate locksmith work including:
- All Keys Lost (AKL) situations
- Module replacement/repair
- Authorized key programming

**Users are solely responsible for ensuring compliance with all applicable laws.**

Unauthorized modification of vehicle modules may violate:
- Computer Fraud and Abuse Act
- Vehicle theft statutes
- VIN tampering laws (49 U.S.C. § 32703)

**The creator assumes NO LIABILITY for misuse.**

## Credits

Built with ❤️ by **Kobe's Keys**

🐍 **MAMBA MENTALITY** 🐍
