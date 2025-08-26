#!/usr/bin/env python3
"""
Data logging example for GQ Terminal GMC-600 interface.
Demonstrates how to log radiation data to CSV files.
"""

import time
import csv
import sys
from datetime import datetime
from pathlib import Path
from gq_terminal import GMCInterface


class RadiationLogger:
    """Data logging class for radiation measurements."""
    
    def __init__(self, port: str, baudrate: int = 115200, log_file: str = None):
        self.gmc = GMCInterface(port, baudrate)
        self.log_file = log_file or f"radiation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.running = False
    
    def connect(self) -> bool:
        """Connect to the device."""
        return self.gmc.connect()
    
    def disconnect(self):
        """Disconnect from the device."""
        if self.running:
            self.stop_logging()
        self.gmc.disconnect()
    
    def start_logging(self, interval: float = 60.0):
        """
        Start data logging.
        
        Args:
            interval: Logging interval in seconds (default: 60s)
        """
        print(f"Starting data logging to: {self.log_file}")
        print(f"Logging interval: {interval} seconds")
        print("Press Ctrl+C to stop\n")
        
        # Create log file with headers
        log_path = Path(self.log_file)
        with open(log_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'timestamp', 'cpm', 'cps', 'battery_voltage', 
                'temperature', 'device_time', 'notes'
            ])
        
        self.running = True
        sample_count = 0
        
        # Get device info for logging
        try:
            version = self.gmc.get_version()
            serial = self.gmc.get_serial_number()
            print(f"Logging data from: {version} (Serial: {serial})")
        except:
            print("Could not get device info")
        
        print("Time".ljust(20), "CPM".rjust(6), "CPS".rjust(6), 
              "Battery".rjust(8), "Temp".rjust(8), "Status")
        print("-" * 60)
        
        try:
            # Enable heartbeat for CPS readings
            self.gmc.start_heartbeat()
            
            while self.running:
                start_time = time.time()
                
                # Collect data
                try:
                    cpm = self.gmc.get_cpm()
                    voltage = self.gmc.get_battery_voltage()
                    temperature = self.gmc.get_temperature()
                    device_time = self.gmc.get_datetime()
                    
                    # Collect CPS samples over the interval
                    cps_samples = []
                    interval_start = time.time()
                    
                    while time.time() - interval_start < interval and self.running:
                        cps = self.gmc.read_heartbeat()
                        if cps is not None:
                            cps_samples.append(cps)
                        time.sleep(0.1)
                    
                    # Calculate average CPS
                    avg_cps = sum(cps_samples) / len(cps_samples) if cps_samples else 0
                    
                    # Timestamp
                    timestamp = datetime.now().isoformat()
                    
                    # Format device time
                    device_time_str = device_time.isoformat() if device_time else ""
                    temp_str = f"{temperature:.1f}" if temperature is not None else ""
                    
                    # Log to CSV
                    with open(log_path, 'a', newline='') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow([
                            timestamp, cpm, f"{avg_cps:.2f}", f"{voltage:.2f}",
                            temp_str, device_time_str, ""
                        ])
                    
                    # Display current reading
                    sample_count += 1
                    status = ""
                    if avg_cps > 100:
                        status += "⚠️HIGH "
                    if voltage < 3.0:
                        status += "🔋LOW "
                    
                    display_time = datetime.now().strftime("%H:%M:%S")
                    temp_display = f"{temperature:.1f}°C" if temperature is not None else "N/A"
                    
                    print(f"{display_time:<20} {cpm:>6} {avg_cps:>6.1f} "
                          f"{voltage:>6.1f}V {temp_display:>8} {status}")
                    
                    # Log special conditions
                    notes = []
                    if avg_cps > 200:
                        notes.append("HIGH_RADIATION")
                    if voltage < 3.0:
                        notes.append("LOW_BATTERY")
                    
                    if notes:
                        # Add note to log file
                        with open(log_path, 'a', newline='') as csvfile:
                            writer = csv.writer(csvfile)
                            last_row = [timestamp, cpm, f"{avg_cps:.2f}", f"{voltage:.2f}",
                                       temp_str, device_time_str, "; ".join(notes)]
                            # Update the last row with notes (simplified approach)
                    
                except Exception as e:
                    print(f"Error collecting data: {e}")
                    time.sleep(1)
                    continue
                
                # Wait for next sample (accounting for processing time)
                elapsed = time.time() - start_time
                if elapsed < interval:
                    time.sleep(interval - elapsed)
                    
        except KeyboardInterrupt:
            print("\nStopping data logging...")
        
        finally:
            self.gmc.stop_heartbeat()
            print(f"\nLogged {sample_count} samples to {self.log_file}")
    
    def stop_logging(self):
        """Stop data logging."""
        self.running = False


def main():
    """Data logging demonstration."""
    import argparse
    
    parser = argparse.ArgumentParser(description='GMC-600 Data Logger')
    parser.add_argument('--port', required=True, help='Serial port (e.g., COM3, /dev/ttyUSB0)')
    parser.add_argument('--baudrate', type=int, default=115200, help='Baud rate (default: 115200)')
    parser.add_argument('--interval', type=float, default=60.0, help='Logging interval in seconds (default: 60)')
    parser.add_argument('--output', help='Output CSV file name (default: auto-generated)')
    args = parser.parse_args()
    
    print("GQ Terminal - Data Logging Example")
    print(f"Connecting to GMC-600 on {args.port}...")
    
    # Create logger instance
    logger = RadiationLogger(args.port, args.baudrate, args.output)
    
    try:
        # Connect to device
        if not logger.connect():
            print("Failed to connect to device!")
            return 1
        
        print("✓ Connected successfully!")
        
        # Start logging
        logger.start_logging(args.interval)
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    finally:
        logger.disconnect()
        print("Disconnected from device")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())