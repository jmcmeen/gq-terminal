#!/usr/bin/env python3
"""
Click-based command-line interface for GMC geiger counter.
"""

import time
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from .interface import GMCInterface


# Common options decorator
def common_options(func):
    """Common options for all commands."""
    func = click.option(
        '--port', '-p',
        required=True,
        help='Serial port (e.g., COM3, /dev/ttyUSB0)'
    )(func)
    func = click.option(
        '--baudrate', '-b',
        default=115200,
        help='Baud rate (default: 115200)'
    )(func)
    func = click.option(
        '--timeout', '-t',
        default=2.0,
        help='Serial timeout in seconds (default: 2.0)'
    )(func)
    return func


@click.group()
@click.version_option(version='0.1.0', prog_name='gq-terminal')
def main():
    """GQ Terminal - Interface for GMC geiger counters."""
    pass


@main.command()
@common_options
@click.option('--verbose', '-v', is_flag=True, help='Show detailed device information')
def info(port: str, baudrate: int, timeout: float, verbose: bool):
    """Get device information and current readings."""
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        click.echo(click.style("✓ Connected successfully", fg='green'))
        
        # Basic device information
        version = gmc.get_version()
        serial_num = gmc.get_serial_number()
        voltage = gmc.get_battery_voltage()
        cpm = gmc.get_cpm()
        
        click.echo("\n=== Device Information ===")
        click.echo(f"Model/Version: {version}")
        click.echo(f"Serial Number: {serial_num}")
        click.echo(f"Battery: {voltage:.2f}V", color=(voltage < 3.0))
        click.echo(f"Current CPM: {cpm}")
        
        if voltage < 3.0:
            click.echo(click.style("⚠️  Low battery warning!", fg='yellow'))
        
        if verbose:
            # Extended information
            temp = gmc.get_temperature()
            if temp is not None:
                click.echo(f"Temperature: {temp:.1f}°C")
            
            gyro = gmc.get_gyroscope()
            if gyro is not None:
                click.echo(f"Gyroscope: X={gyro[0]}, Y={gyro[1]}, Z={gyro[2]}")
            
            dt = gmc.get_datetime()
            if dt is not None:
                click.echo(f"Device Time: {dt}")
            
            # Configuration info
            config = gmc.get_config()
            if len(config) >= 256:
                click.echo(f"Config Size: {len(config)} bytes")
                if verbose:
                    click.echo(f"Config Preview: {config[:16].hex()}")
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()
        click.echo("Disconnected")


@main.command()
@common_options
@click.option('--duration', '-d', default=0, help='Monitoring duration in seconds (0 = infinite)')
@click.option('--interval', '-i', default=1.0, help='Display update interval in seconds')
@click.option('--quiet', '-q', is_flag=True, help='Minimal output (CPS only)')
def monitor(port: str, baudrate: int, timeout: float, duration: int, interval: float, quiet: bool):
    """Real-time radiation monitoring with heartbeat mode."""
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        if not quiet:
            version = gmc.get_version()
            voltage = gmc.get_battery_voltage()
            click.echo(f"Connected to {version}")
            click.echo(f"Battery: {voltage:.1f}V")
            
            if voltage < 3.0:
                click.echo(click.style("⚠️  Warning: Low battery may affect readings", fg='yellow'))
        
        # Start heartbeat mode
        if not gmc.start_heartbeat():
            click.echo(click.style("Failed to start heartbeat mode!", fg='red'), err=True)
            sys.exit(1)
        
        if not quiet:
            click.echo(f"\nStarting real-time monitoring...")
            click.echo("Press Ctrl+C to stop\n")
            
            # Header
            click.echo("Time".ljust(12) + "CPS".rjust(6) + "CPM".rjust(6) + "Battery".rjust(8) + "Status")
            click.echo("-" * 50)
        
        start_time = time.time()
        last_update = time.time()
        cpm = 0
        voltage = 0.0
        stats = {'max_cps': 0, 'min_cps': float('inf'), 'total': 0, 'samples': 0}
        
        try:
            while True:
                # Check duration limit
                if duration > 0 and time.time() - start_time >= duration:
                    break
                
                cps = gmc.read_heartbeat()
                
                if cps is not None:
                    # Update statistics
                    stats['samples'] += 1
                    stats['total'] += cps
                    stats['max_cps'] = max(stats['max_cps'], cps)
                    stats['min_cps'] = min(stats['min_cps'], cps)
                    
                    # Update other readings periodically
                    current_time = time.time()
                    if current_time - last_update >= 5.0:
                        try:
                            cpm = gmc.get_cpm()
                            voltage = gmc.get_battery_voltage()
                        except:
                            pass
                        last_update = current_time
                    
                    if quiet:
                        click.echo(f"{cps}")
                    else:
                        # Format display
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        status = ""
                        
                        if cps > 100:
                            status += "⚠️HIGH "
                        if voltage < 3.0:
                            status += "🔋LOW "
                        
                        click.echo(f"{timestamp:<12} {cps:>6} {cpm:>6} "
                                 f"{voltage:>6.1f}V {status}")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            click.echo("\nStopping monitoring...")
        
        gmc.stop_heartbeat()
        
        # Show statistics
        if not quiet and stats['samples'] > 0:
            duration_actual = time.time() - start_time
            avg_cps = stats['total'] / stats['samples']
            
            click.echo("\n" + "=" * 40)
            click.echo("MONITORING STATISTICS")
            click.echo("=" * 40)
            click.echo(f"Duration: {duration_actual:.1f}s")
            click.echo(f"Samples: {stats['samples']}")
            click.echo(f"Average CPS: {avg_cps:.2f}")
            click.echo(f"Max CPS: {stats['max_cps']}")
            click.echo(f"Min CPS: {stats['min_cps']}")
            click.echo(f"Total counts: {stats['total']}")
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()
        if not quiet:
            click.echo("Disconnected")


@main.command()
@common_options
@click.option('--output', '-o', help='Output CSV file (default: auto-generated)')
@click.option('--interval', '-i', default=60.0, help='Logging interval in seconds (default: 60)')
@click.option('--duration', '-d', default=0, help='Logging duration in seconds (0 = infinite)')
def log(port: str, baudrate: int, timeout: float, output: Optional[str], interval: float, duration: int):
    """Log radiation data to CSV file."""
    if not output:
        output = f"radiation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        version = gmc.get_version()
        serial_num = gmc.get_serial_number()
        click.echo(f"Connected to {version} (Serial: {serial_num})")
        click.echo(f"Logging to: {output}")
        click.echo(f"Interval: {interval}s")
        
        if duration > 0:
            click.echo(f"Duration: {duration}s")
        
        click.echo("Press Ctrl+C to stop\n")
        
        # Create CSV file with headers
        log_path = Path(output)
        with open(log_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'timestamp', 'cpm', 'avg_cps', 'battery_voltage', 
                'temperature', 'device_time', 'notes'
            ])
        
        # Start heartbeat for CPS readings
        gmc.start_heartbeat()
        
        start_time = time.time()
        sample_count = 0
        
        # Header
        click.echo("Time".ljust(20) + "CPM".rjust(6) + "CPS".rjust(6) + "Battery".rjust(8) + "Status")
        click.echo("-" * 50)
        
        try:
            while True:
                # Check duration limit
                if duration > 0 and time.time() - start_time >= duration:
                    break
                
                interval_start = time.time()
                
                # Collect data
                try:
                    cpm = gmc.get_cpm()
                    voltage = gmc.get_battery_voltage()
                    temperature = gmc.get_temperature()
                    device_time = gmc.get_datetime()
                    
                    # Collect CPS samples over the interval
                    cps_samples = []
                    while time.time() - interval_start < interval:
                        cps = gmc.read_heartbeat()
                        if cps is not None:
                            cps_samples.append(cps)
                        time.sleep(0.1)
                    
                    avg_cps = sum(cps_samples) / len(cps_samples) if cps_samples else 0
                    
                    # Log data
                    timestamp = datetime.now().isoformat()
                    device_time_str = device_time.isoformat() if device_time else ""
                    temp_str = f"{temperature:.1f}" if temperature is not None else ""
                    
                    # Determine notes
                    notes = []
                    if avg_cps > 200:
                        notes.append("HIGH_RADIATION")
                    if voltage < 3.0:
                        notes.append("LOW_BATTERY")
                    
                    with open(log_path, 'a', newline='') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow([
                            timestamp, cpm, f"{avg_cps:.2f}", f"{voltage:.2f}",
                            temp_str, device_time_str, "; ".join(notes)
                        ])
                    
                    # Display
                    sample_count += 1
                    status = ""
                    if avg_cps > 100:
                        status += "⚠️HIGH "
                    if voltage < 3.0:
                        status += "🔋LOW "
                    
                    display_time = datetime.now().strftime("%H:%M:%S")
                    click.echo(f"{display_time:<20} {cpm:>6} {avg_cps:>6.1f} "
                             f"{voltage:>6.1f}V {status}")
                
                except Exception as e:
                    click.echo(click.style(f"Error collecting data: {e}", fg='yellow'))
                    time.sleep(1)
                    continue
        
        except KeyboardInterrupt:
            click.echo("\nStopping data logging...")
        
        finally:
            gmc.stop_heartbeat()
            click.echo(f"\nLogged {sample_count} samples to {output}")
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()
        click.echo("Disconnected")


@main.command()
@common_options
@click.option('--address', '-a', type=int, help='Starting address (default: 0)')
@click.option('--length', '-l', type=int, help='Number of bytes to read (default: 1024)')
@click.option('--output', '-o', help='Output file for raw data')
@click.option('--format', 'output_format', type=click.Choice(['hex', 'raw']), default='hex', help='Output format')
def history(port: str, baudrate: int, timeout: float, address: Optional[int], 
           length: Optional[int], output: Optional[str], output_format: str):
    """Read historical data from device flash memory."""
    if address is None:
        address = 0
    if length is None:
        length = 1024
    
    if length > 4096:
        click.echo(click.style("Error: Maximum length is 4096 bytes", fg='red'), err=True)
        sys.exit(1)
    
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        click.echo(f"Reading {length} bytes from address {address}...")
        
        data = gmc.get_history_data(address, length)
        
        if output:
            # Write to file
            if output_format == 'raw':
                with open(output, 'wb') as f:
                    f.write(data)
            else:
                with open(output, 'w') as f:
                    f.write(data.hex())
            
            click.echo(f"Data written to {output}")
        else:
            # Display to console
            if output_format == 'raw':
                click.echo("Raw data (first 256 bytes):")
                click.echo(data[:256])
            else:
                click.echo("Hex data:")
                hex_str = data.hex()
                # Format as hex dump
                for i in range(0, min(len(hex_str), 512), 32):
                    line = hex_str[i:i+32]
                    formatted = ' '.join([line[j:j+2] for j in range(0, len(line), 2)])
                    click.echo(f"{address + i//2:08x}: {formatted}")
                
                if len(data) > 256:
                    click.echo(f"... ({len(data)} total bytes)")
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()
        click.echo("Disconnected")


@main.command()
@common_options
@click.argument('key_num', type=click.IntRange(0, 3))
def key(port: str, baudrate: int, timeout: float, key_num: int):
    """Send software key press (0-3 for S1-S4)."""
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        click.echo(f"Sending key S{key_num + 1} press...")
        
        if gmc.send_key(key_num):
            click.echo(click.style("✓ Key sent successfully", fg='green'))
        else:
            click.echo(click.style("Failed to send key", fg='red'))
            sys.exit(1)
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()


@main.group()
def config():
    """Configuration management commands."""
    pass


@config.command('read')
@common_options
@click.option('--output', '-o', help='Output file for configuration data')
def config_read(port: str, baudrate: int, timeout: float, output: Optional[str]):
    """Read device configuration."""
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        config_data = gmc.get_config()
        
        if output:
            with open(output, 'wb') as f:
                f.write(config_data)
            click.echo(f"Configuration saved to {output}")
        else:
            click.echo(f"Configuration data ({len(config_data)} bytes):")
            hex_str = config_data.hex()
            for i in range(0, len(hex_str), 32):
                line = hex_str[i:i+32]
                formatted = ' '.join([line[j:j+2] for j in range(0, len(line), 2)])
                click.echo(f"{i//2:08x}: {formatted}")
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()


@config.command('write')
@common_options
@click.argument('address', type=click.IntRange(0, 255))
@click.argument('value', type=click.IntRange(0, 255))
def config_write(port: str, baudrate: int, timeout: float, address: int, value: int):
    """Write single byte to configuration."""
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        click.echo(f"Writing 0x{value:02x} to config address {address}...")
        
        if gmc.write_config(address, value):
            click.echo(click.style("✓ Configuration updated", fg='green'))
        else:
            click.echo(click.style("Failed to update configuration", fg='red'))
            sys.exit(1)
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()


@config.command('erase')
@common_options
@click.confirmation_option(prompt='Are you sure you want to erase all configuration?')
def config_erase(port: str, baudrate: int, timeout: float):
    """Erase all configuration data (DESTRUCTIVE!)."""
    click.echo(f"Connecting to GMC on {port}...")
    
    gmc = GMCInterface(port, baudrate, timeout)
    
    try:
        if not gmc.connect():
            click.echo(click.style("Failed to connect to device!", fg='red'), err=True)
            sys.exit(1)
        
        click.echo("Erasing configuration...")
        
        if gmc.erase_config():
            click.echo(click.style("✓ Configuration erased", fg='green'))
        else:
            click.echo(click.style("Failed to erase configuration", fg='red'))
            sys.exit(1)
    
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)
    
    finally:
        gmc.disconnect()


if __name__ == "__main__":
    main()