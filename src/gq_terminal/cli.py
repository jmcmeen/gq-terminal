"""Click-based command-line interface for GQ GMC geiger counters."""

import csv
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import click

from .interface import GMCError, GMCInterface

HIGH_CPS_THRESHOLD = 100
HIGH_CPS_LOG_THRESHOLD = 200
LOW_BATTERY_VOLTS = 3.0

F = TypeVar("F", bound=Callable[..., Any])


def common_options(func: F) -> F:
    """Decorator that adds --port / --baudrate / --timeout to a command."""
    func = click.option(
        "--port", "-p", required=True, help="Serial port (e.g., COM3, /dev/ttyUSB0)"
    )(func)
    func = click.option(
        "--baudrate", "-b", default=115200, show_default=True, help="Baud rate"
    )(func)
    func = click.option(
        "--timeout",
        "-t",
        default=2.0,
        show_default=True,
        help="Serial read timeout in seconds",
    )(func)
    return func


def _open(port: str, baudrate: int, timeout: float) -> GMCInterface:
    gmc = GMCInterface(port, baudrate, timeout)
    if not gmc.connect():
        click.echo(click.style("Failed to connect to device", fg="red"), err=True)
        sys.exit(1)
    return gmc


def _battery_line(voltage: float) -> str:
    fg = "red" if voltage < LOW_BATTERY_VOLTS else None
    return click.style(f"Battery: {voltage:.2f}V", fg=fg)


@click.group()
@click.version_option(package_name="gq-terminal", prog_name="gq-terminal")
def main() -> None:
    """GQ Terminal — command-line interface for GQ GMC geiger counters."""


@main.command()
@common_options
@click.option("--verbose", "-v", is_flag=True, help="Show detailed device information")
def info(port: str, baudrate: int, timeout: float, verbose: bool) -> None:
    """Get device information and current readings."""
    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        click.echo(click.style("Connected", fg="green"))
        version = gmc.get_version()
        serial_num = gmc.get_serial_number()
        voltage = gmc.get_battery_voltage()
        cpm = gmc.get_cpm()

        click.echo("\n=== Device Information ===")
        click.echo(f"Model/Version: {version}")
        click.echo(f"Serial Number: {serial_num}")
        click.echo(_battery_line(voltage))
        click.echo(f"Current CPM: {cpm}")

        if voltage < LOW_BATTERY_VOLTS:
            click.echo(click.style("Low battery warning", fg="yellow"))

        if verbose:
            temp = gmc.get_temperature()
            if temp is not None:
                click.echo(f"Temperature: {temp:.1f} C")
            gyro = gmc.get_gyroscope()
            if gyro is not None:
                click.echo(f"Gyroscope: X={gyro[0]}, Y={gyro[1]}, Z={gyro[2]}")
            dt = gmc.get_datetime()
            if dt is not None:
                click.echo(f"Device Time: {dt}")
            config = gmc.get_config()
            click.echo(f"Config Size: {len(config)} bytes")
            click.echo(f"Config Preview: {config[:16].hex()}")
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@main.command()
@common_options
@click.option(
    "--duration", "-d", default=0, help="Monitoring duration in seconds (0 = infinite)"
)
@click.option(
    "--interval", "-i", default=1.0, help="Display update interval in seconds"
)
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (CPS only)")
def monitor(
    port: str,
    baudrate: int,
    timeout: float,
    duration: int,
    interval: float,
    quiet: bool,
) -> None:
    """Real-time radiation monitoring via heartbeat mode."""
    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        if not quiet:
            click.echo(f"Connected to {gmc.get_version()}")
            voltage = gmc.get_battery_voltage()
            click.echo(_battery_line(voltage))
            if voltage < LOW_BATTERY_VOLTS:
                click.echo(
                    click.style("Warning: low battery may affect readings", fg="yellow")
                )
            click.echo("\nStarting real-time monitoring (Ctrl+C to stop)\n")
            click.echo(
                "Time".ljust(12)
                + "CPS".rjust(6)
                + "CPM".rjust(6)
                + "Battery".rjust(10)
                + "  Status"
            )
            click.echo("-" * 50)

        gmc.start_heartbeat()

        start_time = time.time()
        last_update = start_time
        cpm = 0
        voltage = 0.0
        max_cps = 0
        min_cps: int | None = None
        total_counts = 0
        samples = 0

        try:
            while True:
                if duration > 0 and time.time() - start_time >= duration:
                    break

                cps = gmc.read_heartbeat()
                if cps is not None:
                    samples += 1
                    total_counts += cps
                    max_cps = max(max_cps, cps)
                    min_cps = cps if min_cps is None else min(min_cps, cps)

                    now = time.time()
                    if now - last_update >= 5.0:
                        # CPM and voltage change slowly; sample them less often.
                        # Pause the heartbeat to avoid intermixing reads.
                        gmc.stop_heartbeat()
                        try:
                            cpm = gmc.get_cpm()
                            voltage = gmc.get_battery_voltage()
                        except GMCError:
                            pass
                        gmc.start_heartbeat()
                        last_update = now

                    if quiet:
                        click.echo(f"{cps}")
                    else:
                        status = []
                        if cps > HIGH_CPS_THRESHOLD:
                            status.append("HIGH")
                        if voltage and voltage < LOW_BATTERY_VOLTS:
                            status.append("LOW-BAT")
                        click.echo(
                            f"{datetime.now().strftime('%H:%M:%S'):<12}"
                            f"{cps:>6}{cpm:>6}{voltage:>8.1f}V  " + " ".join(status)
                        )

                time.sleep(interval)
        except KeyboardInterrupt:
            click.echo("\nStopping monitoring...")
        finally:
            gmc.stop_heartbeat()

        if not quiet and samples > 0:
            duration_actual = time.time() - start_time
            avg_cps = total_counts / samples
            click.echo("\n" + "=" * 40)
            click.echo("MONITORING STATISTICS")
            click.echo("=" * 40)
            click.echo(f"Duration: {duration_actual:.1f}s")
            click.echo(f"Samples: {samples}")
            click.echo(f"Average CPS: {avg_cps:.2f}")
            click.echo(f"Max CPS: {max_cps}")
            click.echo(f"Min CPS: {min_cps}")
            click.echo(f"Total counts: {total_counts}")
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@main.command()
@common_options
@click.option("--output", "-o", help="Output CSV file (default: auto-generated)")
@click.option(
    "--interval",
    "-i",
    default=60.0,
    show_default=True,
    help="Logging interval in seconds",
)
@click.option(
    "--duration", "-d", default=0, help="Logging duration in seconds (0 = infinite)"
)
def log(
    port: str,
    baudrate: int,
    timeout: float,
    output: str | None,
    interval: float,
    duration: int,
) -> None:
    """Log radiation readings to a CSV file."""
    if not output:
        output = f"radiation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    log_path = Path(output)

    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        version = gmc.get_version()
        serial_num = gmc.get_serial_number()
        click.echo(f"Connected to {version} (Serial: {serial_num})")
        click.echo(f"Logging to: {output}")
        click.echo(f"Interval: {interval}s\n")

        with log_path.open("w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "timestamp",
                    "cpm",
                    "battery_voltage",
                    "temperature",
                    "device_time",
                    "notes",
                ]
            )

        start_time = time.time()
        sample_count = 0
        click.echo(f"{'Time':<10}{'CPM':>6}{'Battery':>10}  Status")
        click.echo("-" * 50)

        try:
            while True:
                if duration > 0 and time.time() - start_time >= duration:
                    break

                iter_start = time.time()
                try:
                    cpm = gmc.get_cpm()
                    voltage = gmc.get_battery_voltage()
                    temperature = gmc.get_temperature()
                    device_time = gmc.get_datetime()
                except GMCError as e:
                    click.echo(click.style(f"Read error: {e}", fg="yellow"), err=True)
                    time.sleep(1)
                    continue

                notes = []
                if cpm > HIGH_CPS_LOG_THRESHOLD * 60:
                    notes.append("HIGH_RADIATION")
                if voltage < LOW_BATTERY_VOLTS:
                    notes.append("LOW_BATTERY")

                with log_path.open("a", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(
                        [
                            datetime.now().isoformat(),
                            cpm,
                            f"{voltage:.2f}",
                            f"{temperature:.1f}" if temperature is not None else "",
                            device_time.isoformat() if device_time else "",
                            "; ".join(notes),
                        ]
                    )

                sample_count += 1
                click.echo(
                    f"{datetime.now().strftime('%H:%M:%S'):<10}"
                    f"{cpm:>6}{voltage:>8.1f}V  " + " ".join(notes)
                )

                elapsed = time.time() - iter_start
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        except KeyboardInterrupt:
            click.echo("\nStopping data logging...")

        click.echo(f"\nLogged {sample_count} samples to {output}")
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@main.command()
@common_options
@click.option("--address", "-a", type=int, default=0, show_default=True)
@click.option("--length", "-l", type=int, default=1024, show_default=True)
@click.option("--output", "-o", help="Output file for raw data")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["hex", "raw"]),
    default="hex",
    show_default=True,
)
def history(
    port: str,
    baudrate: int,
    timeout: float,
    address: int,
    length: int,
    output: str | None,
    output_format: str,
) -> None:
    """Read historical data from device flash memory."""
    if length > 4096:
        click.echo(
            click.style("Error: maximum length is 4096 bytes", fg="red"), err=True
        )
        sys.exit(1)

    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        click.echo(f"Reading {length} bytes from address {address}...")
        data = gmc.get_history_data(address, length)

        if output:
            out_path = Path(output)
            if output_format == "raw":
                out_path.write_bytes(data)
            else:
                out_path.write_text(data.hex())
            click.echo(f"Data written to {output}")
        else:
            if output_format == "raw":
                click.echo("Raw data (first 256 bytes):")
                click.echo(data[:256])
            else:
                hex_str = data.hex()
                for i in range(0, min(len(hex_str), 512), 32):
                    line = hex_str[i : i + 32]
                    formatted = " ".join(
                        line[j : j + 2] for j in range(0, len(line), 2)
                    )
                    click.echo(f"{address + i // 2:08x}: {formatted}")
                if len(data) > 256:
                    click.echo(f"... ({len(data)} total bytes)")
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@main.command()
@common_options
@click.argument("key_num", type=click.IntRange(0, 3))
def key(port: str, baudrate: int, timeout: float, key_num: int) -> None:
    """Send a software key press (0-3 = S1-S4)."""
    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        gmc.send_key(key_num)
        click.echo(click.style(f"Sent key S{key_num + 1}", fg="green"))
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@main.group()
def config() -> None:
    """Configuration management commands."""


@config.command("read")
@common_options
@click.option("--output", "-o", help="Output file for configuration data")
def config_read(port: str, baudrate: int, timeout: float, output: str | None) -> None:
    """Read the device's 256-byte configuration block."""
    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        data = gmc.get_config()
        if output:
            Path(output).write_bytes(data)
            click.echo(f"Configuration saved to {output}")
        else:
            click.echo(f"Configuration data ({len(data)} bytes):")
            hex_str = data.hex()
            for i in range(0, len(hex_str), 32):
                line = hex_str[i : i + 32]
                formatted = " ".join(line[j : j + 2] for j in range(0, len(line), 2))
                click.echo(f"{i // 2:08x}: {formatted}")
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@config.command("write")
@common_options
@click.argument("address", type=click.IntRange(0, 255))
@click.argument("value", type=click.IntRange(0, 255))
def config_write(
    port: str, baudrate: int, timeout: float, address: int, value: int
) -> None:
    """Write a single byte to configuration memory."""
    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        if gmc.write_config(address, value):
            click.echo(
                click.style(f"Wrote 0x{value:02x} to address {address}", fg="green")
            )
        else:
            click.echo(click.style("Device did not acknowledge write", fg="red"))
            sys.exit(1)
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


@config.command("erase")
@common_options
@click.confirmation_option(prompt="Are you sure you want to erase all configuration?")
def config_erase(port: str, baudrate: int, timeout: float) -> None:
    """Erase all configuration data (destructive)."""
    click.echo(f"Connecting to GMC on {port}...")
    gmc = _open(port, baudrate, timeout)
    try:
        if gmc.erase_config():
            click.echo(click.style("Configuration erased", fg="green"))
        else:
            click.echo(click.style("Device did not acknowledge erase", fg="red"))
            sys.exit(1)
    except GMCError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        gmc.disconnect()


if __name__ == "__main__":
    main()
