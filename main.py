"""
Example usage of the MQTT client library.

This example demonstrates how to create a client, connect to a broker,
subscribe to topics, and publish messages. It runs continuously and
handles graceful shutdown on Ctrl+C.
"""

import asyncio
import gc
import json
import random
from time import time

from aiomqttc import MQTTClient, MqttStats, log
from config import Config
from wifi import wifi

# Flag to indicate shutdown
shutdown_requested = False
lowest_ram_free = None
max_ram_usage = 0
lowest_wifi_signal = None
mqtt_stats: MqttStats = MqttStats()

boot_time = time()


def get_uptime():
    """
    Calculate the system uptime since `boot_time`.

    Returns:
        dict: A dictionary containing:
            - "uptime" (str): Human-readable uptime string in the format "Xd Yh Zm Ws"
            - "uptime_sec" (int): Total number of seconds since `boot_time`

    Example:
        >>> get_uptime()
        {
            'uptime': '0d 2h 17m 35s',
            'uptime_sec': 8255
        }

    Note:
        This function assumes that `boot_time` is a global variable set to the system time
        at the moment the application started, typically via `boot_time = time()`.
    """
    uptime = int(time() - boot_time)
    minutes = uptime // 60
    hours = minutes // 60
    days = hours // 24
    str_uptime = (
        f"{int(days)}d {int(hours % 24)}h {int(minutes % 60)}m {int(uptime % 60)}s"
    )
    return {
        "uptime": str_uptime,
        "uptime_sec": uptime,
    }


def gc_mem_free() -> int:
    if hasattr(gc, "mem_free"):
        return gc.mem_free()
    return 0


def gc_mem_alloc():
    if hasattr(gc, "mem_alloc"):
        return gc.mem_alloc()
    return 0


async def on_message(client, topic, payload, retain):
    log(f"Received message on {topic}: {payload.decode()}")


def check_wifi_signal(sta, quiet: bool = False) -> dict:
    """Check and log WiFi signal strength"""
    global lowest_wifi_signal
    if not sta:
        return {}
    try:
        rssi = sta.status("rssi")

        if lowest_wifi_signal is None or rssi < lowest_wifi_signal:
            lowest_wifi_signal = rssi

        ip = sta.ifconfig()[0]
        mac = ":".join(f"{b:02x}" for b in sta.config("mac"))
        if not quiet:
            log("WiFi Signal Strength")
            log(f"    WiFi Signal Strength: {rssi} dBm")
            log(f"    Lowest WiFi Signal..: {lowest_wifi_signal} dBm")
            log(f"    IP Address..........: {ip}")
            log(f"    MAC Address.........: {mac}")
        return {
            "signal": rssi,
            "signal_lowest": lowest_wifi_signal,
            "ip": ip,
            "mac": mac,
        }
    except Exception as e:
        log(f"Error checking WiFi signal: {e}")
        return {}


def check_ram_usage() -> dict:
    """
    Check and track current RAM usage statistics.

    This function queries the system's memory usage via `gc_mem_alloc()` and `gc_mem_free()` (which are
    expected to be wrappers around `gc.mem_alloc()` and `gc.mem_free()` in MicroPython or similar environments).

    It also maintains two global variables:
        - `lowest_ram_free`: Tracks the lowest amount of free memory observed since startup.
        - `max_ram_usage`: Tracks the highest amount of allocated memory observed since startup.

    Returns:
        dict: A dictionary containing:
            - "free" (int): Current free RAM in bytes.
            - "allocated" (int): Current allocated RAM in bytes.
            - "free_lowest" (int): Minimum observed free RAM (historical low).
            - "max_allocated" (int): Maximum observed allocated RAM (historical high).

    Example:
        >>> check_ram_usage()
        {
            'free': 26560,
            'allocated': 83440,
            'free_lowest': 26200,
            'max_allocated': 85000
        }

    Note:
        This function assumes that the following global variables are initialized elsewhere:
            - `lowest_ram_free = None`
            - `max_ram_usage = 0`
    """
    mem_alloc = gc_mem_alloc()
    mem_free = gc_mem_free()
    global lowest_ram_free
    global max_ram_usage
    if mem_alloc > max_ram_usage:
        max_ram_usage = mem_alloc
    if lowest_ram_free is None or mem_free < lowest_ram_free:
        lowest_ram_free = mem_free
    return {
        "free": mem_free,
        "allocated": mem_alloc,
        "free_lowest": lowest_ram_free,
        "max_allocated": max_ram_usage,
    }


# Define callback for successful connection
async def on_connect(client, return_code):
    log(f"Connected with code {return_code}")
    await client.subscribe("test/test", qos=1)


async def on_ping(client, request: bool, rtt_ms: int):
    # if request:
    #     log("PING sent to broker")
    # else:
    #     log(f"PING response received from broker in {rtt_ms} ms")
    pass


# Define callback for disconnection
async def on_disconnect(client, return_code):
    if return_code:
        log(f"Disconnected with code {return_code}")
    else:
        log("Disconnected")


async def periodic_publish(client: MQTTClient, last_pub_ts: int, pub_freq_sec: int = 1):
    """Publish a message periodically"""
    ok = True
    if time() - last_pub_ts >= pub_freq_sec:
        message = f"Periodic message #{last_pub_ts} from MicroPython"
        ok = await client.publish("micropython/test", message, qos=1)
        last_pub_ts = time()
    return last_pub_ts, ok


async def client_connect(config: Config, stats: MqttStats) -> MQTTClient:
    """
    Asynchronously establish a connection to an MQTT broker with retry logic.

    This function creates a new `MQTTClient` instance with settings from the provided `config`,
    sets callback handlers, and attempts to connect to the MQTT broker with exponential backoff retry logic.

    Args:
        config (Config): Configuration object containing MQTT connection parameters:
            - mqtt_broker (str): Broker hostname or IP.
            - mqtt_port (int): Broker port.
            - mqtt_username (str): Username for authentication (can be None).
            - mqtt_password (str): Password for authentication (can be None).
            - mqtt_tls (bool): Whether to use TLS/SSL.
        stats (MqttStats): An instance used to collect and track MQTT statistics.

    Returns:
        MQTTClient: A connected MQTT client instance ready for publish/subscribe operations.

    Retry Logic:
        - Starts with a delay of 1 second.
        - Exponential backoff is applied up to a maximum delay of 60 seconds.
        - A small random jitter is added to the delay to avoid thundering herd issues.

    Example:
        >>> client = await client_connect(config, stats)
        >>> await client.publish("topic/test", b"hello")

    Note:
        The function assumes that callback handlers (`on_message`, `on_connect`, etc.)
        are implemented in the global scope and set on the client before connecting.
    """
    server = config.mqtt_broker
    client_id = f"esp32_client_{random.randint(1000, 9999)}"
    port = config.mqtt_port
    username = config.mqtt_username
    password = config.mqtt_password
    ssl = config.mqtt_tls
    keepalive = 15
    verbose: int = 0
    will_topic = "micropython/disconnect"
    will_message = f"Client {client_id} disconnected"
    will_qos = 1
    will_retain = False
    # ================
    client = MQTTClient(
        client_id=client_id,
        server=server,
        ssl=ssl,
        keepalive=keepalive,
        user=username,
        password=password,
        port=port,
        verbose=verbose,
        stats=stats,
        clean_session=True,
        will_topic=will_topic,
        will_message=will_message,
        will_qos=will_qos,
        will_retain=will_retain,
    )
    # ================
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_ping = on_ping
    mqtt_retry_min_delay = 1  # in seconds
    mqtt_retry_max_delay = 60

    delay = mqtt_retry_min_delay
    while True:
        log("Connecting to broker...")
        if await client.connect():
            log("Connected to broker")
            break
        log(f"Failed to connect to broker, retrying in {delay} seconds...")
        await asyncio.sleep(delay + random.uniform(0, 0.5 * delay))
        delay = min(delay * 2, mqtt_retry_max_delay)
    return client


async def publish_stats(
    client: MQTTClient, sta, put_stats_last_ts: int, pub_stats_freq: int
):
    """
    Collect and publish system statistics over MQTT, with rate limiting.

    This function gathers multiple categories of system stats (RAM, Wi-Fi, uptime, MQTT client)
    and publishes them to the MQTT topic `"micropython/stats"` with QoS 1, unless the publish
    frequency threshold has not yet been met.

    Args:
        client (MQTTClient): An instance of the connected MQTT client.
        sta: A Wi-Fi interface object (e.g., `network.WLAN(STA_IF)` in MicroPython).
        put_stats_last_ts (int): The Unix timestamp (in seconds) of the last successful publish.
        pub_stats_freq (int): Minimum interval (in seconds) between successive publishes.

    Returns:
        tuple: (new_timestamp, success_flag)
            - new_timestamp (int): The updated timestamp of this publish attempt (or unchanged if skipped).
            - success_flag (bool): Whether the publish was successful (or skipped due to rate limit).

    Behavior:
        - Checks if enough time has passed since the last publish (`pub_stats_freq`).
        - Collects:
            - RAM usage via `check_ram_usage()`
            - Wi-Fi signal quality via `check_wifi_signal(sta, quiet=True)`
            - Uptime via `get_uptime()`
            - MQTT client stats via `client.stats.get_stats()`
        - Publishes the aggregated data to the MQTT topic in JSON format (minified).
        - Logs both the minified and pretty-printed versions of the JSON.

    Example:
        >>> put_stats_last_ts, success = await publish_stats(client, wlan, last_ts, 60)
    """
    ram_stats = check_ram_usage()
    wifi_stats = check_wifi_signal(sta, quiet=True)
    if time() - put_stats_last_ts < pub_stats_freq:
        return put_stats_last_ts, True
    uptime_stats = get_uptime()
    client_stats = client.stats.get_stats()
    client_stats["_id"] = client.client_id
    stats = {
        "client": client_stats,
        "wifi": wifi_stats,
        "ram": ram_stats,
        "uptime": uptime_stats,
    }
    message = json.dumps(stats, separators=(",", ":"))
    log(f"Publishing stats:{message}")
    ok = await client.publish("micropython/stats", message, qos=1)
    if not ok:
        log("[MAIN] Failed to publish stats")
    return time(), ok


async def mqtt_thread(config: Config, sta):
    """
    Background task that manages MQTT connection and periodic telemetry publishing.

    This coroutine runs in a loop and performs the following:
        1. Establishes an MQTT connection using configuration parameters.
        2. Publishes periodic messages at `pub_freq_sec` intervals (e.g., heartbeat).
        3. Publishes system statistics (RAM, Wi-Fi, uptime, client stats) at `pub_stats_sec` intervals.
        4. Handles automatic reconnection if the broker is unreachable or the connection drops.
        5. Logs all major steps and any publishing failures.

    Args:
        config (Config): Configuration object containing MQTT and Wi-Fi credentials.
        sta: Wi-Fi interface object (e.g., `network.WLAN(STA_IF)`).

    Globals:
        shutdown_requested (bool): A flag used to gracefully terminate the task.

    Variables:
        last_put_ts (int): Timestamp of last successful periodic message (e.g., heartbeat).
        pub_freq_sec (int): Frequency in seconds for periodic messages.
        pub_stats_sec (int): Frequency in seconds for publishing system statistics.
        put_stats_last_ts (int): Timestamp of last stats publish.

    Behavior:
        - If the MQTT connection fails or is lost, it waits 5 seconds before retrying.
        - Errors in the loop are caught and logged, and the loop resumes after a brief pause.

    Example:
        This function is typically run in the background using:
            asyncio.create_task(mqtt_thread(config, sta))

    """
    last_put_ts = time()
    pub_freq_sec = 1
    pub_stats_sec = 5
    put_stats_last_ts = time()
    while not shutdown_requested:
        try:
            client = await client_connect(config, mqtt_stats)
            while client.connected and not shutdown_requested:
                await asyncio.sleep(1)
                last_put_ts, ok = await periodic_publish(
                    client, last_put_ts, pub_freq_sec
                )
                if ok:
                    put_stats_last_ts, ok = await publish_stats(
                        client, sta, put_stats_last_ts, pub_stats_sec
                    )
                if not ok:
                    log("[MAIN] Failed to publish message")
                    break
            log("Disconnected from broker")
            await client.disconnect()
            if not shutdown_requested:
                await asyncio.sleep(5)
        except Exception as e:
            log(f"Error in MQTT thread: {e}")
            await asyncio.sleep(5)


async def main():
    """
    Main asynchronous entry point for the program.

    Responsibilities:
    1. Initializes RAM usage tracking.
    2. Registers signal handlers (e.g., for clean shutdown on SIGINT/SIGTERM).
    3. Loads configuration from `config.json` using the `Config` class.
    4. Connects to Wi-Fi using the provided SSID and password.
    5. Starts the `mqtt_thread()` task in the background to manage MQTT connectivity and telemetry.
    6. Enters a main loop where additional asynchronous tasks can be performed.

    Notes:
    - The `shutdown_requested` global variable can be used to trigger graceful termination in background tasks.
    - The call to `asyncio.create_task()` ensures `mqtt_thread()` runs concurrently.
    - The `while True` loop with `await asyncio.sleep(1)` acts as a placeholder for other logic that may be added later.

    Example Use Case:
        This kind of setup is typical in IoT devices where:
        - MQTT handles telemetry or control messages.
        - The main loop performs periodic measurements, device checks, or user interaction.

    Dependencies:
        - `check_ram_usage()`: Initializes memory tracking.
        - `log()`: Logging function for console/debug output.
        - `register_signal_handlers()`: Registers asyncio signal handlers for shutdown.
        - `Config`: Class for loading Wi-Fi and MQTT broker configuration.
        - `wifi(ssid, password)`: Connects to Wi-Fi.
        - `mqtt_thread(config, sta)`: Coroutine managing MQTT connection and publishing.

    """
    check_ram_usage()
    log("Stating aiomqttc example")
    config = Config().load()
    sta = wifi(config.wifi_ssid, config.wifi_password)
    log("Running... (Press Ctrl+C to exit)")
    global shutdown_requested
    config_tcb = asyncio.create_task(mqtt_thread(config, sta))
    while not shutdown_requested:
        # do something else
        await asyncio.sleep(1)
    log("Exiting main loop")
    await config_tcb


asyncio.run(main())
