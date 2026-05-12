"""
GMC Geiger Counter Interface.

Communication interface for GQ GMC geiger counters using the GQ-RFC1201
protocol over serial. Spec: https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt

Tested against the GMC-600; other GMC-280/300/320 models should be largely
compatible but a few commands (temperature, gyroscope, datetime) require
firmware revisions noted in the protocol document.
"""

import logging
import struct
import time
from datetime import datetime
from types import TracebackType

import serial

logger = logging.getLogger(__name__)

_ACK = 0xAA


class GMCError(Exception):
    """Base exception for GMC communication errors."""


class GMCNotConnectedError(GMCError):
    """Raised when an operation is attempted on a disconnected device."""


class GMCInterface:
    """Interface for a GQ GMC geiger counter over a serial connection."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        """
        Args:
            port: Serial port (e.g., ``'COM3'`` on Windows,
                ``'/dev/ttyUSB0'`` on Linux).
            baudrate: 115200 for GMC-600 / current firmware; 57600 for older GMC-300.
            timeout: Per-read timeout in seconds.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: serial.Serial | None = None
        self.heartbeat_active = False
        # GMC-500/600/800 family returns CPM and heartbeat CPS as 4 bytes;
        # the older GMC-280/300/320 family returns 2. Detected lazily from GETVER.
        self._cpm_width: int | None = None
        # Cached GETVER response. Length is firmware-dependent (14 bytes on the
        # original spec, 15 on GMC-600+ Re.2.22, etc.), so we use a drain read
        # and remember the result to avoid round-tripping it on every call.
        self._version: str | None = None

    def connect(self) -> bool:
        """Open the serial port. Returns True on success, False on serial error."""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
            return self.serial_conn.is_open
        except serial.SerialException:
            logger.exception("Failed to open serial port %s", self.port)
            return False

    def disconnect(self) -> None:
        """Close the serial port. Stops the heartbeat first if active."""
        if self.serial_conn and self.serial_conn.is_open:
            if self.heartbeat_active:
                try:
                    self._write(b"<HEARTBEAT0>>")
                except serial.SerialException:
                    pass
                self.heartbeat_active = False
            self.serial_conn.close()

    def __enter__(self) -> "GMCInterface":
        if not self.connect():
            raise GMCError(f"Could not connect to {self.port}")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()

    def _require_conn(self) -> serial.Serial:
        if self.serial_conn is None or not self.serial_conn.is_open:
            raise GMCNotConnectedError("Not connected to device")
        return self.serial_conn

    def _write(self, data: bytes) -> None:
        conn = self._require_conn()
        conn.write(data)
        conn.flush()

    def _read_exact(self, n: int) -> bytes:
        """Read exactly ``n`` bytes or raise GMCError on short read (timeout)."""
        conn = self._require_conn()
        buf = conn.read(n)
        if len(buf) != n:
            raise GMCError(f"Short read: expected {n} bytes, got {len(buf)}")
        return buf

    def _send(self, command: bytes, response_len: int) -> bytes:
        """Send a raw command (including delimiters) and read a fixed-length reply."""
        self._write(command)
        if response_len == 0:
            return b""
        return self._read_exact(response_len)

    def _drain_response(self, command: bytes, settle: float = 0.1) -> bytes:
        """Send a command and read whatever the device sends back.

        Use for responses whose length is firmware-dependent. Polls
        ``in_waiting`` until two consecutive checks agree, so a slow device
        finishing a long transfer (e.g. GETCFG's 256–512 bytes) isn't cut off.
        """
        conn = self._require_conn()
        conn.reset_input_buffer()
        self._write(command)
        time.sleep(settle)
        last = -1
        n = conn.in_waiting
        while n != last:
            last = n
            time.sleep(settle)
            n = conn.in_waiting
        if n == 0:
            raise GMCError(f"No response to {command!r}")
        return conn.read(n)

    @staticmethod
    def _wrap(command: str, params: bytes = b"") -> bytes:
        """Build a ``<CMD[params]>>`` frame. Params are raw bytes per GQ-RFC1201."""
        return b"<" + command.encode("ascii") + params + b">>"

    def get_version(self) -> str:
        """Hardware model + firmware version as ASCII.

        Length is firmware-dependent (14 bytes on the original GQ-RFC1201
        spec, 15 on GMC-600+ Re.2.22, etc.), so we drain the whole response.
        Cached after the first call.
        """
        if self._version is None:
            response = self._drain_response(self._wrap("GETVER"))
            self._version = response.decode("ascii", errors="ignore").strip("\x00 ")
        return self._version

    def _cpm_response_width(self) -> int:
        """Return 4 for GMC-500/600/800 family, 2 for older GMC-280/300/320.

        Cached after the first call. Detected from ``GETVER`` because the GETCPM
        response width is firmware-family dependent and there is no command to
        query it directly.
        """
        if self._cpm_width is None:
            version = self.get_version()
            if version.startswith(("GMC-500", "GMC-600", "GMC-800")):
                self._cpm_width = 4
            else:
                self._cpm_width = 2
        return self._cpm_width

    def get_cpm(self) -> int:
        """Current counts per minute.

        Response width is 2 bytes on GMC-280/300/320 and 4 bytes on
        GMC-500/600/800 (auto-detected from GETVER on first call).
        """
        width = self._cpm_response_width()
        response = self._send(self._wrap("GETCPM"), width)
        fmt = ">I" if width == 4 else ">H"
        (cpm,) = struct.unpack(fmt, response)
        return int(cpm)

    def get_battery_voltage(self) -> float:
        """Battery voltage in volts.

        GMC-280/300/320 return a single byte (value × 10 V). GMC-500/600 firmware
        variants return a short ASCII string like ``b'4.3v\\x00'``; this method
        handles either form.
        """
        data = self._drain_response(self._wrap("GETVOLT"))
        text = data.decode("ascii", errors="ignore").strip("\x00 \t\r\nvV")
        try:
            return float(text)
        except ValueError:
            return data[0] / 10.0

    def get_serial_number(self) -> str:
        """7-byte serial number, returned as a lowercase hex string."""
        response = self._send(self._wrap("GETSERIAL"), 7)
        return response.hex()

    def get_temperature(self) -> float | None:
        """Temperature in Celsius (GMC-320 Re.3.01+), or None if unsupported.

        Response layout per GQ-RFC1201 section 24:
            BYTE1 = integer part, BYTE2 = decimal part,
            BYTE3 = sign (0 = positive, nonzero = negative),
            BYTE4 = 0xAA terminator.
        """
        try:
            response = self._send(self._wrap("GETTEMP"), 4)
        except GMCError:
            return None
        integer_part = response[0]
        decimal_part = response[1]
        negative = response[2] != 0
        temp = integer_part + decimal_part / 10.0
        return -temp if negative else temp

    def get_gyroscope(self) -> tuple[int, int, int] | None:
        """3-axis gyroscope reading (GMC-320 Re.3.01+), or None if unsupported."""
        try:
            response = self._send(self._wrap("GETGYRO"), 7)
        except GMCError:
            return None
        x, y, z = struct.unpack(">HHH", response[:6])
        return (x, y, z)

    def get_datetime(self) -> datetime | None:
        """Device real-time clock (GMC-280/300 Re.3.00+), or None if unsupported."""
        try:
            response = self._send(self._wrap("GETDATETIME"), 7)
        except GMCError:
            return None
        try:
            return datetime(
                2000 + response[0],
                response[1],
                response[2],
                response[3],
                response[4],
                response[5],
            )
        except ValueError:
            return None

    def set_datetime(self, dt: datetime) -> bool:
        """Set device real-time clock (GMC-280/300 Re.3.00+).

        Parameters are sent as 6 raw bytes (YY MM DD HH MM SS), as required by
        the GQ-RFC1201 spec — *not* as ASCII hex digits.
        """
        params = bytes(
            [dt.year - 2000, dt.month, dt.day, dt.hour, dt.minute, dt.second]
        )
        response = self._send(self._wrap("SETDATETIME", params), 1)
        return response[0] == _ACK

    def start_heartbeat(self) -> bool:
        """Begin automatic CPS streaming (one packet per second).

        Packet width depends on device family — detected here so the stream
        reader doesn't have to round-trip GETVER mid-stream.
        """
        self._cpm_response_width()  # populate cache before stream starts
        conn = self._require_conn()
        conn.reset_input_buffer()
        self._write(self._wrap("HEARTBEAT1"))
        self.heartbeat_active = True
        return True

    def stop_heartbeat(self) -> bool:
        """Stop the CPS stream and discard any residual streamed bytes."""
        conn = self._require_conn()
        self._write(self._wrap("HEARTBEAT0"))
        self.heartbeat_active = False
        # Drain any in-flight heartbeat packets so the next command sees a clean buffer.
        time.sleep(0.2)
        conn.reset_input_buffer()
        return True

    def read_heartbeat(self) -> int | None:
        """Read one CPS sample from the stream, or None if no data is waiting.

        Sample width matches the device's CPM width (4 bytes on GMC-500/600/800,
        2 bytes on older models). The legacy 2-byte form reserves the top 2
        bits, so we mask to 14 bits in that case.
        """
        if not self.heartbeat_active:
            return None
        width = self._cpm_response_width()
        conn = self._require_conn()
        if conn.in_waiting < width:
            return None
        data = conn.read(width)
        if len(data) != width:
            return None
        if width == 4:
            (raw,) = struct.unpack(">I", data)
            return int(raw)
        (raw,) = struct.unpack(">H", data)
        return int(raw) & 0x3FFF

    def get_history_data(self, address: int, length: int) -> bytes:
        """Read ``length`` bytes from flash starting at ``address``.

        Address is 3 bytes (MSB first), length is 2 bytes (MSB first); both are
        sent as raw bytes per GQ-RFC1201 section 6. ``length`` must be ≤ 4096.
        """
        if length <= 0 or length > 4096:
            raise ValueError("length must be in 1..4096")
        if address < 0 or address > 0xFFFFFF:
            raise ValueError("address must fit in 24 bits")
        params = struct.pack(">I", address)[1:] + struct.pack(">H", length)
        return self._send(self._wrap("SPIR", params), length)

    def get_config(self) -> bytes:
        """Configuration block.

        GQ-RFC1201 specifies 256 bytes; firmware on the GMC-500/600/800 family
        returns 512. Drained dynamically so both work.
        """
        return self._drain_response(self._wrap("GETCFG"), settle=0.2)

    def erase_config(self) -> bool:
        """Erase all configuration data."""
        return self._send(self._wrap("ECFG"), 1)[0] == _ACK

    def write_config(self, address: int, data: int) -> bool:
        """Write a single byte to configuration memory.

        Both address and data are sent as raw bytes (one each), per
        GQ-RFC1201 section 9 — *not* as ASCII hex digits.
        """
        if not 0 <= address <= 255:
            raise ValueError("address must be 0..255")
        if not 0 <= data <= 255:
            raise ValueError("data must be 0..255")
        params = bytes([address, data])
        return self._send(self._wrap("WCFG", params), 1)[0] == _ACK

    def update_config(self) -> bool:
        """Reload configuration (commit writes)."""
        return self._send(self._wrap("CFGUPDATE"), 1)[0] == _ACK

    def send_key(self, key_num: int) -> bool:
        """Simulate a software key press. ``key_num`` is 0..3 → S1..S4."""
        if not 0 <= key_num <= 3:
            raise ValueError("key_num must be 0..3")
        # KEY accepts either the ASCII form (<KEY0>>, Re.2.11+) or a single
        # raw byte parameter on older firmware. We use the ASCII form.
        self._send(self._wrap(f"KEY{key_num}"), 0)
        return True

    def power_off(self) -> bool:
        """Power the device off. No response is returned."""
        self._send(self._wrap("POWEROFF"), 0)
        return True

    def power_on(self) -> bool:
        """Power the device on. No response is returned."""
        self._send(self._wrap("POWERON"), 0)
        return True

    def reboot(self) -> bool:
        """Reboot the device. No response is returned."""
        self._send(self._wrap("REBOOT"), 0)
        return True

    def factory_reset(self, confirm: bool = False) -> bool:
        """Restore factory defaults. Pass ``confirm=True`` to acknowledge.

        Raises:
            GMCError: if ``confirm`` is not True.
        """
        if not confirm:
            raise GMCError(
                "factory_reset() is destructive; pass confirm=True to proceed"
            )
        return self._send(self._wrap("FACTORYRESET"), 1)[0] == _ACK
