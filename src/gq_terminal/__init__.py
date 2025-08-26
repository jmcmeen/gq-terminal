"""
GQ Terminal - Python interface for GQ GMC-600 geiger counter.

This package provides a Python interface for communicating with GQ GMC-600
geiger counters using the GQ-RFC1201 protocol over serial connection.
"""

from .interface import GMCInterface

__version__ = "0.1.0"
__all__ = ["GMCInterface"]