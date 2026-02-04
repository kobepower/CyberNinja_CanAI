#!/usr/bin/env python3
# test_run.py - Simple test to verify everything works

print("Step 1: Starting...")

import sys
print("Step 2: sys imported")

try:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
    print("Step 3: PyQt5 imported OK")
except ImportError as e:
    print(f"Step 3: PyQt5 import FAILED: {e}")
    sys.exit(1)

try:
    from backend.can_interface import CANInterface
    print("Step 4: CANInterface imported OK")
except Exception as e:
    print(f"Step 4: CANInterface import FAILED: {e}")

try:
    from utils.uds_decoder import decode_uds
    print("Step 5: uds_decoder imported OK")
except Exception as e:
    print(f"Step 5: uds_decoder import FAILED: {e}")

try:
    from gui.tabs.can_monitor_tab import CANMonitorTab
    print("Step 6: CANMonitorTab imported OK")
except Exception as e:
    print(f"Step 6: CANMonitorTab import FAILED: {e}")
    import traceback
    traceback.print_exc()

print("Step 7: Creating QApplication...")
app = QApplication(sys.argv)

print("Step 8: Creating window...")
window = QMainWindow()
window.setWindowTitle("Test Window")
window.setGeometry(100, 100, 400, 300)
label = QLabel("If you see this, PyQt5 works!", window)
label.setGeometry(50, 100, 300, 50)

print("Step 9: Showing window...")
window.show()

print("Step 10: Entering event loop...")
sys.exit(app.exec_())
