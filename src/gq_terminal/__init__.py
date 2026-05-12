"""GQ Terminal — Python interface for GQ GMC geiger counters (GQ-RFC1201)."""

from importlib.metadata import PackageNotFoundError, version

from .interface import GMCError, GMCInterface, GMCNotConnectedError

try:
    __version__ = version("gq-terminal")
except PackageNotFoundError:  # editable install before metadata is built
    __version__ = "0.0.0+unknown"

__all__ = ["GMCInterface", "GMCError", "GMCNotConnectedError", "__version__"]
