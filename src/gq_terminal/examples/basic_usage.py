#!/usr/bin/env python3
"""
Basic usage example for GQ Terminal GMC-600 interface.
"""

import time
import sys
from gq_terminal import GMCInterface


def main():
    """Basic usage demonstration."""
    # Configure your serial port here
    # PORT = '/dev/ttyUSB0'  # Linux/Mac
    PORT = 'COM3'        # Windows
    BAUDRATE = 115200
    
    print("GQ Terminal - Basic Usage Example")
    print(f"Connecting to GMC-600 on {PORT}...")
    
    # Create interface instance
    gmc = GMCInterface(PORT, BAUDRATE)
    
    # Connect to device
    if not gmc.connect():
        print("Failed to connect to device!")
        print("Check:")
        print("- Serial port is correct")
        print("- Device is powered on")
        print("- USB cable is connected")
        return 1
    
    print("✓ Connected successfully!")
    
    try:
        # Get basic device information
        print("\n=== Device Information ===")
        version = gmc.get_version()
        serial = gmc.get_serial_number()
        voltage = gmc.get_battery_voltage()
        
        print(f"Model/Version: {version}")
        print(f"Serial Number: {serial}")
        print(f"Battery Voltage: {voltage:.2f}V")
        
        # Check battery status
        if voltage < 3.0:
            print("⚠️  Low battery warning!")
        elif voltage > 4.0:
            print("🔋 Battery level good")
        
        # Get current radiation readings
        print("\n=== Current Readings ===")
        cpm = gmc.get_cpm()
        print(f"Current CPM: {cpm}")
        
        # Try to get temperature (if supported)
        temp = gmc.get_temperature()
        if temp is not None:
            print(f"Temperature: {temp:.1f}°C")
        else:
            print("Temperature: Not supported on this model")
        
        # Try to get gyroscope data (if supported)
        gyro = gmc.get_gyroscope()
        if gyro is not None:
            print(f"Gyroscope - X: {gyro[0]}, Y: {gyro[1]}, Z: {gyro[2]}")
        else:
            print("Gyroscope: Not supported on this model")
        
        # Get device date/time
        dt = gmc.get_datetime()
        if dt is not None:
            print(f"Device Time: {dt}")
        else:
            print("Device Time: Not supported on this model")
        
        # Demonstrate configuration reading
        print("\n=== Configuration ===")
        config = gmc.get_config()
        if len(config) >= 256:
            print(f"Configuration size: {len(config)} bytes")
            print(f"First 16 config bytes: {config[:16].hex()}")
        
        print("\n=== Test Complete ===")
        print("Device communication successful!")
        
    except Exception as e:
        print(f"Error during communication: {e}")
        return 1
    
    finally:
        # Always disconnect
        gmc.disconnect()
        print("Disconnected from device")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())