# GQ Terminal

A Python interface for GQ GMC Geiger Counters using the GQ-RFC1201 communication protocol.

This implementation has currently only been tested with the GQ GMC-600

Vibe coded (I know I'm sorry) using this file as context, https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt

## Features

- Complete implementation of GQ-RFC1201 protocol (26 commands)
- Real-time radiation monitoring with heartbeat mode
- Battery voltage and device status monitoring
- Temperature and gyroscope data (for supported models)
- Configuration management
- Historical data retrieval from flash memory
- Date/time synchronization
- Command-line interface for quick testing

## Installation

```bash
pip install gq-terminal
```

## Quick Start

### Command Line Usage

The CLI now uses Click framework with subcommands for better organization:

```bash
# Get device information
gq-terminal info --port COM3

# Detailed device info
gq-terminal info --port /dev/ttyUSB0 --verbose

# Real-time monitoring
gq-terminal monitor --port COM3

# Monitor for 30 seconds with quiet output
gq-terminal monitor --port COM3 --duration 30 --quiet

# Log data to CSV file
gq-terminal log --port COM3 --interval 60 --output radiation.csv

# Read device configuration
gq-terminal config read --port COM3

# Send software key press (S1-S4)
gq-terminal key --port COM3 2  # Press S3

# Read historical data from flash
gq-terminal history --port COM3 --address 0 --length 1024

# Get help for any command
gq-terminal --help
gq-terminal monitor --help
```

### Python API Usage

```python
from gq_terminal import GMCInterface

# Connect to device
gmc = GMCInterface('/dev/ttyUSB0', baudrate=115200)
if gmc.connect():
    print("Connected!")
    
    # Get device info
    version = gmc.get_version()
    serial = gmc.get_serial_number()
    print(f"Device: {version}, Serial: {serial}")
    
    # Get current radiation reading
    cpm = gmc.get_cpm()
    print(f"Current CPM: {cpm}")
    
    # Get battery voltage
    voltage = gmc.get_battery_voltage()
    print(f"Battery: {voltage:.1f}V")
    
    # Start real-time monitoring
    gmc.start_heartbeat()
    for _ in range(10):
        cps = gmc.read_heartbeat()
        if cps is not None:
            print(f"CPS: {cps}")
        time.sleep(1)
    gmc.stop_heartbeat()
    
    gmc.disconnect()
```

## Supported Commands

The interface supports all GQ-RFC1201 protocol commands:

### Basic Operations
- `get_version()` - Hardware model and firmware version
- `get_cpm()` - Current counts per minute
- `get_battery_voltage()` - Battery voltage status
- `get_serial_number()` - Device serial number

### Real-time Monitoring
- `start_heartbeat()` - Enable automatic CPS reporting
- `stop_heartbeat()` - Disable automatic reporting
- `read_heartbeat()` - Read CPS data from heartbeat mode

### Environmental Sensors (model dependent)
- `get_temperature()` - Temperature in Celsius
- `get_gyroscope()` - 3-axis gyroscope data

### Date/Time Management
- `get_datetime()` - Get device date/time
- `set_datetime(datetime)` - Set device date/time

### Data Retrieval
- `get_history_data(address, length)` - Read flash memory data
- `get_config()` - Get 256-byte configuration

### Configuration Management
- `write_config(address, data)` - Write configuration byte
- `erase_config()` - Erase all configuration
- `update_config()` - Reload configuration

### Device Control
- `send_key(key_num)` - Send software key press (S1-S4)
- `power_off()` - Power off device
- `power_on()` - Power on device
- `reboot()` - Reboot device
- `factory_reset()` - Reset to factory defaults

## Serial Port Configuration

The package uses the following serial settings optimized for GMC-600 with latest firmware:

- **Baud Rate**: 115200 (configurable)
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Flow Control**: None

For older firmware versions, you may need to use 57600 baud rate.

## Protocol Details

This implementation follows the GQ-RFC1201 specification:
- Commands are formatted as `<COMMAND>>` with ASCII delimiters
- All parameters are hexadecimal values
- Binary data responses are handled appropriately
- Proper error handling for communication timeouts

## CLI Commands

The Click-based CLI provides these commands:

### Main Commands
- `info` - Get device information and current readings
- `monitor` - Real-time radiation monitoring with statistics
- `log` - Data logging to CSV files
- `history` - Read historical data from flash memory  
- `key` - Send software key presses (S1-S4)

### Configuration Commands
- `config read` - Read device configuration
- `config write ADDRESS VALUE` - Write single config byte
- `config erase` - Erase all configuration (with confirmation)

### Common Options
All commands support these options:
- `--port` / `-p` - Serial port (required)
- `--baudrate` / `-b` - Baud rate (default: 115200)
- `--timeout` / `-t` - Serial timeout (default: 2.0s)

### Examples
```bash
# Get device info with verbose output
gq-terminal info -p COM3 -v

# Monitor for 5 minutes with 30-second updates
gq-terminal monitor -p /dev/ttyUSB0 -d 300 -i 30

# Log data every 2 minutes to specific file
gq-terminal log -p COM3 -i 120 -o my_radiation_log.csv

# Read 2048 bytes from flash address 1000
gq-terminal history -p COM3 -a 1000 -l 2048 -o flash_data.bin --format raw

# Write config byte 0x42 to address 10
gq-terminal config write -p COM3 10 66
```

## Requirements

- Python 3.8+
- pyserial 3.5+
- click 8.0+
- Compatible GQ GMC geiger counter (GMC-280, GMC-300, GMC-320, GMC-600)

## License

CC0 1.0 Universal

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Changelog

### 0.1.0
- Initial release
- Full GQ-RFC1201 protocol implementation
- Command-line interface
- Real-time monitoring support