"""GQ Terminal — Python interface for GQ GMC geiger counters (GQ-RFC1201)."""

from importlib.metadata import PackageNotFoundError, version

from .interface import (
    Calibration,
    GMCError,
    GMCInterface,
    GMCNotConnectedError,
    SerialPortInfo,
    discover_ports,
    find_gmc_port,
    parse_calibration,
)

try:
    __version__ = version("gq-terminal")
except PackageNotFoundError:  # editable install before metadata is built
    __version__ = "0.0.0+unknown"

__all__ = [
    "GMCInterface",
    "GMCError",
    "GMCNotConnectedError",
    "SerialPortInfo",
    "Calibration",
    "discover_ports",
    "find_gmc_port",
    "parse_calibration",
    "__version__",
]
