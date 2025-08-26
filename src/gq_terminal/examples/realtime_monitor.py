#!/usr/bin/env python3
"""
Real-time monitoring example for GQ Terminal GMC-600 interface.
"""

import time
import sys
import signal
from datetime import datetime
from gq_terminal import GMCInterface


class RadiationMonitor:
    """Real-time radiation monitoring class."""
    
    def __init__(self, port: str, baudrate: int = 115200):
        self.gmc = GMCInterface(port, baudrate)
        self.running = False
        self.stats = {
            'max_cps': 0,
            'min_cps': float('inf'),
            'total_counts': 0,
            'samples': 0,
            'start_time': None
        }
    
    def connect(self) -> bool:
        """Connect to the device."""
        return self.gmc.connect()
    
    def disconnect(self):
        """Disconnect from the device."""
        if self.running:
            self.stop_monitoring()
        self.gmc.disconnect()
    
    def start_monitoring(self):
        """Start real-time monitoring with heartbeat mode."""
        print("Starting real-time monitoring...")
        print("Press Ctrl+C to stop\n")
        
        # Start heartbeat mode
        if not self.gmc.start_heartbeat():
            print("Failed to start heartbeat mode!")
            return False
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        
        # Print header
        print("Time".ljust(12), "CPS".rjust(6), "CPM".rjust(6), 
              "Battery".rjust(8), "Temp".rjust(8), "Status")
        print("-" * 60)
        
        last_update = time.time()
        cpm = 0
        voltage = 0.0
        temp = None
        
        try:
            while self.running:
                # Read heartbeat data
                cps = self.gmc.read_heartbeat()
                
                if cps is not None:
                    # Update statistics
                    self.stats['samples'] += 1
                    self.stats['total_counts'] += cps
                    self.stats['max_cps'] = max(self.stats['max_cps'], cps)
                    self.stats['min_cps'] = min(self.stats['min_cps'], cps)
                    
                    # Update other readings periodically (every 5 seconds)
                    current_time = time.time()
                    if current_time - last_update >= 5.0:
                        try:
                            cpm = self.gmc.get_cpm()
                            voltage = self.gmc.get_battery_voltage()
                            temp = self.gmc.get_temperature()
                        except:
                            pass
                        last_update = current_time
                    
                    # Format display
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
                    
                    # Status indicators
                    status = ""
                    if cps > 100:
                        status += "⚠️ HIGH "
                    if voltage < 3.0:
                        status += "🔋LOW "
                    
                    # Print current reading
                    print(f"{timestamp:<12} {cps:>6} {cpm:>6} "
                          f"{voltage:>6.1f}V {temp_str:>8} {status}")
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nStopping monitoring...")
        
        return True
    
    def stop_monitoring(self):
        """Stop monitoring and print statistics."""
        self.running = False
        self.gmc.stop_heartbeat()
        
        if self.stats['samples'] > 0:
            duration = datetime.now() - self.stats['start_time']
            avg_cps = self.stats['total_counts'] / self.stats['samples']
            
            print("\n" + "=" * 50)
            print("MONITORING STATISTICS")
            print("=" * 50)
            print(f"Duration: {duration}")
            print(f"Total samples: {self.stats['samples']}")
            print(f"Average CPS: {avg_cps:.2f}")
            print(f"Maximum CPS: {self.stats['max_cps']}")
            print(f"Minimum CPS: {self.stats['min_cps']}")
            print(f"Total counts: {self.stats['total_counts']}")
            print(f"Est. average CPM: {avg_cps * 60:.1f}")


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\nShutdown signal received...")
    sys.exit(0)


def main():
    """Real-time monitoring demonstration."""
    # Configure your serial port here
    # PORT = '/dev/ttyUSB0'  # Linux/Mac
    # PORT = 'COM3'        # Windows
    import os
    if os.name == 'nt':
        PORT = 'COM3'  # Adjust as needed
    else:
        PORT = '/dev/ttyUSB0'  # Adjust as needed

    BAUDRATE = 115200
    
    print("GQ Terminal - Real-time Monitoring Example")
    print(f"Connecting to GMC on {PORT}...")
    
    # Setup signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create monitor instance
    monitor = RadiationMonitor(PORT, BAUDRATE)
    
    try:
        # Connect to device
        if not monitor.connect():
            print("Failed to connect to device!")
            return 1
        
        print("✓ Connected successfully!")
        
        # Get basic device info
        version = monitor.gmc.get_version()
        voltage = monitor.gmc.get_battery_voltage()
        print(f"Device: {version}")
        print(f"Battery: {voltage:.1f}V")
        
        if voltage < 3.0:
            print("⚠️  Warning: Low battery may affect readings")
        
        # Start monitoring
        monitor.start_monitoring()
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    finally:
        monitor.disconnect()
        print("Disconnected from device")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())