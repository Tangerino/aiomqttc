# aiomqttc API Documentation

## 1. Module Overview

Asynchronous MQTT client for MicroPython and CPython.

This module provides an MQTT client that can be used in asynchronous applications, supporting both MicroPython and standard CPython environments. It aims to provide a familiar API similar to other MQTT client libraries.

## 2. MQTTClient Class

An asynchronous MQTT client.

This client handles connecting to an MQTT broker, publishing messages, subscribing to topics, and managing the MQTT session including keep-alives and basic reconnection logic.

### Constructor

```python
MQTTClient(
    client_id: str | None = None,
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
)
```

**Parameters:**

*   `client_id` (str | None): The client ID. If None or too short, one is generated.
*   `server` (str | None): The MQTT broker address.
*   `port` (int): The MQTT broker port. Default: `1883`.
*   `user` (str | None): Username for authentication.
*   `password` (str | None): Password for authentication.
*   `keepalive` (int): Keep-alive interval in seconds. Default: `60`.
*   `ssl` (bool): True to use SSL/TLS. Default: `False`.
*   `ssl_params` (dict | None): SSL parameters (platform-specific).
*   `verbose` (int): Logging verbosity (0: off, 1: info, 2: debug with packet dumps). Default: `0`.
*   `stats` (MqttStats | None): An MqttStats instance for collecting statistics.
*   `clean_session` (bool): MQTT clean session flag. Default: `True`.
*   `will_topic` (str | None): Last will topic.
*   `will_message` (str | bytes | None): Last will message.
*   `will_qos` (int): QoS for the last will message. Default: `0`.
*   `will_retain` (bool): Retain flag for the last will message. Default: `False`.

### Methods

#### `connect(timeout_sec: int = 10) -> bool`

Connects to the MQTT broker. This method establishes the network connection, sends the MQTT CONNECT packet, and waits for a CONNACK. If successful, it starts background tasks for handling incoming messages and keep-alives.

*   **Parameters:**
    *   `timeout_sec` (int): Timeout in seconds for the connection attempt. Default: `10`.
*   **Returns:**
    *   (bool): `True` if the connection was successful, `False` otherwise.

#### `disconnect()`

Disconnects from the MQTT broker. Sends a DISCONNECT packet and closes the network connection. Also cancels background tasks.

#### `publish(topic: str, message: str | bytes, qos: int = 0, retain: bool = False) -> bool | None`

Publishes a message to a given topic.

*   **Parameters:**
    *   `topic` (str): The MQTT topic to publish to.
    *   `message` (str | bytes): The message payload.
    *   `qos` (int): Quality of Service level (0, 1). QoS 2 is not supported. Default: `0`.
    *   `retain` (bool): If True, the message is retained by the broker. Default: `False`.
*   **Returns:**
    *   (bool | None): `True` if the message was successfully sent (for QoS 0) or acknowledged (for QoS 1). `False` if PUBACK was not received in time for QoS 1. `None` if the client is not connected and cannot connect, or if an unexpected error occurs.

#### `subscribe(topic: str, qos: int = 0, callback: callable | None = None) -> bool`

Subscribes to a topic.

*   **Parameters:**
    *   `topic` (str): The topic filter to subscribe to.
    *   `qos` (int): The requested Quality of Service level. Default: `0`.
    *   `callback` (callable | None): Optional callback to be invoked when a message arrives on this topic. Signature: `def callback(topic, payload, retain)` or `async def callback(topic, payload, retain)`.
*   **Returns:**
    *   (bool): `True` if the subscribe request was successfully sent and acknowledged (SUBACK) with a matching QoS, `False` otherwise.

#### `unsubscribe(topic: str) -> bool`

Unsubscribes from a topic.

*   **Parameters:**
    *   `topic` (str): The topic filter to unsubscribe from.
*   **Returns:**
    *   (bool): `True` if the unsubscribe request was successfully sent and acknowledged (UNSUBACK), `False` otherwise.

#### `get_last_error() -> str | None`

Gets a human-readable message for the last connection error.

*   **Returns:**
    *   (str | None): A string describing the last CONNACK error, or `None` if no error or not applicable.

### Callbacks

Callbacks can be set by assigning a function (or async function) to the corresponding attribute on the `MQTTClient` instance.

*   `on_connect`: Async callback triggered on successful connection.
    *   **Signature:** `async def on_connect(client, rc)`
    *   **Parameters:**
        *   `client` (MQTTClient): The client instance.
        *   `rc` (int): The return code from the CONNACK packet (0 for success).
*   `on_disconnect`: Async callback triggered on disconnection.
    *   **Signature:** `async def on_disconnect(client, rc)`
    *   **Parameters:**
        *   `client` (MQTTClient): The client instance.
        *   `rc` (int | None): The return code indicating the reason for disconnection. `None` for a client-initiated clean disconnect.
*   `on_message`: Async callback triggered when a message is received.
    *   **Signature:** `async def on_message(client, topic, payload, retain)`
    *   **Parameters:**
        *   `client` (MQTTClient): The client instance.
        *   `topic` (str): The topic on which the message was received.
        *   `payload` (bytes): The message payload.
        *   `retain` (bool): The retain flag for the message.
*   `on_ping`: Async callback triggered when a PINGREQ is sent or PINGRESP is received.
    *   **Signature:** `async def on_ping(client, is_request, rtt_ms)`
    *   **Parameters:**
        *   `client` (MQTTClient): The client instance.
        *   `is_request` (bool): `True` if a PINGREQ was sent, `False` if a PINGRESP was received.
        *   `rtt_ms` (int): Round-trip time in milliseconds for PINGRESP (0 if `is_request` is `True`).

## 3. MqttStats Class

Collects and manages statistics for MQTT client operations.

### Constructor

```python
MqttStats()
```
Initializes MqttStats with default values.

### Methods

#### `publish(status: bool, rtt_ms: int, packet_size: int)`

Records statistics for a publish operation.

*   **Parameters:**
    *   `status` (bool): `True` if the publish was successful (e.g., PUBACK received), `False` otherwise.
    *   `rtt_ms` (int): Round-trip time in milliseconds for the publish operation.
    *   `packet_size` (int): Size of the published packet in bytes.

#### `receive(packet_size: int)`

Records statistics for a received packet.

*   **Parameters:**
    *   `packet_size` (int): Size of the received packet in bytes.

#### `connect()`
Increments the count of connection attempts.

#### `connect_fail()`
Increments the count of failed connection attempts.

#### `ping_sent()`
Increments the count of PINGREQ packets sent.

#### `ping_received(rtt_ms: int)`
Records statistics for a received PINGRESP.

*   **Parameters:**
    *   `rtt_ms` (int): Round-trip time in milliseconds for the PINGREQ/PINGRESP.

#### `reset()`
Resets all statistics to their initial values.

#### `get_stats() -> dict`
Calculates and returns a dictionary of aggregated statistics.

*   **Returns:**
    *   (dict): A dictionary containing various statistics. Example keys:
        *   `"packets_sent"` (int)
        *   `"packets_received"` (int)
        *   `"bytes_sent"` (int)
        *   `"bytes_received"` (int)
        *   `"pub_ok_count"` (int)
        *   `"pub_fail_count"` (int)
        *   `"pub_rtt_ms"` (int): Average publish RTT.
        *   `"pub_package_avg_size"` (int): Average published package size.
        *   `"sub_package_avg_size"` (int): Average received package size.
        *   `"connections_sent"` (int)
        *   `"connections_failed"` (int)
        *   `"ping_sent_count"` (int)
        *   `"ping_received_count"` (int)
        *   `"ping_rtt_ms"` (int): Average ping RTT.

## 4. StreamConnection Class

Manages an asynchronous network stream connection. This class provides methods for opening, reading from, writing to, and closing a network connection, with support for both MicroPython and CPython's asyncio. It is primarily used internally by `MQTTProtocol`.

### Key Public Methods

#### `classmethod async open(host: str, port: int, ssl: bool = False, timeout: float = None, is_micropython: bool = False, debug: bool = False) -> StreamConnection`
Opens a new stream connection.

*   **Parameters:**
    *   `host` (str): The host address to connect to.
    *   `port` (int): The port number to connect to.
    *   `ssl` (bool): If `True`, use SSL/TLS for the connection.
    *   `timeout` (float | None): Optional timeout in seconds for the connection attempt.
    *   `is_micropython` (bool): `True` if running on MicroPython.
    *   `debug` (bool): If `True`, enables debug logging.
*   **Returns:**
    *   (StreamConnection): An instance of `StreamConnection`.
*   **Raises:**
    *   `ValueError`: If the connection fails.

#### `async write(data: bytes, timeout: float = None, retries: int = 0)`
Writes data to the stream.

*   **Parameters:**
    *   `data` (bytes): The bytes to write.
    *   `timeout` (float | None): Optional timeout in seconds for the write operation.
    *   `retries` (int): Number of times to retry writing if it fails.
*   **Raises:**
    *   `ValueError`: If the write operation fails after all retries.

#### `async read(n: int = -1) -> bytes`
Reads up to `n` bytes from the stream. If `n` is -1, reads until EOF.

*   **Parameters:**
    *   `n` (int): The maximum number of bytes to read.
*   **Returns:**
    *   (bytes): The bytes read from the stream. Returns `b""` if EOF is reached.

#### `async close()`
Closes the stream connection.

## 5. RTC and Datetime Classes

These classes provide utility for handling date and time, primarily for logging purposes within the `aiomqttc` module.

### RTC Class
A real-time clock (RTC) interface. This class provides a basic abstraction for accessing the system's RTC.

#### Key Methods
*   `init(date_parts: tuple)`: Initializes the RTC with the given date and time (primarily for MicroPython).
*   `datetime() -> tuple`: Gets the current date and time from the RTC.

### Datetime Class
A helper class to represent a specific date and time.

#### Key Methods
*   `utc_now() -> Datetime`: Updates the `Datetime` object with the current UTC date and time.
*   `__str__() -> str`: Returns a string representation of the `Datetime` object (Format: `YYYY-MM-DD HH:MM:SS`).

## 6. MQTTProtocol Class (Internal)

Handles the MQTT protocol logic, including packet creation and parsing. This class is responsible for the low-level details of the MQTT protocol. It is used internally by `MQTTClient` and typically not directly interacted with by the end-user. Its methods mirror many of the `MQTTClient` methods but at a lower, packet-level.

Key responsibilities include:
*   Connecting to the broker and handling CONNACK.
*   Sending PUBLISH, SUBSCRIBE, UNSUBSCRIBE, PINGREQ, DISCONNECT packets.
*   Receiving and parsing PUBACK, SUBACK, UNSUBACK, PINGRESP, and incoming PUBLISH packets.
*   Managing packet IDs and encoding/decoding MQTT strings.
*   Handling QoS 1 publish acknowledgements.
