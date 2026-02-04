# utils/hex_validator.py

"""
Description:
Provides input validation for hexadecimal values in GUI fields.
"""

# ----------------------------------------------------------------------------------
# 1) Imports
# ----------------------------------------------------------------------------------
from PyQt5.QtGui import QValidator
import re

# ----------------------------------------------------------------------------------
# 2) Validator Classes
# ----------------------------------------------------------------------------------
class HexValidator(QValidator):
    """Validates 3-digit hexadecimal CAN IDs (000-7FF)"""
    def __init__(self, parent=None, max_length: int = 3, max_value: int = 0x7FF):
        super().__init__(parent)
        self.max_length = max_length
        self.max_value = max_value
        self.regex = re.compile(r'^[0-9A-Fa-f]{0,3}$')

    def validate(self, text, pos):
        text = text.upper()
        if not self.regex.match(text):
            return (QValidator.Invalid, text, pos)
        if len(text) > self.max_length:
            return (QValidator.Invalid, text, pos)
        if text:
            try:
                value = int(text, 16)
                if value > self.max_value:
                    return (QValidator.Invalid, text, pos)
            except ValueError:
                return (QValidator.Invalid, text, pos)
        return (QValidator.Acceptable, text, pos)

class HexBytesValidator(QValidator):
    """Validates space-separated hex bytes (e.g., 'DE AD BE EF')"""
    def __init__(self, parent=None, min_bytes: int = 1, max_bytes: int = 8):
        super().__init__(parent)
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes
        self.regex = re.compile(r'^([0-9A-Fa-f]{2}(\s|$))*$')

    def validate(self, text, pos):
        text = text.upper().strip()
        if not self.regex.match(text):
            return (QValidator.Invalid, text, pos)
        byte_count = len(text.split())
        if byte_count < self.min_bytes or byte_count > self.max_bytes:
            return (QValidator.Intermediate, text, pos)
        return (QValidator.Acceptable, text, pos)