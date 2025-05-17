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

__version__ = "1.0.2"

# Determine if running on MicroPython
_IS_MICROPYTHON = sys.implementation.name == "micropython"
_IS_ESP32 = sys.platform == "esp32" if _IS_MICROPYTHON else False

# Import platform-specific modules conditionally
if _IS_MICROPYTHON:
    try:
        from micropython import const
        from machine import RTC as hal_rtc
    except ImportError:
        # Fallback for platforms that don't support const
        def const(x):
            return x


        def hal_rtc():
            return None

    from time import ticks_ms, ticks_diff, ticks_add, gmtime

else:
    from time import monotonic, gmtime


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
    def __init__(self):
        pass

    def init(self, date_parts):
        if _IS_MICROPYTHON:
            rtc = hal_rtc()
            rtc.init(date_parts)

    def datetime(self):
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

    def utc_now(self):
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

    def __str__(self):
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            self.year, self.month, self.day, self.hour, self.minute, self.second
        )


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
        line = " ".join("{:02x}".format(c) for c in data[i: i + 16])
        log("{:04d}: {}".format(i, line))


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
        chars = data[c: c + length]
        hex_string = " ".join("%0*x" % (digits, x) for x in chars)
        printable = "".join(f"{(x <= 127 and print_table[x]) or '.'}" for x in chars)
        lines.append("%04d  %-*s  %s\n" % (c, length * 3, hex_string, printable))
    log(f"{s}\n{''.join(lines)}")


def generate_client_id():
    rnd = random.getrandbits(32)
    return f"esp32_{binascii.hexlify(rnd.to_bytes(4, 'big')).decode()}"


class StreamConnection:
    MP = 1
    CPYTHON = 2

    def __init__(self, reader, writer, is_micropython, debug=False):
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
            host,
            port,
            ssl=False,
            timeout=None,
            is_micropython: bool = False,
            debug=False,
    ):
        self = cls(None, None, is_micropython, debug)
        self._host = host
        self._port = port
        self._ssl = ssl
        self._timeout = timeout
        await self._connect()
        return self

    async def _connect(self):
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

    async def reconnect(self, delay=1):
        await self.close()
        if self._debug:
            print(f"Reconnecting in {delay}s...")
        await asyncio.sleep(delay)
        await self._connect()

    async def write(self, data: bytes, timeout=None, retries=0):
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

    async def read(self, n=-1):
        async with self._read_lock:
            if self._eof:
                return b""
            data = await self.reader.read(n)
            if data == b"":
                self._eof = True
            return data

    async def readline(self):
        if self._eof:
            return b""
        line = await self.reader.readline()
        if line == b"":
            self._eof = True
        return line

    async def read_until(self, delimiter: bytes, max_bytes=1024):
        """Read until delimiter or max_bytes is reached."""
        while delimiter not in self._buffer and len(self._buffer) < max_bytes:
            chunk = await self.read(64)
            if not chunk:
                break
            self._buffer.extend(chunk)

        idx = self._buffer.find(delimiter)
        if idx >= 0:
            result = self._buffer[: idx + len(delimiter)]
            self._buffer = self._buffer[idx + len(delimiter):]
            return bytes(result)
        else:
            result = self._buffer[:]
            self._buffer.clear()
            return bytes(result)

    def at_eof(self) -> bool:
        return self._eof

    async def buffered_read(self, size: int):
        while len(self._buffer) < size:
            chunk = await self.read(size - len(self._buffer))
            if not chunk:
                break
            self._buffer.extend(chunk)
        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return bytes(result)

    async def close(self):
        if self._debug:
            print("Closing connection")
        if self.writer:
            if self.platform == self.MP:
                await self.writer.aclose()  # type: ignore[attr-defined]
            else:
                self.writer.close()
                await self.writer.wait_closed()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


class MQTTProtocol:
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
        # self._retry_task = asyncio.create_task(self._retry_pubacks_loop())

    async def connect(
            self,
            server,
            port,
            client_id,
            user,
            password,
            keepalive,
            ssl=False,
            ssl_params=None,
            timeout_sec=10,
    ):
        self.timeout_sec = timeout_sec
        try:
            # log(f"MQTTProtocol:connect. Connecting to {server}:{port}")
            self.stream = await StreamConnection.open(
                server,
                port,
                ssl=ssl,
                timeout=timeout_sec,
                is_micropython=_IS_MICROPYTHON,
                debug=self.verbose == 2,
            )

            packet = self._build_connect_packet(client_id, user, password, keepalive)
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
        await self._send_packet(self.DISCONNECT, b"")
        await self.stream.close()

    async def publish(self, topic, message, qos=0, retain=False, pid=None) -> bool:
        """
        Publishes a message to the given MQTT topic.

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

    async def subscribe(self, topic, qos=0, timeout_sec=5):
        packet = bytearray()
        pid = self._get_packet_id()
        packet.extend(struct.pack("!H", pid))
        packet.extend(self._encode_string(topic))
        packet.append(qos)

        await self._send_packet(self.SUBSCRIBE | 0x02, packet)

        try:
            resp = await asyncio.wait_for(self._read_packet(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            log("SUBACK timeout")
            return None

        if not resp:
            log("No response received after SUBSCRIBE")
            return None

        packet_type, payload = resp

        if packet_type != self.SUBACK:
            log(f"Expected SUBACK (0x90) but received {hex(packet_type)}")
            return None

        if len(payload) < 3:
            log(f"Invalid SUBACK packet length: {len(payload)}")
            return None

        received_pid = (payload[0] << 8) | payload[1]
        granted_qos = payload[2]

        if received_pid != pid:
            log(f"SUBACK PID mismatch: expected {pid}, got {received_pid}")
            return None

        if granted_qos & 0x80 or granted_qos != qos:
            log(
                f"Subscription failed or QoS mismatch: requested {qos}, granted {granted_qos}"
            )
            return None

        log(f"Subscribed to {topic} with QoS {granted_qos}")
        return pid

    async def unsubscribe(self, topic, timeout_sec=5):
        pid = self._get_packet_id()
        packet = struct.pack("!H", pid) + self._encode_string(topic)
        await self._send_packet(self.UNSUBSCRIBE | 0x02, packet)

        resp = await asyncio.wait_for(self._read_packet(), timeout=timeout_sec)
        if resp[0] == self.UNSUBACK:
            log(f"Unsubscribed from {topic}")
        else:
            log(f"Unexpected UNSUBACK response: {resp}")
        return pid

    async def ping(self):
        await self._send_packet(self.PINGREQ, b"")

    async def handle_packet(self) -> bool:
        try:
            resp = await self._read_packet()
            if not resp:
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
                topic = payload[2: 2 + topic_len].decode()
                offset = 2 + topic_len

                if qos > 0:
                    pid = struct.unpack("!H", payload[offset: offset + 2])[0]
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

        except asyncio.TimeoutError:
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
            log("No data received (header)")
            return None

        packet_type = header[0]
        remaining_length = 0
        multiplier = 1

        while True:
            byte_data = await self.stream.buffered_read(1)
            if not byte_data:
                log("No data received (remaining length)")
                return None

            byte = byte_data[0]
            remaining_length += (byte & 0x7F) * multiplier
            if not (byte & 0x80):
                break
            multiplier *= 128
            if multiplier > 128 * 128 * 128:
                raise Exception("Malformed remaining length (exceeds 4 bytes)")

        payload = (
            await self.stream.buffered_read(remaining_length)
            if remaining_length > 0
            else b""
        )
        if payload is None:
            log("No payload received")
            return None

        if self.verbose == 2:
            dump_array(payload, header=f"Received packet: {packet_type}")

        return packet_type, payload

    async def _send_packet(self, packet_type, payload):
        remaining_length = len(payload)
        remaining_bytes = bytearray()
        while True:
            byte = remaining_length % 128
            remaining_length //= 128
            if remaining_length:
                byte |= 0x80
            remaining_bytes.append(byte)
            if not remaining_length:
                break

        packet = bytearray([packet_type]) + remaining_bytes + payload

        if self.verbose == 2:
            dump_array(packet, header=f"Sending packet: {packet_type}")

        await self.stream.write(packet, timeout=self.timeout_sec)

    def _build_connect_packet(self, client_id, user, password, keepalive):
        packet = bytearray()
        packet.extend(self._encode_string("MQTT"))
        packet.append(4)  # Protocol level 4 (MQTT 3.1.1)
        flags = 0x02  # Clean session
        if user:
            flags |= 0x80
        if password:
            flags |= 0x40
        packet.append(flags)
        packet.extend(struct.pack("!H", keepalive))
        packet.extend(self._encode_string(client_id))
        if user:
            packet.extend(self._encode_string(user))
        if password:
            packet.extend(self._encode_string(password))
        return packet

    def _encode_string(self, s):
        if isinstance(s, str):
            s = s.encode()
        return struct.pack("!H", len(s)) + s

    def _get_packet_id(self):
        self.pid = (self.pid + 1) % 65535
        if self.pid == 0:
            self.pid = 1
        # log(f"Generated new packet ID: {self.pid}")
        return self.pid

    def get_error_message(self, error_code):
        return (
            self.CONNACK_CODES.get(error_code, f"Unknown error ({error_code})")
            if error_code
            else None
        )

    async def close(self):
        if self.stream:
            await self.stream.close()
            self.stream = None

    async def _retry_pubacks_loop(self):
        RETRY_INTERVAL = 2_000  # ms
        while True:
            await asyncio.sleep(1)
            now = ticks_ms()
            for pid, (ts, topic, message, qos, retain, dup) in list(self._pending_pubacks.items()):
                if ticks_diff(now, ts) > RETRY_INTERVAL:
                    log(f"Retrying QoS 1 message PID {pid} (dup={dup})")
                    try:
                        await self._resend_qos1(pid, topic, message, qos, retain, dup=True)
                        self._pending_pubacks[pid] = (
                            ticks_ms(),
                            topic,
                            message,
                            qos,
                            retain,
                            True,
                        )
                    except Exception as e:
                        log(f"Retry failed for PID {pid}: {e}")

    async def _resend_qos1(self, pid, topic, message, qos, retain, dup=False):
        packet = bytearray()
        packet.extend(self._encode_string(topic))
        packet.extend(struct.pack("!H", pid))
        packet.extend(message)

        flags = qos << 1
        if retain:
            flags |= 1
        if dup:
            flags |= 0x08  # DUP flag for resend

        await self._send_packet(self.PUBLISH | flags, packet)


class MqttStats:
    def __init__(self):
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

    def publish(self, status, rtt_ms, packet_size: int):
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
        self.packets_received += 1
        self.bytes_received += packet_size
        if len(self.sub_package_size_list) >= self.max_list_size:
            self.sub_package_size_list.pop(0)
        self.sub_package_size_list.append(packet_size)

    def connect(self):
        self.connections_sent += 1

    def connect_fail(self):
        self.connections_failed += 1

    def ping_sent(self):
        self.ping_sent_count += 1

    def ping_received(self, rtt_ms):
        self.ping_received_count += 1
        if len(self.ping_rtt_ms_list) >= self.max_list_size:
            self.ping_rtt_ms_list.pop(0)
        self.ping_rtt_ms_list.append(rtt_ms)

    def reset(self):
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

    def get_stats(self):
        # add some stats aggregation
        pub_rtt_ms = sum(self.pub_rtt_ms_list) / len(self.pub_rtt_ms_list) if self.pub_rtt_ms_list else 0
        pub_package_size = sum(self.pub_package_size_list) / len(self.pub_package_size_list) if self.pub_package_size_list else 0
        sub_package_size = sum(self.sub_package_size_list) / len(self.sub_package_size_list) if self.sub_package_size_list else 0
        ping_rtt_ms = sum(self.ping_rtt_ms_list) / len(self.ping_rtt_ms_list) if self.ping_rtt_ms_list else 0
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
            "ping_rtt_ms": int(ping_rtt_ms)
        }


class MQTTClient:
    def __init__(
            self,
            client_id=None,
            server=None,
            port=1883,
            user=None,
            password=None,
            keepalive=60,
            ssl=False,
            ssl_params=None,
            verbose: int = 0,
    ):
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
        self.subscriptions = {}
        self.last_ping = 0
        self.last_rx = 0
        self._last_error_code = None

        self.reconnect_interval = 0
        self.max_reconnect_interval = 0
        self.reconnect_attempt = 0

        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.on_ping = None

        self._ping_task = None
        self._receive_task = None
        self.stats: MqttStats = MqttStats()
        self.protocol = MQTTProtocol(self)

    async def connect(self, timeout_sec: int = 10):
        if self.connected:
            return True

        try:
            log(f"MQTTClient:connect. Connecting to {self.server}:{self.port}")
            self.stats.connect()
            try:
                result = await self.protocol.connect(
                    self.server,
                    self.port,
                    self.client_id,
                    self.user,
                    self.password,
                    self.keepalive,
                    self.ssl,
                    self.ssl_params,
                    timeout_sec,
                )
            except Exception as e:
                log(f"Failed to connect to {self.server}:{self.port}: {e}")
                result = False

            if not result:
                self.stats.connect_fail()
                return False

            self.connected = True
            self.reconnect_attempt = 0
            self.last_rx = ticks_ms()
            self.last_ping = ticks_ms()

            self._receive_task = asyncio.create_task(self._receive_loop())
            self._ping_task = asyncio.create_task(self._keep_alive())

            if self.on_connect:
                await self.on_connect(self, 0)

            return True

        except asyncio.TimeoutError:
            log("Connection timeout")
            await self.handle_disconnect()
        except Exception as e:
            log(f"Connection failed: {e}")
            await self.handle_disconnect()
        self.stats.connect_fail()
        return False

    async def disconnect(self):
        if self.connected:
            self.connected = False
            try:
                await self.protocol.disconnect()
            except Exception as e:
                log(f"Error disconnecting: {e}")
            finally:
                self.connected = False
                await self.handle_disconnect()

    async def publish(self, topic, message, qos=1, retain=False):
        if not self.connected:
            if not await self.connect():
                log("Client not connected, publish skipped")
                return False

        if isinstance(message, str):
            message = message.encode()

        try:
            tt = ticks_ms()
            success = await self.protocol.publish(topic, message, qos, retain)
            elapsed = ticks_diff(ticks_ms(), tt)
            if not success:
                log(f"Publish failed for topic {topic}. No PUBACK received.")
                self.stats.publish(False, elapsed, len(message))
            else:
                # log(f"Published message to {topic} with PID {pid} in {elapsed}ms")
                self.stats.publish(True, elapsed, len(message))
            return success
        except Exception as e:
            log(f"Publish error: {e}")
            await self.handle_disconnect()
            return None

    async def subscribe(self, topic, qos=0):
        pid = self.protocol._get_packet_id()
        packet = bytearray()
        packet.extend(struct.pack("!H", pid))
        packet.extend(self.protocol._encode_string(topic))
        packet.append(qos)

        self.subscriptions[topic] = {"pid": pid, "qos": qos, "confirmed": False}
        await self.protocol._send_packet(self.protocol.SUBSCRIBE | 0x02, packet)
        log(f"Subscribe request sent for topic {topic} with PID {pid}")

    async def unsubscribe(self, topic):
        if not self.connected:
            if not await self.connect():
                raise Exception("Not connected")

        pid = self.protocol._get_packet_id()
        packet = bytearray()
        packet.extend(struct.pack("!H", pid))
        packet.extend(self.protocol._encode_string(topic))

        await self.protocol._send_packet(self.protocol.UNSUBSCRIBE | 0x02, packet)
        self.subscriptions.pop(topic, None)
        log(f"Unsubscribe request sent for topic {topic} with PID {pid}")

    def reconnect_delay_set(self, min_delay=1, max_delay=10):
        self.reconnect_interval = min_delay
        self.max_reconnect_interval = max_delay

    def get_last_error(self):
        return self.protocol.get_error_message(self._last_error_code)

    async def _keep_alive(self):
        log("Starting keep-alive loop")
        while self.connected:
            now = ticks_ms()
            elapsed = ticks_diff(now, self.last_ping)
            if elapsed >= self.keepalive * 1000 / 2:
                try:
                    await self.protocol.ping()
                    self.last_ping = now
                    if self.on_ping:
                        self.stats.ping_sent()
                        await self.on_ping(self, True, 0)
                except Exception as e:
                    log(f"Ping error: {e}")
                    await self.handle_disconnect()
                    break

            if ticks_diff(now, self.last_rx) > self.keepalive * 1000 * 1.5:
                log("Server timeout, reconnecting")
                await self.handle_disconnect()
                break

            await asyncio.sleep(1)
        log("Keep-alive loop stopped")

    def mark_disconnected(self):
        self.connected = False

    async def _receive_loop(self):
        log("Starting receive loop")
        while self.connected:
            try:
                ok = await self.protocol.handle_packet()
                if not ok:
                    log("Receive error, stopping loop")
                    self.mark_disconnected()
                    break
            except asyncio.TimeoutError:
                if not self.connected:
                    break
                log("Receive timeout")
            except Exception as e:
                console.print_exception()
                log(f"Receive error: {type(e)}")
                await self.handle_disconnect()
                break
        log("Receive loop stopped")

    async def handle_disconnect(self, return_code=None):
        was_connected = self.connected
        self.connected = False

        if return_code is not None:
            self._last_error_code = return_code

        # Cancel tasks safely
        for task in [self._ping_task, self._receive_task]:
            if task:
                try:
                    task.cancel()
                    await task  # Ensure the task is fully canceled
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log(f"Error canceling task: {e}")

        self._ping_task = None
        self._receive_task = None

        await self.protocol.close()

        if was_connected and self.on_disconnect:
            try:
                await self.on_disconnect(self, return_code)
            except Exception as e:
                log(f"Error in on_disconnect callback: {e}")

        if return_code:
            log(
                f"Disconnected from broker: {self.protocol.get_error_message(return_code)}"
            )
        else:
            log("Disconnected from broker")

        should_reconnect = was_connected or (
                return_code and return_code in self.protocol.RECONNECTABLE_ERRORS
        )
        if should_reconnect:
            asyncio.create_task(self._reconnect())

    async def _reconnect(self):
        if self.reconnect_interval <= 0 or self.max_reconnect_interval <= 0:
            return
        self.reconnect_attempt += 1
        delay = min(
            self.reconnect_interval * (2 ** (self.reconnect_attempt - 1)),
            self.max_reconnect_interval,
        )
        log(f"Reconnecting in {delay}s (attempt {self.reconnect_attempt})")
        await asyncio.sleep(delay)
        if not self.connected:
            await self.connect()
