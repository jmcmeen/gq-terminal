"""
GMC-600 Geiger Counter Interface
Communication interface for GQ GMC-600 geiger counter using the GQ-RFC1201 protocol.
"""

import serial
import struct
import time
from typing import Optional, Tuple
from datetime import datetime


class GMCInterface:
    """Interface class for GMC geiger counter communication."""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        """
        Initialize GMC interface.
        
        Args:
            port: Serial port (e.g., 'COM3' on Windows, '/dev/ttyUSB0' on Linux)
            baudrate: Communication speed (115200 for GMC-600 with latest firmware)
            timeout: Serial read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None
        self.heartbeat_active = False
    
    def connect(self) -> bool:
        """
        Establish serial connection to GMC-600.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity=serial.PARITY_NONE,
                stopbits=1,
                timeout=self.timeout
            )
            return self.serial_conn.is_open
        except serial.SerialException as e:
            print(f"Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.heartbeat_active = False
            self.serial_conn.close()
    
    def _send_command(self, command: str) -> bytes:
        """
        Send command to GMC-600 and return response.
        
        Args:
            command: Command string without < and >> delimiters
            
        Returns:
            Raw response bytes
        """
        if not self.serial_conn or not self.serial_conn.is_open:
            raise RuntimeError("Not connected to device")
        
        full_command = f"<{command}>>"
        self.serial_conn.write(full_command.encode('ascii'))
        self.serial_conn.flush()
        
        # Small delay to ensure command is processed
        time.sleep(0.1)
        
        response = self.serial_conn.read_all()
        return response
    
    def get_version(self) -> str:
        """
        Get hardware model and firmware version.
        
        Returns:
            14-character string with model and version info
        """
        response = self._send_command("GETVER")
        return response.decode('ascii', errors='ignore').strip()
    
    def get_cpm(self) -> int:
        """
        Get current counts per minute (CPM).
        
        Returns:
            CPM value as integer
        """
        response = self._send_command("GETCPM")
        if len(response) >= 2:
            return struct.unpack('>H', response[:2])[0]
        return 0
    
    def get_battery_voltage(self) -> float:
        """
        Get battery voltage.
        
        Returns:
            Battery voltage in volts
        """
        response = self._send_command("GETVOLT")
        if len(response) >= 1:
            return response[0] / 10.0
        return 0.0
    
    def get_serial_number(self) -> str:
        """
        Get device serial number.
        
        Returns:
            7-byte serial number as string
        """
        response = self._send_command("GETSERIAL")
        return response.decode('ascii', errors='ignore').strip()
    
    def get_temperature(self) -> Optional[float]:
        """
        Get temperature reading.
        
        Returns:
            Temperature in Celsius, None if not supported
        """
        try:
            response = self._send_command("GETTEMP")
            if len(response) >= 4:
                integer_part = response[0]
                decimal_part = response[1]
                negative_sign = response[2]
                temp = integer_part + (decimal_part / 100.0)
                return -temp if negative_sign != 0 else temp
        except:
            return None
        return None
    
    def get_gyroscope(self) -> Optional[Tuple[int, int, int]]:
        """
        Get gyroscope data.
        
        Returns:
            Tuple of (x, y, z) values, None if not supported
        """
        try:
            response = self._send_command("GETGYRO")
            if len(response) >= 7:
                x = struct.unpack('>H', response[0:2])[0]
                y = struct.unpack('>H', response[2:4])[0]
                z = struct.unpack('>H', response[4:6])[0]
                return (x, y, z)
        except:
            return None
        return None
    
    def get_datetime(self) -> Optional[datetime]:
        """
        Get device date and time.
        
        Returns:
            datetime object, None if not supported
        """
        try:
            response = self._send_command("GETDATETIME")
            if len(response) >= 7:
                year = 2000 + response[0]
                month = response[1]
                day = response[2]
                hour = response[3]
                minute = response[4]
                second = response[5]
                return datetime(year, month, day, hour, minute, second)
        except:
            return None
        return None
    
    def set_datetime(self, dt: datetime) -> bool:
        """
        Set device date and time.
        
        Args:
            dt: datetime object to set
            
        Returns:
            True if successful
        """
        try:
            year = dt.year - 2000
            command = f"SETDATETIME{year:02x}{dt.month:02x}{dt.day:02x}{dt.hour:02x}{dt.minute:02x}{dt.second:02x}"
            response = self._send_command(command)
            return len(response) > 0 and response[-1] == 0xAA
        except:
            return False
    
    def start_heartbeat(self) -> bool:
        """
        Start heartbeat mode (automatic CPS reporting every second).
        
        Returns:
            True if successful
        """
        try:
            self._send_command("HEARTBEAT1")
            self.heartbeat_active = True
            return True
        except:
            return False
    
    def stop_heartbeat(self) -> bool:
        """
        Stop heartbeat mode.
        
        Returns:
            True if successful
        """
        try:
            self._send_command("HEARTBEAT0")
            self.heartbeat_active = False
            return True
        except:
            return False
    
    def read_heartbeat(self) -> Optional[int]:
        """
        Read heartbeat data (counts per second).
        
        Returns:
            CPS value, None if no data available
        """
        if not self.heartbeat_active or not self.serial_conn:
            return None
        
        try:
            if self.serial_conn.in_waiting >= 2:
                data = self.serial_conn.read(2)
                if len(data) == 2:
                    # Only use lowest 14 bits for valid data
                    cps = struct.unpack('>H', data)[0] & 0x3FFF
                    return cps
        except:
            pass
        return None
    
    def get_history_data(self, address: int, length: int) -> bytes:
        """
        Request history data from flash memory.
        
        Args:
            address: Starting address (0-based)
            length: Number of bytes to read (max 4096)
            
        Returns:
            Raw history data bytes
        """
        if length > 4096:
            raise ValueError("Length cannot exceed 4096 bytes")
        
        # Convert address and length to hex bytes
        a2 = (address >> 16) & 0xFF
        a1 = (address >> 8) & 0xFF
        a0 = address & 0xFF
        l1 = (length >> 8) & 0xFF
        l0 = length & 0xFF
        
        command = f"SPIR{a2:02x}{a1:02x}{a0:02x}{l1:02x}{l0:02x}"
        return self._send_command(command)
    
    def get_config(self) -> bytes:
        """
        Get configuration data.
        
        Returns:
            256 bytes of configuration data
        """
        return self._send_command("GETCFG")
    
    def erase_config(self) -> bool:
        """
        Erase all configuration data.
        
        Returns:
            True if successful
        """
        response = self._send_command("ECFG")
        return len(response) > 0 and response[-1] == 0xAA
    
    def write_config(self, address: int, data: int) -> bool:
        """
        Write single byte to configuration.
        
        Args:
            address: Config address (0-255)
            data: Data byte to write (0-255)
            
        Returns:
            True if successful
        """
        command = f"WCFG{address:02x}{data:02x}"
        response = self._send_command(command)
        return len(response) > 0 and response[-1] == 0xAA
    
    def update_config(self) -> bool:
        """
        Reload/update configuration.
        
        Returns:
            True if successful
        """
        response = self._send_command("CFGUPDATE")
        return len(response) > 0 and response[-1] == 0xAA
    
    def send_key(self, key_num: int) -> bool:
        """
        Send software key press.
        
        Args:
            key_num: Key number (0-3 for S1-S4)
            
        Returns:
            True if successful
        """
        if key_num < 0 or key_num > 3:
            raise ValueError("Key number must be 0-3")
        
        try:
            self._send_command(f"KEY{key_num}")
            return True
        except:
            return False
    
    def power_off(self) -> bool:
        """
        Power off the device.
        
        Returns:
            True if command sent successfully
        """
        try:
            self._send_command("POWEROFF")
            return True
        except:
            return False
    
    def power_on(self) -> bool:
        """
        Power on the device.
        
        Returns:
            True if command sent successfully
        """
        try:
            self._send_command("POWERON")
            return True
        except:
            return False
    
    def reboot(self) -> bool:
        """
        Reboot the device.
        
        Returns:
            True if command sent successfully
        """
        try:
            self._send_command("REBOOT")
            return True
        except:
            return False
    
    def factory_reset(self) -> bool:
        """
        Reset device to factory defaults.
        
        Returns:
            True if successful
        """
        response = self._send_command("FACTORYRESET")
        return len(response) > 0 and response[-1] == 0xAA