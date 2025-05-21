"""
Asynchronous MQTT client for MicroPython and CPython.

This module provides an MQTT client that can be used in asynchronous
applications, supporting both MicroPython and standard CPython environments.
It aims to provide a familiar API similar to other MQTT client libraries.
"""
import asyncio
import binascii
import random
import struct
import sys

try:
    from rich.console import Console
except ImportError:

    class Console:
        def print_exception(self, show_locals: bool = False):
            log("Console not available")


console = Console()

__version__ = "1.0.6"

# Determine if running on MicroPython
_IS_MICROPYTHON = sys.implementation.name == "micropython"
_IS_ESP32 = sys.platform == "esp32" if _IS_MICROPYTHON else False

# Import platform-specific modules conditionally
if _IS_MICROPYTHON:
    try:
        from machine import RTC as hal_rtc
        from micropython import const
    except ImportError:
        # Fallback for platforms that don't support const
        def const(x):
            return x

        def hal_rtc():
            return None

    from time import gmtime, ticks_add, ticks_diff, ticks_ms

else:
    from time import gmtime, monotonic

    def const(x):
        return x

    # Define platform-independent ticks functions
    def ticks_ms():
        return int(monotonic() * 1000)

    def ticks_diff(ticks1, ticks2):
        return ticks1 - ticks2

    def ticks_add(ticks1, ticks2):
        return ticks1 + ticks2

    def hal_rtc():
        return None


class RTC:
    """
    A real-time clock (RTC) interface.

    This class provides a basic abstraction for accessing the system's RTC.
    It is designed to work on both MicroPython and CPython platforms.
    """

    def __init__(self):
        """Initializes the RTC interface."""
        pass

    def init(self, date_parts: tuple):
        """Initializes the RTC with the given date and time.

        This method is primarily for MicroPython devices.

        Args:
            date_parts: A tuple containing the date and time components
                        (year, month, day, weekday, hour, minute, second, microsecond).
        """
        if _IS_MICROPYTHON:
            rtc = hal_rtc()
            rtc.init(date_parts)

    def datetime(self) -> tuple:
        """Gets the current date and time from the RTC.

        Returns:
            A tuple representing the current date and time:
            (year, month, day, weekday, hour, minute, second, microsecond).
            The weekday is 0-6 for Monday-Sunday.
            Microseconds will be 0 on platforms that don't support it.
        """
        if _IS_MICROPYTHON:
            rtc = hal_rtc()
            return rtc.datetime()
        utc = gmtime()
        return (
            utc.tm_year,
            utc.tm_mon,
            utc.tm_mday,
            utc.tm_wday,
            utc.tm_hour,
            utc.tm_min,
            utc.tm_sec,
            0,
        )


class Datetime:
    def __init__(
        self,
        year: int = 0,
        month: int = 0,
        day: int = 0,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        weekday: int = 0,
        usec: int = 0,
    ):
        self.year: int = year
        self.month: int = month
        self.day: int = day
        self.hour: int = hour
        self.minute: int = minute
        self.second: int = second
        self.weekday: int = weekday
        self.usec: int = usec

    def utc_now(self) -> "Datetime":
        """Updates the Datetime object with the current UTC date and time.

        Returns:
            The updated Datetime object.
        """
        rtc = RTC()
        (
            self.year,
            self.month,
            self.day,
            self.weekday,
            self.hour,
            self.minute,
            self.second,
            self.usec,
        ) = rtc.datetime()
        return self

    def __str__(self) -> str:
        """Returns a string representation of the Datetime object.

        Format: YYYY-MM-DD HH:MM:SS

        Returns:
            The formatted date and time string.
        """
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}:{self.second:02d}"


def log(msg: str = ""):
    dt = Datetime()
    utc = str(dt.utc_now())
    ms = int(ticks_ms() % 1000)
    s = f"{utc}.{ms:03d} {msg}"
    print(s)


def memory_dump(data, offset=0, length=None, header: str = ""):
    if header:
        log(header)
    if length is None:
        length = len(data) - offset
    for i in range(offset, offset + length, 16):
        line = " ".join(f"{c:02x}" for c in data[i : i + 16])
        log(f"{i:04d}: {line}")


def dump_array(data, header=None, length=16, force_publish: bool = False):
    if data is None:
        return
    try:
        _dump_array_aux(data, header, length, force_publish)
    except Exception as e:
        len_data = len(data) if data else 0
        log(f"ERROR - dump_array - {data} ({len_data} bytes) - {e}")


def _dump_array_aux(data, header, length):
    if not data:
        return
    s = f"{header} ({len(data)} bytes)" if header is not None else ""
    print_table = "".join(
        (len(repr(chr(x))) == 3) and chr(x) or "." for x in range(256)
    )
    lines = []
    digits = 4 if isinstance(data, str) else 2
    for c in range(0, len(data), length):
        chars = data[c : c + length]
        hex_string = " ".join("%0*x" % (digits, x) for x in chars)
        printable = "".join(f"{(x <= 127 and print_table[x]) or '.'}" for x in chars)
        lines.append("%04d  %-*s  %s\n" % (c, length * 3, hex_string, printable))
    log(f"{s}\n{''.join(lines)}")


def generate_client_id():
    rnd = random.getrandbits(32)
    return f"esp32_{binascii.hexlify(rnd.to_bytes(4, 'big')).decode()}"


class StreamConnection:
    """
    Manages an asynchronous network stream connection.

    This class provides methods for opening, reading from, writing to,
    and closing a network connection, with support for both MicroPython
    and CPython's asyncio.

    Attributes:
        reader (asyncio.StreamReader): The stream reader.
        writer (asyncio.StreamWriter): The stream writer.
        platform (int): Indicates if running on MicroPython (MP) or CPython.
        _eof (bool): True if the end of the stream has been reached.
        _buffer (bytearray): Internal buffer for reading data.
        _debug (bool): If True, enables debug logging.
        _host (str): The host address for the connection.
        _port (int): The port number for the connection.
        _ssl (bool): True if SSL/TLS should be used.
        _timeout (Optional[float]): Connection and operation timeout in seconds.
        _read_lock (asyncio.Lock): Lock to synchronize read operations.
    """

    MP = 1
    CPYTHON = 2

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        is_micropython: bool,
        debug: bool = False,
    ):
        """
        Initializes the StreamConnection.

        Args:
            reader: The asyncio StreamReader.
            writer: The asyncio StreamWriter.
            is_micropython: True if running on MicroPython, False otherwise.
            debug: If True, enables debug logging.
        """
        self.reader = reader
        self.writer = writer
        self.platform = self.MP if is_micropython else self.CPYTHON
        self._eof = False
        self._buffer = bytearray()
        self._debug = debug
        self._host = None
        self._port = None
        self._ssl = False
        self._timeout = None
        self._read_lock = asyncio.Lock()

    @classmethod
    async def open(
        cls,
        host: str,
        port: int,
        ssl: bool = False,
        timeout: float = None,
        is_micropython: bool = False,
        debug: bool = False,
    ) -> "StreamConnection":
        """
        Opens a new stream connection.

        Args:
            host: The host address to connect to.
            port: The port number to connect to.
            ssl: If True, use SSL/TLS for the connection.
            timeout: Optional timeout in seconds for the connection attempt.
            is_micropython: True if running on MicroPython.
            debug: If True, enables debug logging.

        Returns:
            An instance of StreamConnection.

        Raises:
            ValueError: If the connection fails.
        """
        self = cls(None, None, is_micropython, debug)
        self._host = host
        self._port = port
        self._ssl = ssl
        self._timeout = timeout
        await self._connect()
        return self

    async def _connect(self):
        """Establishes the network connection."""
        try:
            if self._timeout:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port, ssl=self._ssl),
                    timeout=self._timeout,
                )
            else:
                reader, writer = await asyncio.open_connection(
                    self._host, self._port, ssl=self._ssl
                )
            self.reader = reader
            self.writer = writer
            self._eof = False
        except Exception as e:
            raise ValueError(f"StreamConnection:_connect. Failed to connect: {e}")

    async def reconnect(self, delay: float = 1):
        """
        Closes the current connection and attempts to reconnect.

        Args:
            delay: Time in seconds to wait before attempting to reconnect.
        """
        await self.close()
        if self._debug:
            print(f"Reconnecting in {delay}s...")
        await asyncio.sleep(delay)
        await self._connect()

    async def write(self, data: bytes, timeout: float = None, retries: int = 0):
        """
        Writes data to the stream.

        Args:
            data: The bytes to write.
            timeout: Optional timeout in seconds for the write operation.
            retries: Number of times to retry writing if it fails.

        Raises:
            ValueError: If the write operation fails after all retries.
        """
        attempt = 0
        while True:
            try:
                if self._debug:
                    print(f"Writing {len(data)} bytes")
                if self.platform == self.MP:
                    await self.writer.awrite(data)  # type: ignore[attr-defined]
                else:
                    self.writer.write(data)
                    await asyncio.wait_for(
                        self.writer.drain(), timeout or self._timeout
                    )
                return
            except Exception as e:
                if attempt >= retries:
                    raise ValueError(f"Write failed after {attempt + 1} attempts: {e}")
                attempt += 1
                if self._debug:
                    print(f"Write failed, retrying ({attempt}/{retries})...")
                await self.reconnect()

    async def read(self, n: int = -1) -> bytes:
        """
        Reads up to n bytes from the stream.

        If n is -1, reads until EOF.

        Args:
            n: The maximum number of bytes to read.

        Returns:
            The bytes read from the stream. Returns b"" if EOF is reached.
        """
        async with self._read_lock:
            if self._eof:
                return b""
            try:
                data = await asyncio.wait_for(self.reader.read(n), timeout=self._timeout)
            except asyncio.TimeoutError:
                log("StreamConnection:read timeout")
                self._eof = True # Assume EOF on timeout to prevent blocking loops
                return b""
            except Exception as e:
                log(f"StreamConnection:read error: {e}")
                self._eof = True # Assume EOF on other errors
                return b""

            if data == b"":
                self._eof = True
            return data

    async def readline(self) -> bytes:
        """
        Reads a line from the stream.

        A line is a sequence of bytes ending with a newline character (\\n).

        Returns:
            The line read from the stream, including the newline character.
            Returns b"" if EOF is reached.
        """
        if self._eof:
            return b""
        try:
            line = await asyncio.wait_for(self.reader.readline(), timeout=self._timeout)
        except asyncio.TimeoutError:
            log("StreamConnection:readline timeout")
            self._eof = True
            return b""
        except Exception as e:
            log(f"StreamConnection:readline error: {e}")
            self._eof = True
            return b""

        if line == b"":
            self._eof = True
        return line

    async def read_until(self, delimiter: bytes, max_bytes: int = 1024) -> bytes:
        """
        Reads from the stream until a specified delimiter is found or max_bytes are read.

        Args:
            delimiter: The byte sequence to search for.
            max_bytes: The maximum number of bytes to read into the internal buffer
                       before giving up.

        Returns:
            The bytes read from the stream, including the delimiter if found.
            If the delimiter is not found within max_bytes, returns the bytes read so far.
        """
        while delimiter not in self._buffer and len(self._buffer) < max_bytes:
            try:
                chunk = await self.read(64) # Read in small chunks
            except Exception as e:
                log(f"StreamConnection:read_until error during read: {e}")
                break # Stop reading on error
            if not chunk: # EOF reached
                break
            self._buffer.extend(chunk)

        idx = self._buffer.find(delimiter)
        if idx >= 0:
            result = self._buffer[: idx + len(delimiter)]
            self._buffer = self._buffer[idx + len(delimiter) :]
            return bytes(result)
        else:
            # Delimiter not found, return what's in the buffer up to max_bytes
            # or everything if less than max_bytes
            result = self._buffer[:]
            self._buffer.clear()
            return bytes(result)

    def at_eof(self) -> bool:
        """
        Checks if the end of the stream has been reached.

        Returns:
            True if EOF is reached, False otherwise.
        """
        return self._eof

    async def buffered_read(self, size: int) -> bytes:
        """
        Reads exactly `size` bytes from the stream, using an internal buffer.

        This method will block until `size` bytes are read or EOF is reached.

        Args:
            size: The number of bytes to read.

        Returns:
            The bytes read from the stream. If EOF is reached before `size`
            bytes are read, returns the bytes read so far.
        """
        while len(self._buffer) < size:
            try:
                chunk = await self.read(size - len(self._buffer))
            except Exception as e:
                log(f"StreamConnection:buffered_read error during read: {e}")
                break # Stop reading on error
            if not chunk:  # EOF
                break
            self._buffer.extend(chunk)
        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return bytes(result)

    async def close(self):
        """Closes the stream connection."""
        if self._debug:
            print("Closing connection")
        if self.writer:
            try:
                if self.platform == self.MP:
                    await self.writer.aclose()  # type: ignore[attr-defined]
                else:
                    self.writer.close()
                    await self.writer.wait_closed()
            except Exception as e:
                log(f"StreamConnection:close error: {e}")
        self.reader = None
        self.writer = None
        self._eof = True


    async def __aenter__(self) -> "StreamConnection":
        """Enters the runtime context related to this object."""
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Exits the runtime context related to this object."""
        await self.close()


class MqttStats:
    """
    Collects and manages statistics for MQTT client operations.

    Attributes:
        packets_sent (int): Total number of packets sent.
        packets_received (int): Total number of packets received.
        bytes_sent (int): Total number of bytes sent.
        bytes_received (int): Total number of bytes received.
        max_list_size (int): Maximum size for lists storing RTT and package sizes.
        pub_ok_count (int): Number of successful publish operations (QoS > 0).
        pub_fail_count (int): Number of failed publish operations (QoS > 0).
        pub_rtt_ms_list (list[int]): List of round-trip times for publish operations.
        pub_package_size_list (list[int]): List of published package sizes.
        sub_package_size_list (list[int]): List of subscribed (received) package sizes.
        ping_rtt_ms_list (list[int]): List of round-trip times for PINGREQ/PINGRESP.
        connections_sent (int): Number of connection attempts.
        connections_failed (int): Number of failed connection attempts.
        ping_sent_count (int): Number of PINGREQ packets sent.
        ping_received_count (int): Number of PINGRESP packets received.
    """

    def __init__(self):
        """Initializes MqttStats with default values."""
        self.packets_sent = 0
        self.packets_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.max_list_size = 10
        self.pub_ok_count = 0
        self.pub_fail_count = 0
        self.pub_rtt_ms_list = []
        self.pub_package_size_list = []
        self.sub_package_size_list = []
        self.ping_rtt_ms_list = []
        self.connections_sent = 0
        self.connections_failed = 0
        self.ping_sent_count = 0
        self.ping_received_count = 0
        self.ping_rtt_ms_list = []

    def publish(self, status: bool, rtt_ms: int, packet_size: int):
        """
        Records statistics for a publish operation.

        Args:
            status: True if the publish was successful (e.g., PUBACK received),
                    False otherwise.
            rtt_ms: Round-trip time in milliseconds for the publish operation.
            packet_size: Size of the published packet in bytes.
        """
        self.packets_sent += 1
        if status:
            self.pub_ok_count += 1
        else:
            self.pub_fail_count += 1
        if len(self.pub_rtt_ms_list) >= self.max_list_size:
            self.pub_rtt_ms_list.pop(0)
        self.pub_rtt_ms_list.append(rtt_ms)
        self.bytes_sent += packet_size
        if len(self.pub_package_size_list) >= self.max_list_size:
            self.pub_package_size_list.pop(0)
        self.pub_package_size_list.append(packet_size)

    def receive(self, packet_size: int):
        """
        Records statistics for a received packet.

        Args:
            packet_size: Size of the received packet in bytes.
        """
        self.packets_received += 1
        self.bytes_received += packet_size
        if len(self.sub_package_size_list) >= self.max_list_size:
            self.sub_package_size_list.pop(0)
        self.sub_package_size_list.append(packet_size)

    def connect(self):
        """Increments the count of connection attempts."""
        self.connections_sent += 1

    def connect_fail(self):
        """Increments the count of failed connection attempts."""
        self.connections_failed += 1

    def ping_sent(self):
        """Increments the count of PINGREQ packets sent."""
        self.ping_sent_count += 1

    def ping_received(self, rtt_ms: int):
        """
        Records statistics for a received PINGRESP.

        Args:
            rtt_ms: Round-trip time in milliseconds for the PINGREQ/PINGRESP.
        """
        self.ping_received_count += 1
        if len(self.ping_rtt_ms_list) >= self.max_list_size:
            self.ping_rtt_ms_list.pop(0)
        self.ping_rtt_ms_list.append(rtt_ms)

    def reset(self):
        """Resets all statistics to their initial values."""
        self.packets_sent = 0
        self.packets_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.pub_ok_count = 0
        self.pub_fail_count = 0
        self.pub_rtt_ms_list.clear()
        self.pub_package_size_list.clear()
        self.sub_package_size_list.clear()
        self.ping_rtt_ms_list.clear()
        self.connections_sent = 0
        self.connections_failed = 0
        self.ping_sent_count = 0
        self.ping_received_count = 0


    def get_stats(self) -> dict:
        """
        Calculates and returns a dictionary of aggregated statistics.

        Returns:
            A dictionary containing various statistics such as average RTT,
            packet counts, and byte counts.
        """
        pub_rtt_ms = (
            sum(self.pub_rtt_ms_list) / len(self.pub_rtt_ms_list)
            if self.pub_rtt_ms_list
            else 0
        )
        pub_package_size = (
            sum(self.pub_package_size_list) / len(self.pub_package_size_list)
            if self.pub_package_size_list
            else 0
        )
        sub_package_size = (
            sum(self.sub_package_size_list) / len(self.sub_package_size_list)
            if self.sub_package_size_list
            else 0
        )
        ping_rtt_ms = (
            sum(self.ping_rtt_ms_list) / len(self.ping_rtt_ms_list)
            if self.ping_rtt_ms_list
            else 0
        )
        return {
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "pub_ok_count": self.pub_ok_count,
            "pub_fail_count": self.pub_fail_count,
            "pub_rtt_ms": int(pub_rtt_ms),
            "pub_package_avg_size": int(pub_package_size),
            "sub_package_avg_size": int(sub_package_size),
            "connections_sent": self.connections_sent,
            "connections_failed": self.connections_failed,
            "ping_sent_count": self.ping_sent_count,
            "ping_received_count": self.ping_received_count,
            "ping_rtt_ms": int(ping_rtt_ms),
        }


class MQTTProtocol:
    """
    Handles the MQTT protocol logic, including packet creation and parsing.

    This class is responsible for the low-level details of the MQTT protocol,
    such as constructing MQTT packets (CONNECT, PUBLISH, SUBSCRIBE, etc.)
    and parsing incoming packets from the broker.

    Attributes:
        client (MQTTClient): The MQTTClient instance this protocol handler serves.
        verbose (int): Verbosity level for logging.
        pid (int): Current packet identifier, incremented for each new packet.
        _last_error_code (Optional[int]): The last CONNACK error code received.
        timeout_sec (int): Default timeout for network operations in seconds.
        stream (Optional[StreamConnection]): The network stream connection to the broker.
        _pending_pubacks (dict[int, tuple]): Stores information about QoS 1 publish
                                            messages awaiting PUBACK.
        _ack_timeout_sec (int): Timeout in seconds for waiting for PUBACKs.
    """

    CONNECT = 0x10
    CONNACK = 0x20
    PUBLISH = 0x30
    PUBACK = 0x40
    PUBREC = 0x50
    PUBREL = 0x62
    PUBCOMP = 0x70
    SUBSCRIBE = 0x82
    SUBACK = 0x90
    UNSUBSCRIBE = 0xA2
    UNSUBACK = 0xB0
    PINGREQ = 0xC0
    PINGRESP = 0xD0
    DISCONNECT = 0xE0

    CONNACK_CODES = {
        0: "Connection accepted",
        1: "Connection refused: unacceptable protocol version",
        2: "Connection refused: identifier rejected",
        3: "Connection refused: server unavailable",
        4: "Connection refused: bad username or password",
        5: "Connection refused: not authorized",
    }

    RECONNECTABLE_ERRORS = [3]

    def __init__(self, client):
        self.client = client
        self.verbose = client.verbose
        self.pid = 0
        self._last_error_code = None
        self.timeout_sec = 10
        self.stream: StreamConnection = None
        self._pending_pubacks = {}
        self._ack_timeout_sec = 5  # seconds
        # self._retry_task = asyncio.create_task(self._retry_pubacks_loop()) # TODO: Re-evaluate retry task

    async def connect(
        self,
        server: str,
        port: int,
        client_id: str,
        user: str | None,
        password: str | None,
        keepalive: int,
        ssl: bool = False,
        ssl_params: dict | None = None,
        timeout_sec: int = 10,
        clean_session: bool = True,
        will_topic: str | None = None,
        will_message: bytes | str | None = None,
        will_qos: int = 0,
        will_retain: bool = False,
    ) -> dict | bool:
        """
        Establishes a connection to the MQTT broker.

        Args:
            server: The MQTT broker hostname or IP address.
            port: The MQTT broker port.
            client_id: The client identifier.
            user: The username for authentication (optional).
            password: The password for authentication (optional).
            keepalive: The keep-alive interval in seconds.
            ssl: True to use SSL/TLS, False otherwise.
            ssl_params: SSL parameters (implementation-specific, optional).
            timeout_sec: Connection timeout in seconds.
            clean_session: If True, the broker discards previous session information.
            will_topic: The topic for the "last will and testament" message (optional).
            will_message: The payload for the "last will" message (optional).
            will_qos: The QoS level for the "last will" message.
            will_retain: If True, the "last will" message is retained.

        Returns:
            A dictionary with 'success': True and 'session_present': bool on success,
            False otherwise.

        Raises:
            Exception: If any error occurs during connection.
        """
        self.timeout_sec = timeout_sec
        try:
            self.stream = await StreamConnection.open(
                server,
                port,
                ssl=ssl,
                timeout=timeout_sec,
                is_micropython=_IS_MICROPYTHON,
                debug=self.verbose == 2,
            )

            packet = self._build_connect_packet(
                client_id,
                user,
                password,
                keepalive,
                clean_session,
                will_topic,
                will_message,
                will_qos,
                will_retain,
            )
            await self._send_packet(self.CONNECT, packet)

            resp = await asyncio.wait_for(self._read_packet(), timeout=5)
            if not resp or resp[0] != self.CONNACK:
                raise Exception(f"Expected CONNACK but received: {resp}")

            session_present = bool(resp[1][0] & 0x01)
            return_code = resp[1][1] if len(resp[1]) > 1 else 0
            self._last_error_code = return_code if return_code != 0 else None

            if return_code != 0:
                msg = self.CONNACK_CODES.get(
                    return_code, f"Unknown error: {return_code}"
                )
                log(f"CONNACK error: {msg} (code {return_code})")
                return False

            log(f"Connected (session_present={session_present})")
            return {"success": True, "session_present": session_present}

        except Exception as e:
            # console.print_exception(show_locals=True)
            log(f"MQTTProtocol:connect. Connection error: {e}")
            if self.stream:
                await self.stream.close()
            raise

    async def disconnect(self):
        """Sends a DISCONNECT packet and closes the network stream."""
        if self.stream and self.stream.writer: # Ensure stream is valid before use
            try:
                await self._send_packet(self.DISCONNECT, b"")
            except Exception as e:
                log(f"MQTTProtocol:disconnect error sending packet: {e}")
            finally:
                await self.stream.close()
        elif self.stream: # Stream might exist but writer is None if connection failed early
            await self.stream.close()


    async def publish(
        self, topic: str, message: bytes | str, qos: int = 0, retain: bool = False, pid: int | None = None
    ) -> bool:
        """
        Constructs and sends a PUBLISH packet.

        Args:
            topic (str): The MQTT topic to publish to.
            message (Union[str, bytes]): The message payload.
            qos (int): Quality of Service level (0 or 1). Defaults to 0.
            retain (bool): Whether the message should be retained by the broker.
            pid (int, optional): Packet ID to use for the message. If None, a new ID is generated.

        Returns:
            bool: True if the message was acknowledged (for QoS 1) or sent (QoS 0),
                  False if the PUBACK was not received in time (QoS 1 only).
        """
        packet = bytearray()
        packet.extend(self._encode_string(topic))

        if qos > 0:
            pid = pid or self._get_packet_id()
            packet.extend(struct.pack("!H", pid))
            self._pending_pubacks[pid] = (
                ticks_ms(),
                topic,
                message,
                qos,
                retain,
                False,  # not duplicate on first send
            )
        else:
            pid = 0
        packet.extend(message)

        flags = qos << 1
        if retain:
            flags |= 1

        await self._send_packet(self.PUBLISH | flags, packet)

        if qos == 1:  # Wait for PUBACK manually
            start = ticks_ms()
            while True:
                await asyncio.sleep(0.1)
                if pid not in self._pending_pubacks:
                    return True
                if ticks_diff(ticks_ms(), start) > self._ack_timeout_sec * 1000:
                    log(f"Timeout waiting for PUBACK for PID {pid}")
                    self._pending_pubacks.pop(pid, None)
                    return False
        return True

    async def subscribe(self, topic: str, qos: int = 0, timeout_sec: int = 5) -> int | None:
        """
        Constructs and sends a SUBSCRIBE packet, then waits for SUBACK.

        Args:
            topic: The topic filter to subscribe to.
            qos: The requested Quality of Service level for the subscription.
            timeout_sec: Time in seconds to wait for the SUBACK packet.

        Returns:
            The packet identifier (PID) of the SUBSCRIBE message if successful
            and acknowledged by the broker with a matching QoS, otherwise None.
            Returns None on timeout or if subscription is rejected or QoS mismatch.
        """
        packet = bytearray()
        pid = self._get_packet_id()
        packet.extend(struct.pack("!H", pid))
        packet.extend(self._encode_string(topic))
        packet.append(qos)

        await self._send_packet(self.SUBSCRIBE | 0x02, packet)

        try:
            resp = await asyncio.wait_for(self._read_packet(), timeout=timeout_sec)
        except asyncio.TimeoutError: # Use asyncio.TimeoutError for CPython
            log("SUBACK timeout")
            return None
        except TimeoutError: # MicroPython specific timeout
            log("SUBACK timeout (micropython)")
            return None


        if not resp:
            log("No response received after SUBSCRIBE")
            return None

        packet_type, payload = resp

        if packet_type != self.SUBACK:
            log(f"Expected SUBACK (0x90) but received {hex(packet_type)}")
            return None

        if len(payload) < 3: # PID (2 bytes) + QoS (1 byte)
            log(f"Invalid SUBACK packet length: {len(payload)}")
            return None

        received_pid = (payload[0] << 8) | payload[1]
        granted_qos = payload[2]

        if received_pid != pid:
            log(f"SUBACK PID mismatch: expected {pid}, got {received_pid}")
            return None

        # 0x80 indicates failure, see MQTT v3.1.1 spec 3.9.3
        if granted_qos & 0x80 or granted_qos != qos:
            log(
                f"Subscription failed or QoS mismatch: requested {qos}, granted {granted_qos:#02x}"
            )
            return None

        log(f"Subscribed to {topic} with QoS {granted_qos}")
        return pid

    async def unsubscribe(self, topic: str, timeout_sec: int = 5) -> int | None:
        """
        Constructs and sends an UNSUBSCRIBE packet, then waits for UNSUBACK.

        Args:
            topic: The topic filter to unsubscribe from.
            timeout_sec: Time in seconds to wait for the UNSUBACK packet.

        Returns:
            The packet identifier (PID) of the UNSUBSCRIBE message if acknowledged,
            otherwise None (e.g., on timeout or unexpected response).
        """
        pid = self._get_packet_id()
        packet = struct.pack("!H", pid) + self._encode_string(topic)
        await self._send_packet(self.UNSUBSCRIBE | 0x02, packet)

        try:
            resp = await asyncio.wait_for(self._read_packet(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            log(f"UNSUBACK timeout for topic {topic}")
            return None
        except TimeoutError: # MicroPython specific timeout
            log(f"UNSUBACK timeout for topic {topic} (micropython)")
            return None


        if resp and resp[0] == self.UNSUBACK:
            # Check PID match
            received_pid = struct.unpack("!H", resp[1][:2])[0] if len(resp[1]) >= 2 else None
            if received_pid == pid:
                log(f"Unsubscribed from {topic}")
                return pid
            else:
                log(f"UNSUBACK PID mismatch: expected {pid}, got {received_pid}")
                return None
        else:
            log(f"Unexpected response to UNSUBSCRIBE: {resp}")
            return None


    async def ping(self):
        """Sends a PINGREQ packet to the broker."""
        await self._send_packet(self.PINGREQ, b"")

    async def handle_packet(self) -> bool:
        """
        Reads and processes the next incoming MQTT packet from the stream.

        This method handles different packet types like PINGRESP, PUBLISH,
        PUBACK, SUBACK, and UNSUBACK. It invokes callbacks on the client
        as appropriate.

        Returns:
            True if a packet was handled successfully or no packet was immediately
            available (non-blocking), False if a connection-breaking error occurred
            or a timeout happened that suggests a dead connection.

        Raises:
            TimeoutError: If reading from the stream times out (can be caught by caller).
            Exception: For other unhandled errors during packet processing.
        """
        try:
            if not self.stream or self.stream.at_eof():
                log("handle_packet: Stream is closed or at EOF.")
                return False # Indicate connection issue

            resp = await self._read_packet() # This can raise TimeoutError
            if not resp:
                # No full packet available right now, but connection might still be fine
                await asyncio.sleep(0.05)
                return True

            packet_type, payload = resp
            self.client.last_rx = ticks_ms()

            if packet_type == self.PINGRESP:
                if self.client.on_ping:
                    elapsed = ticks_diff(ticks_ms(), self.client.last_ping) # Use ticks_diff
                    self.client.stats.ping_received(elapsed)
                    # Assuming on_ping is a coroutine, ensure it's awaited
                    ping_cb = self.client.on_ping(self.client, False, elapsed)
                    if asyncio.iscoroutine(ping_cb):
                        await ping_cb


            elif packet_type & 0xF0 == self.PUBLISH:
                qos = (packet_type & 0x06) >> 1
                retain = bool(packet_type & 0x01) # Ensure bool
                topic_len = struct.unpack("!H", payload[:2])[0]
                topic = payload[2 : 2 + topic_len].decode("utf-8") # Specify UTF-8
                offset = 2 + topic_len

                if qos > 0:
                    pid = struct.unpack("!H", payload[offset : offset + 2])[0]
                    offset += 2
                    if qos == 1:
                        await self._send_packet(self.PUBACK, struct.pack("!H", pid))
                    # QoS 2 (PUBREC/PUBREL/PUBCOMP) is not fully supported here

                msg_payload = payload[offset:]

                # Callbacks
                # 1. Specific subscription callback
                sub_details = self.client.subscriptions.get(topic)
                if sub_details and isinstance(sub_details, dict):
                    cb = sub_details.get("callback")
                    if cb:
                        # Check if callback is a coroutine
                        if asyncio.iscoroutinefunction(cb):
                            await cb(topic, msg_payload, retain)
                        else:
                            cb(topic, msg_payload, retain)


                # 2. Generic on_message callback
                if self.client.on_message:
                    self.client.stats.receive(len(msg_payload))
                    # Assuming on_message is a coroutine
                    on_msg_cb = self.client.on_message(self.client, topic, msg_payload, retain)
                    if asyncio.iscoroutine(on_msg_cb):
                        await on_msg_cb


            elif packet_type == self.PUBACK:
                if len(payload) >= 2:
                    pid = struct.unpack("!H", payload[:2])[0]
                    log(f"PUBACK received for PID {pid}")
                    self._pending_pubacks.pop(pid, None)
                else:
                    log("Malformed PUBACK: too short")


            elif packet_type == self.SUBACK:
                if len(payload) >= 3: # PID (2 bytes) + Result Code (1 byte)
                    pid = struct.unpack("!H", payload[:2])[0]
                    granted_qos_list = payload[2:] # Can be multiple for multi-topic subscribe
                    log(f"SUBACK received for PID {pid} with granted QoS list: {granted_qos_list}")

                    # This part needs to align with how subscriptions are stored and confirmed.
                    # Assuming single topic subscription per SUBACK for now.
                    for topic, sub_info in list(self.client.subscriptions.items()): # Iterate copy
                        if isinstance(sub_info, dict) and sub_info.get("pid") == pid:
                            if not (granted_qos_list[0] & 0x80): # Check if subscription was successful
                                sub_info["confirmed"] = True
                                sub_info["granted_qos"] = granted_qos_list[0]
                                log(f"Subscription to {topic} confirmed with QoS {granted_qos_list[0]}")
                            else:
                                log(f"Subscription to {topic} failed by broker (PID {pid})")
                                self.client.subscriptions.pop(topic, None) # Remove failed subscription
                            break # Assuming one SUBACK payload per PID
                else:
                    log("Malformed SUBACK: too short")

            elif packet_type == self.UNSUBACK:
                if len(payload) >= 2: # PID (2 bytes)
                    pid = struct.unpack("!H", payload[:2])[0]
                    log(f"UNSUBACK received for PID {pid}")
                    # Client might remove from subscriptions upon sending UNSUBSCRIBE
                    # or confirm removal here.
                    # For now, just log. If client manages this, no action needed here.
                else:
                    log("Malformed UNSUBACK: too short")


        except asyncio.TimeoutError: # CPython
            # This timeout is from _read_packet waiting for data.
            # It doesn't necessarily mean the connection is dead, could be just no incoming messages.
            # The keep-alive mechanism should handle actual dead connections.
            # log("Packet read timeout in handle_packet")
            return True # Indicate no fatal error, loop can continue
        except TimeoutError: # MicroPython
            # log("Packet read timeout in handle_packet (micropython)")
            return True

        except Exception as e:
            console.print_exception()
            log(f"Unhandled exception in handle_packet: {type(e).__name__}: {e}")
            return False # Indicate an error that might require disconnect/reconnect
        return True

    async def _read_packet(self):
        header = await self.stream.buffered_read(1)
        if not header:
                await asyncio.sleep(0.05)
                return True

            packet_type, payload = resp
            self.client.last_rx = ticks_ms()

            if packet_type == self.PINGRESP:
                if self.client.on_ping:
                    elapsed = ticks_ms() - self.client.last_ping
                    self.client.stats.ping_received(elapsed)
                    await self.client.on_ping(self, False, elapsed)

            elif packet_type & 0xF0 == self.PUBLISH:
                qos = (packet_type & 0x06) >> 1
                retain = packet_type & 0x01
                topic_len = struct.unpack("!H", payload[:2])[0]
                topic = payload[2 : 2 + topic_len].decode()
                offset = 2 + topic_len

                if qos > 0:
                    pid = struct.unpack("!H", payload[offset : offset + 2])[0]
                    offset += 2
                    if qos == 1:
                        await self._send_packet(self.PUBACK, struct.pack("!H", pid))

                msg_payload = payload[offset:]

                if topic in self.client.subscriptions:
                    cb = self.client.subscriptions[topic]
                    if isinstance(cb, dict):
                        cb = cb.get("callback")
                    if cb:
                        cb(topic, msg_payload, retain)

                if self.client.on_message:
                    self.client.stats.receive(len(msg_payload))
                    await self.client.on_message(self, topic, msg_payload, retain)

            elif packet_type == self.PUBACK:
                if len(payload) >= 2:
                    pid = struct.unpack("!H", payload[:2])[0]
                    log(f"PUBACK received for PID {pid}")
                    self._pending_pubacks.pop(pid, None)

            elif packet_type == self.SUBACK:
                if len(payload) >= 3:
                    pid = struct.unpack("!H", payload[:2])[0]
                    granted_qos = payload[2]
                    log(f"SUBACK received for PID {pid} with QoS {granted_qos}")

                    for topic, sub in self.client.subscriptions.items():
                        if isinstance(sub, dict) and sub.get("pid") == pid:
                            sub["confirmed"] = True
                            log(f"Subscription to {topic} confirmed")
                            break

            elif packet_type == self.UNSUBACK:
                if len(payload) >= 2:
                    pid = struct.unpack("!H", payload[:2])[0]
                    log(f"UNSUBACK received for PID {pid}")
                    # Aqui você pode remover do dict se quiser

        except TimeoutError:
            log("Packet read timeout")
            return False

        except Exception as e:
            console.print_exception()
            log(f"Unhandled exception in handle_packet: {e}")
            return False
        return True

    async def _read_packet(self):
        header = await self.stream.buffered_read(1)
        if not header:
            # log("No data received (header), stream might be closed by peer.")
            # This indicates a potential connection issue if it happens unexpectedly.
            # The caller (handle_packet) should decide how to react.
            return None # Propagate that no header was read

        packet_type = header[0]
        remaining_length = 0
        multiplier = 1

        # Decode remaining length (MQTT variable byte integer)
        for _ in range(4): # Max 4 bytes for remaining length
            byte_data = await self.stream.buffered_read(1)
            if not byte_data:
                # log("No data received (remaining length byte), stream might be closed.")
                return None # Connection likely closed mid-packet

            byte = byte_data[0]
            remaining_length += (byte & 0x7F) * multiplier
            if not (byte & 0x80): # Continuation bit is not set
                break
            multiplier *= 128
            if multiplier > 128 * 128 * 128: # Check for malformed length
                raise ValueError("Malformed remaining length (exceeds 4 bytes)")
        else: # Loop finished without break, means all 4 bytes had continuation bit
            raise ValueError("Malformed remaining length (too many bytes)")


        payload = b""
        if remaining_length > 0:
            payload = await self.stream.buffered_read(remaining_length)
            if len(payload) != remaining_length:
                # log(f"Failed to read full payload: expected {remaining_length}, got {len(payload)}")
                return None # Connection likely closed mid-payload

        if self.verbose == 2:
            dump_array(payload, header=f"Received packet type: {packet_type:#02x}, len: {remaining_length}")

        return packet_type, payload

    async def _send_packet(self, packet_type: int, payload: bytes):
        """
        Constructs the full MQTT packet (header + payload) and sends it.

        Args:
            packet_type: The MQTT packet type (e.g., PUBLISH, SUBSCRIBE).
            payload: The packet-specific payload.

        Raises:
            Exception: If writing to the stream fails.
        """
        if not self.stream or not self.stream.writer:
            raise ConnectionError("Cannot send packet, stream is not available.")

        remaining_length = len(payload)
        remaining_bytes = bytearray()
        while True:
            byte = remaining_length % 128
            remaining_length //= 128
            if remaining_length > 0:
                byte |= 0x80  # Set continuation bit
            remaining_bytes.append(byte)
            if remaining_length == 0:
                break

        packet = bytearray([packet_type]) + remaining_bytes + payload

        if self.verbose == 2:
            dump_array(packet, header=f"Sending packet type: {packet_type:#02x}, len: {len(payload)}")

        await self.stream.write(packet, timeout=self.timeout_sec)

    def _build_connect_packet(
        self,
        client_id: str,
        user: str | None,
        password: str | None,
        keepalive: int,
        clean_session: bool,
        will_topic: str | None,
        will_message: bytes | str | None,
        will_qos: int,
        will_retain: bool,
    ) -> bytes:
        """
        Builds the MQTT CONNECT packet.

        Returns:
            The constructed CONNECT packet as bytes.
        """
        packet = bytearray()
        # Protocol Name and Level
        packet.extend(self._encode_string("MQTT"))  # Protocol name
        packet.append(4)  # Protocol level 4 (MQTT v3.1.1)

        # Connect Flags
        flags = 0
        if clean_session:
            flags |= 0x02
        if user:
            flags |= 0x80
        if password:  # Password flag is only set if username is also present
            flags |= 0x40
        if will_topic and will_message is not None: # will_message can be empty string
            flags |= 0x04  # Will Flag
            flags |= will_qos << 3
            if will_retain:
                flags |= 0x20 # Will Retain Flag (bit 5)

        packet.append(flags)
        packet.extend(struct.pack("!H", keepalive))  # Keep Alive

        # Payload
        packet.extend(self._encode_string(client_id))
        if will_topic and will_message is not None:
            packet.extend(self._encode_string(will_topic))
            # Ensure will_message is bytes
            if isinstance(will_message, str):
                will_message = will_message.encode('utf-8')
            packet.extend(self._encode_string(will_message)) # Length-prefixed
        if user:
            packet.extend(self._encode_string(user))
        if password: # Only include password if username is present
            packet.extend(self._encode_string(password))
        return bytes(packet)

    def _encode_string(self, s: str | bytes) -> bytes:
        """
        Encodes a string or bytes into the MQTT length-prefixed format.

        Args:
            s: The string or bytes to encode.

        Returns:
            The encoded string/bytes with a 2-byte length prefix.
        """
        if isinstance(s, str):
            s = s.encode("utf-8") # Ensure UTF-8 encoding for strings
        return struct.pack("!H", len(s)) + s

    def _get_packet_id(self) -> int:
        """
        Generates and returns a new unique packet identifier.

        Packet IDs are 16-bit unsigned integers. This method ensures they are
        unique for inflight messages and wraps around. PID 0 is invalid.

        Returns:
            A unique packet identifier (1-65535).
        """
        self.pid = (self.pid % 65535) + 1 # Cycle through 1-65535
        # log(f"Generated new packet ID: {self.pid}")
        return self.pid

    def get_error_message(self, error_code: int | None) -> str | None:
        """
        Gets a human-readable error message for a given CONNACK error code.

        Args:
            error_code: The MQTT CONNACK error code.

        Returns:
            A string describing the error, or None if error_code is None.
        """
        if error_code is None:
            return None
        return self.CONNACK_CODES.get(error_code, f"Unknown error code: {error_code}")


    async def close(self):
        """Closes the underlying network stream if it's open."""
        if self.stream:
            await self.stream.close()
            self.stream = None

    async def _retry_pubacks_loop(self):
        """
        Periodically retries sending QoS 1 PUBLISH messages that haven't received a PUBACK.
        Note: This loop is currently not started by default.
        """
        RETRY_INTERVAL_MS = 2_000  # Milliseconds
        while True:
            await asyncio.sleep(RETRY_INTERVAL_MS / 1000) # asyncio.sleep takes seconds
            now = ticks_ms()
            for pid, (ts, topic, message, qos, retain, _) in list( # Use _ for dup flag as it's reset
                self._pending_pubacks.items()
            ):
                if ticks_diff(now, ts) > RETRY_INTERVAL_MS:
                    log(f"Retrying QoS 1 message PID {pid} (dup=True)")
                    try:
                        # Resend with DUP flag set to True
                        await self._resend_qos1(
                            pid, topic, message, qos, retain, dup=True
                        )
                        # Update timestamp for the resent message
                        self._pending_pubacks[pid] = (
                            ticks_ms(),
                            topic,
                            message,
                            qos,
                            retain,
                            True, # Mark as duplicate
                        )
                    except Exception as e:
                        log(f"Retry failed for PID {pid}: {e}")
                        # Optionally, implement a max retry count and remove from pending_pubacks

    async def _resend_qos1(
        self, pid: int, topic: str, message: bytes, qos: int, retain: bool, dup: bool = False
    ):
        """
        Resends a QoS 1 PUBLISH packet.

        Args:
            pid: The original packet identifier.
            topic: The MQTT topic.
            message: The message payload.
            qos: Quality of Service level (should be 1).
            retain: Retain flag.
            dup: DUP (duplicate) flag.
        """
        packet = bytearray()
        packet.extend(self._encode_string(topic))
        packet.extend(struct.pack("!H", pid)) # Use original PID
        packet.extend(message)

        flags = qos << 1
        if retain:
            flags |= 0x01 # Retain bit
        if dup:
            flags |= 0x08  # DUP flag (bit 3)

        await self._send_packet(self.PUBLISH | flags, packet)


class MQTTClient:
    """
    An asynchronous MQTT client.

    This client handles connecting to an MQTT broker, publishing messages,
    subscribing to topics, and managing the MQTT session including keep-alives
    and basic reconnection logic.

    Attributes:
        client_id (str): The client ID for the MQTT connection.
        server (str): The MQTT broker hostname or IP address.
        port (int): The MQTT broker port.
        user (Optional[str]): Username for MQTT authentication.
        password (Optional[str]): Password for MQTT authentication.
        keepalive (int): Keep-alive interval in seconds.
        ssl (bool): True to use SSL/TLS, False otherwise.
        ssl_params (dict): SSL parameters (platform-specific).
        verbose (int): Verbosity level for logging (0: off, 1: info, 2: debug).
        connected (bool): True if the client is currently connected to the broker.
        subscriptions (dict): Stores current subscriptions (topic -> details).
        last_ping (int): Timestamp of the last PINGREQ sent (via `ticks_ms`).
        last_rx (int): Timestamp of the last packet received (via `ticks_ms`).
        _last_error_code (Optional[int]): The last CONNACK error code from the broker.
        reconnect_interval (int): Initial interval in seconds for reconnection attempts.
                                  Set to 0 to disable automatic reconnection.
        max_reconnect_interval (int): Maximum interval in seconds for reconnection.
        reconnect_attempt (int): Current number of reconnection attempts.
        on_connect (Optional[Callable]): Async callback triggered on successful connection.
                                         Signature: `async def on_connect(client, rc)`
        on_disconnect (Optional[Callable]): Async callback triggered on disconnection.
                                            Signature: `async def on_disconnect(client, rc)`
        on_message (Optional[Callable]): Async callback triggered when a message is received.
                                         Signature: `async def on_message(client, topic, payload, retain)`
        on_ping (Optional[Callable]): Async callback triggered when a PINGREQ is sent or PINGRESP is received.
                                      Signature: `async def on_ping(client, is_request, rtt_ms)`
        stats (MqttStats): Object for tracking MQTT statistics.
        protocol (MQTTProtocol): The MQTT protocol handler instance.
        clean_session (bool): MQTT clean session flag.
        will_topic (Optional[str]): Last will and testament topic.
        will_message (Optional[Union[str, bytes]]): Last will and testament message.
        will_qos (int): QoS for the last will message.
        will_retain (bool): Retain flag for the last will message.
    """
    def __init__(
        self,
        client_id: str | None = None,
        server=None,
        port=1883,
        user=None,
        password=None,
        keepalive=60,
        ssl=False,
        ssl_params=None,
        verbose: int = 0,
        stats: MqttStats = None,
        clean_session: bool = True,
        will_topic=None,
        will_message=None,
        server: str | None = None,
        port: int = 1883,
        user: str | None = None,
        password: str | None = None,
        keepalive: int = 60,
        ssl: bool = False,
        ssl_params: dict | None = None,
        verbose: int = 0,
        stats: MqttStats | None = None,
        clean_session: bool = True,
        will_topic: str | None = None,
        will_message: str | bytes | None = None,
        will_qos: int = 0,
        will_retain: bool = False,
    ):
        """
        Initializes the MQTTClient.

        Args:
            client_id: The client ID. If None or too short, one is generated.
            server: The MQTT broker address.
            port: The MQTT broker port.
            user: Username for authentication.
            password: Password for authentication.
            keepalive: Keep-alive interval in seconds.
            ssl: True to use SSL/TLS.
            ssl_params: SSL parameters (platform-specific).
            verbose: Logging verbosity (0: off, 1: info, 2: debug with packet dumps).
            stats: An MqttStats instance for collecting statistics.
            clean_session: MQTT clean session flag.
            will_topic: Last will topic.
            will_message: Last will message.
            will_qos: QoS for the last will message.
            will_retain: Retain flag for the last will message.
        """
        self.client_id = (
            client_id if client_id and len(client_id) >= 2 else generate_client_id()
        )
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.keepalive = keepalive
        self.ssl = ssl
        self.ssl_params = ssl_params or {}
        self.verbose = verbose

        self.connected = False
        self.subscriptions = {} # Stores topic -> {"pid": int, "qos": int, "confirmed": bool, "callback": Callable}
        self.last_ping = 0
        self.last_rx = 0
        self._last_error_code = None # Stores the CONNACK return code on failure

        # Reconnection parameters
        self.reconnect_interval = 0  # Base interval in seconds, 0 to disable
        self.max_reconnect_interval = 0 # Max interval in seconds
        self.reconnect_attempt = 0

        # Callbacks
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.on_ping = None # Called for PINGREQ sent and PINGRESP received

        self._ping_task = None
        self._receive_task = None
        self.stats: MqttStats = stats or MqttStats()
        self.protocol = MQTTProtocol(self) # Pass self to MQTTProtocol
        self.clean_session = clean_session
        self.will_topic = will_topic
        self.will_message = will_message
        self.will_qos = will_qos
        self.will_retain = will_retain

    def __repr__(self) -> str:
        """Returns a string representation of the MQTTClient."""
        return f"MQTTClient(client_id='{self.client_id}', server='{self.server}', port={self.port})"

    async def connect(self, timeout_sec: int = 10) -> bool:
        """
        Connects to the MQTT broker.

        This method establishes the network connection, sends the MQTT CONNECT packet,
        and waits for a CONNACK. If successful, it starts background tasks for
        handling incoming messages and keep-alives.

        Args:
            timeout_sec: Timeout in seconds for the connection attempt.

        Returns:
            True if the connection was successful, False otherwise.
        """
        if self.connected:
            return True
        if not self.server:
            log("MQTTClient:connect error - server address not set.")
            return False

        try:
            log(f"MQTTClient:connect. Connecting to {self.server}:{self.port}")
            self.stats.connect()
            connect_result = await asyncio.wait_for(
                self.protocol.connect(
                    self.server,
                    self.port,
                    self.client_id,
                    self.user,
                    self.password,
                    self.keepalive,
                    self.ssl,
                    self.ssl_params,
                    timeout_sec, # Pass timeout to protocol.connect
                    self.clean_session,
                    self.will_topic,
                    self.will_message,
                    self.will_qos,
                    self.will_retain,
                ),
                timeout=timeout_sec + 1, # Outer timeout slightly larger
            )


            if not isinstance(connect_result, dict) or not connect_result.get("success"):
                self.stats.connect_fail()
                self._last_error_code = self.protocol._last_error_code # Store error from protocol
                log(f"MQTTClient:connect failed. Error: {self.get_last_error()}")
                await self.protocol.close() # Ensure stream is closed
                return False

            self.connected = True
            self.reconnect_attempt = 0 # Reset on successful connection
            self.last_rx = ticks_ms()
            self.last_ping = ticks_ms() # Initialize last_ping time

            # Start background tasks
            self._receive_task = asyncio.create_task(self._receive_loop())
            if self.keepalive > 0:
                self._ping_task = asyncio.create_task(self._keep_alive())

            if self.on_connect:
                # CONNACK code 0 means success
                cb = self.on_connect(self, 0) # Pass self and return code 0
                if asyncio.iscoroutine(cb): await cb


            # Resubscribe to topics if it was a reconnect and not a clean session
            if not self.clean_session and connect_result.get("session_present"):
                log("Re-subscribing to topics after reconnect with session_present.")
                for topic, sub_details in self.subscriptions.items():
                    if isinstance(sub_details, dict) and not sub_details.get("confirmed"):
                        await self.subscribe(topic, sub_details.get("qos", 0), sub_details.get("callback"))


            return True

        except asyncio.TimeoutError:
            log(f"MQTTClient:connect timeout connecting to {self.server}:{self.port}")
            self.stats.connect_fail()
            await self.protocol.close() # Ensure stream is closed on timeout
            # Do not call handle_disconnect here, let _reconnect logic handle it if configured
        except Exception as e:
            # console.print_exception(show_locals=True)
            log(f"MQTTClient:connect failed: {type(e).__name__}: {e}")
            self.stats.connect_fail()
            await self.protocol.close() # Ensure stream is closed on other exceptions
            # Do not call handle_disconnect here
        return False


    async def disconnect(self):
        """
        Disconnects from the MQTT broker.

        Sends a DISCONNECT packet and closes the network connection.
        Also cancels background tasks.
        """
        if self.connected:
            log("MQTTClient:disconnect. Disconnecting...")
            self.connected = False # Mark as disconnected immediately
            try:
                if self.protocol and self.protocol.stream: # Check if protocol and stream exist
                    await self.protocol.disconnect()
            except Exception as e:
                log(f"MQTTClient:disconnect error during protocol.disconnect: {e}")
            finally:
                # Call handle_disconnect with a specific code (e.g., 0 for graceful)
                # or None if it's a client-initiated disconnect not due to an error.
                # Using a local variable for return_code as it's client initiated.
                await self.handle_disconnect(return_code=None) # Client initiated, no error code from broker
        else:
            log("MQTTClient:disconnect. Already disconnected.")


    async def publish(
        self, topic: str, message: str | bytes, qos: int = 0, retain: bool = False
    ) -> bool | None:
        """
        Publishes a message to a given topic.

        Args:
            topic: The MQTT topic to publish to.
            message: The message payload (string or bytes).
            qos: Quality of Service level (0, 1). QoS 2 is not supported.
            retain: If True, the message is retained by the broker.

        Returns:
            True if the message was successfully sent (for QoS 0) or acknowledged
            (for QoS 1). False if PUBACK was not received in time for QoS 1.
            None if the client is not connected and cannot connect, or if an
            unexpected error occurs.
        """
        if not self.connected:
            log("MQTTClient:publish - Not connected. Attempting to connect...")
            if not await self.connect(): # Try to connect first
                log("MQTTClient:publish - Connection attempt failed. Publish skipped.")
                return None # Indicate failure to publish due to connection

        if isinstance(message, str):
            message = message.encode("utf-8") # Ensure bytes with UTF-8

        try:
            start_time = ticks_ms()
            # The protocol.publish method now directly returns True/False for QoS 1
            # or True for QoS 0 if sent.
            success = await self.protocol.publish(topic, message, qos, retain)
            rtt = ticks_diff(ticks_ms(), start_time)

            if qos > 0: # Only update stats if QoS > 0 where success means ACK
                self.stats.publish(success, rtt, len(message))
                if not success:
                    log(f"Publish failed for topic '{topic}' (QoS {qos}). No PUBACK or error.")
            else: # For QoS 0, success means sent
                self.stats.publish(True, rtt, len(message)) # RTT is just send time for QoS 0

            return success
        except Exception as e:
            # console.print_exception(show_locals=True)
            log(f"MQTTClient:publish error for topic '{topic}': {type(e).__name__}: {e}")
            # An exception during publish often means a connection issue.
            await self.handle_disconnect() # Trigger disconnect handling
            return None # Indicate failure

    async def subscribe(
        self, topic: str, qos: int = 0, callback: callable | None = None
    ) -> bool:
        """
        Subscribes to a topic.

        Args:
            topic: The topic filter to subscribe to.
            qos: The requested Quality of Service level.
            callback: Optional callback to be invoked when a message arrives on this topic.
                      Signature: `def callback(topic, payload, retain)` or
                                 `async def callback(topic, payload, retain)`

        Returns:
            True if the subscribe request was successfully sent and acknowledged (SUBACK)
            with a matching QoS, False otherwise.
        """
        if not self.connected:
            log("MQTTClient:subscribe - Not connected. Attempting to connect...")
            if not await self.connect():
                log("MQTTClient:subscribe - Connection attempt failed. Subscription skipped.")
                return False

        # Store subscription intent. Confirmation happens in handle_packet upon SUBACK.
        # The MQTTProtocol.subscribe method will handle sending the packet and awaiting SUBACK.
        pid = await self.protocol.subscribe(topic, qos)

        if pid is not None:
            # If protocol.subscribe returns a PID, it means SUBACK was received and valid
            # (matching PID, and granted QoS is not failure code 0x80).
            # The actual granted QoS is checked inside protocol.subscribe.
            # We update the local subscription list here.
            self.subscriptions[topic] = {
                "pid": pid,
                "qos": qos, # Store requested QoS; granted QoS is handled by protocol if needed
                "confirmed": True, # Mark as confirmed since protocol.subscribe succeeded
                "callback": callback,
            }
            log(f"Successfully subscribed to topic '{topic}' with QoS {qos}.")
            return True
        else:
            # protocol.subscribe returned None, meaning SUBACK timeout or failure
            log(f"Failed to subscribe to topic '{topic}' (SUBACK error or timeout).")
            self.subscriptions.pop(topic, None) # Clean up if it was added optimistically
            return False


    async def unsubscribe(self, topic: str) -> bool:
        """
        Unsubscribes from a topic.

        Args:
            topic: The topic filter to unsubscribe from.

        Returns:
            True if the unsubscribe request was successfully sent and acknowledged (UNSUBACK),
            False otherwise.
        """
        if not self.connected:
            # Unlike subscribe, usually can't unsubscribe if not connected,
            # as the broker wouldn't know about the client.
            # However, some brokers might allow it if session is persisted.
            # For simplicity, require connection.
            log("MQTTClient:unsubscribe - Not connected. Unsubscription skipped.")
            return False


        # The MQTTProtocol.unsubscribe method will handle sending and awaiting UNSUBACK.
        pid = await self.protocol.unsubscribe(topic)

        if pid is not None:
            # UNSUBACK received and PID matched
            self.subscriptions.pop(topic, None) # Remove from local list
            log(f"Successfully unsubscribed from topic '{topic}'.")
            return True
        else:
            log(f"Failed to unsubscribe from topic '{topic}' (UNSUBACK error or timeout).")
            return False


    def get_last_error(self) -> str | None:
        """
        Gets a human-readable message for the last connection error.

        Returns:
            A string describing the last CONNACK error, or None if no error
            or not applicable.
        """
        return self.protocol.get_error_message(self._last_error_code)

    async def _keep_alive(self):
        """Background task to send PINGREQ packets at regular intervals."""
        log("MQTTClient: Starting keep-alive loop.")
        ping_interval_s = self.keepalive / 2.0
        if ping_interval_s <= 0:
            log("MQTTClient: Keep-alive disabled (interval <= 0).")
            return

        while self.connected:
            await asyncio.sleep(ping_interval_s) # Wait first
            now = ticks_ms()
            # Check if it's time to send a ping
            # No need for `elapsed = ticks_diff(now, self.last_ping)` check here,
            # as sleep(ping_interval_s) determines the schedule.

            if self.connected: # Re-check connected status after sleep
                try:
                    if self.verbose: log(f"MQTTClient: Sending PINGREQ (Keepalive: {self.keepalive}s)")
                    await self.protocol.ping()
                    self.last_ping = now # Record time of sending PINGREQ
                    self.stats.ping_sent()
                    if self.on_ping:
                        cb = self.on_ping(self, True, 0) # is_request=True, rtt=0 for request
                        if asyncio.iscoroutine(cb): await cb
                except Exception as e:
                    # console.print_exception(show_locals=True)
                    log(f"MQTTClient: Ping error: {type(e).__name__}: {e}. Disconnecting.")
                    # Don't call self.disconnect() from here as it might lead to recursion
                    # if disconnect itself tries to cancel this task.
                    # Instead, trigger handle_disconnect.
                    await self.handle_disconnect() # Pass no rc, error is local
                    break # Exit keep-alive loop

            # Check for server timeout (no messages received for too long)
            # This should be longer than keepalive to allow for PINGRESP
            server_timeout_s = self.keepalive * 1.5
            if ticks_diff(now, self.last_rx) > server_timeout_s * 1000:
                log(f"MQTTClient: Server timeout (no packet received for > {server_timeout_s}s). Disconnecting.")
                await self.handle_disconnect() # No specific broker error code
                break # Exit keep-alive loop

        log("MQTTClient: Keep-alive loop stopped.")


    def mark_disconnected(self):
        """
        Marks the client as disconnected.
        This is typically called internally when a connection loss is detected.
        """
        if self.connected:
            log("MQTTClient: Marking as disconnected.")
            self.connected = False


    async def _receive_loop(self):
        """Background task to continuously read and handle incoming MQTT packets."""
        log("MQTTClient: Starting receive loop.")
        while self.connected:
            try:
                if not self.protocol or not self.protocol.stream or self.protocol.stream.at_eof():
                    log("MQTTClient:_receive_loop - Stream not available or EOF. Disconnecting.")
                    await self.handle_disconnect()
                    break

                # protocol.handle_packet() should return False on critical error, True otherwise.
                # It can raise TimeoutError if configured, but we expect it to handle its own timeouts
                # for packet parts and return True if it's just waiting for more data.
                ok = await self.protocol.handle_packet()
                if not ok:
                    log("MQTTClient:_receive_loop - protocol.handle_packet indicated error. Disconnecting.")
                    await self.handle_disconnect() # Error from broker or stream
                    break
                # Add a small sleep if handle_packet is very busy and returns True quickly
                # This prevents tight loops if no data is immediately available but connection is fine.
                # However, if handle_packet uses buffered_read with timeouts, this might not be needed.
                # For now, rely on blocking reads or internal sleeps in handle_packet/stream.
                # await asyncio.sleep(0.01) # Small yield
            except asyncio.TimeoutError: # Should be handled by protocol.handle_packet ideally
                # This might occur if _read_packet has a very short timeout not handled internally.
                # Generally, keep-alive should detect dead connections.
                if not self.connected: # If already marked disconnected, just exit
                    break
                # log("MQTTClient:_receive_loop - Timeout in handle_packet. Checking connection.")
                # No action needed here, keep_alive loop will handle dead connection.
                await asyncio.sleep(0.1) # Brief pause before next attempt
            except ConnectionError as e: # Specific connection errors
                log(f"MQTTClient:_receive_loop - ConnectionError: {e}. Disconnecting.")
                await self.handle_disconnect()
                break
            except Exception as e:
                # console.print_exception(show_locals=True)
                log(f"MQTTClient:_receive_loop - Unhandled error: {type(e).__name__}: {e}. Disconnecting.")
                await self.handle_disconnect() # Generic error
                break
        log("MQTTClient: Receive loop stopped.")


    async def handle_disconnect(self, return_code: int | None = None):
        """
        Handles the disconnection logic.

        This method is called when the client disconnects, either intentionally
        or due to an error. It cleans up resources, cancels tasks, and invokes
        the `on_disconnect` callback. It may also trigger reconnection logic.

        Args:
            return_code: The MQTT CONNACK return code if disconnection was due to
                         a broker error, or a client-specific code. None if it's
                         a clean client-initiated disconnect or unknown error.
        """
        if not self.connected and not self._ping_task and not self._receive_task:
            # Already handled or was never fully connected
            # log("handle_disconnect: Already fully disconnected or tasks cleaned up.")
            return

        was_connected = self.connected
        self.connected = False # Ensure marked as disconnected

        if return_code is not None:
            self._last_error_code = return_code

        # Cancel background tasks
        if self._ping_task:
            if not self._ping_task.done(): self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass # Expected
            except Exception as e:
                log(f"MQTTClient: Error during ping_task cancellation: {e}")
            self._ping_task = None

        if self._receive_task:
            if not self._receive_task.done(): self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass # Expected
            except Exception as e:
                log(f"MQTTClient: Error during receive_task cancellation: {e}")
            self._receive_task = None

        # Close the protocol's stream connection
        if self.protocol:
            await self.protocol.close() # Ensures stream is closed

        # Mark all non-confirmed subscriptions as not confirmed
        for topic in self.subscriptions:
            if isinstance(self.subscriptions[topic], dict):
                self.subscriptions[topic]['confirmed'] = False


        if was_connected and self.on_disconnect:
            try:
                cb = self.on_disconnect(self, return_code) # Pass self and return code
                if asyncio.iscoroutine(cb): await cb
            except Exception as e:
                log(f"MQTTClient: Error in on_disconnect callback: {e}")

        if return_code is not None:
            log(f"MQTTClient: Disconnected. Reason: {self.get_last_error()} (Code: {return_code})")
        else:
            log("MQTTClient: Disconnected.")


        # Reconnection logic
        # Only try to reconnect if it was previously connected, or if a specific
        # reconnectable error occurred (handled by RECONNECTABLE_ERRORS in protocol)
        # and reconnection is enabled.
        should_reconnect = (was_connected or \
                           (return_code and return_code in self.protocol.RECONNECTABLE_ERRORS)) and \
                           self.reconnect_interval > 0 and self.max_reconnect_interval > 0

        if should_reconnect:
            # This creates a new task that will attempt reconnection after a delay.
            # It doesn't block handle_disconnect.
            asyncio.create_task(self._reconnect())


    async def _reconnect(self):
        """
        Manages the reconnection process with exponential backoff.
        This is run as a separate task.
        """
        if self.connected: # Should not happen if called from handle_disconnect
            return

        self.reconnect_attempt += 1
        base_delay = self.reconnect_interval
        max_delay = self.max_reconnect_interval
        # Exponential backoff with jitter: delay * (2^attempt)
        # Cap at max_delay. Add random jitter to prevent thundering herd.
        delay = min(base_delay * (2 ** (self.reconnect_attempt -1)), max_delay)
        jitter = random.uniform(0, delay * 0.1) # Add up to 10% jitter
        actual_delay = delay + jitter

        log(f"MQTTClient: Attempting reconnect {self.reconnect_attempt} in {actual_delay:.2f}s...")
        await asyncio.sleep(actual_delay)

        if not self.connected: # Check again, another process might have reconnected
            log(f"MQTTClient: Reconnecting now (attempt {self.reconnect_attempt})...")
            # The connect method itself will reset reconnect_attempt on success
            if await self.connect():
                log("MQTTClient: Reconnect successful.")
                # reconnect_attempt is reset in connect()
            else:
                log("MQTTClient: Reconnect attempt failed.")
                # If connect fails, and it triggers handle_disconnect,
                # handle_disconnect might schedule another _reconnect.
                # This is okay, as reconnect_attempt will keep increasing.
                # Consider adding a max_reconnect_attempts if desired.
                if self.reconnect_interval > 0 and self.max_reconnect_interval > 0:
                    # If connect() itself doesn't trigger another _reconnect (e.g. if it fails early)
                    # we might want to schedule it here. However, connect() failing should ideally
                    # go through handle_disconnect which would then call _reconnect.
                    # To be safe, if still not connected, and auto-reconnect is on,
                    # schedule another attempt if handle_disconnect wasn't called by connect().
                    # This is a bit complex; simpler if connect() always calls handle_disconnect on failure.
                    # Assuming connect() calls handle_disconnect which calls _reconnect.
                    pass
