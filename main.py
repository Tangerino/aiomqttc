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

from config import Config
from wifi import wifi

try:
    import signal
except ImportError:
    # For platforms that don't support signal (like MicroPython)
    signal = None

from aiomqttc import MQTTClient, log, _IS_MICROPYTHON, MqttStats

# Flag to indicate shutdown
shutdown_requested = False
lowest_ram_free = None
max_ram_usage = 0
lowest_wifi_signal = None
mqtt_stats: MqttStats = MqttStats()

boot_time = time()


def get_uptime():
    uptime = int(time() - boot_time)
    minutes = uptime // 60
    hours = minutes // 60
    days = hours // 24
    str_uptime = f"{int(days)}d {int(hours % 24)}h {int(minutes % 60)}m {int(uptime % 60)}s"
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
        mac = ":".join("{:02x}".format(b) for b in sta.config("mac"))
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


def check_ram_usage(quiet: bool = False) -> dict:
    """Check and log RAM usage"""
    mem_alloc = gc_mem_alloc()
    mem_free = gc_mem_free()
    global lowest_ram_free
    global max_ram_usage
    if mem_alloc > max_ram_usage:
        max_ram_usage = mem_alloc
    if lowest_ram_free is None or mem_free < lowest_ram_free:
        lowest_ram_free = mem_free
    if not quiet:
        log("RAM Usage")
        log(f"    Free RAM............: {mem_free // 1024:6d} Kb")
        log(f"    Allocated RAM.......: {mem_alloc // 1024:6d} Kb")
        log(f"    Lowest Free RAM.....: {lowest_ram_free // 1024:6d} Kb")
        log(f"    Max Allocated RAM...: {max_ram_usage // 1024:6d} Kb")
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


# Signal handler for graceful shutdown
def signal_handler():
    global shutdown_requested
    log("Shutdown requested, closing MQTT client...")
    shutdown_requested = True


# Register signal handler
async def register_signal_handlers():
    if _IS_MICROPYTHON:
        # MicroPython does not support signal handlers
        log(
            "Signal handlers are not supported in MicroPython. Using KeyboardInterrupt fallback."
        )
        return
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # For systems where add_signal_handler is not implemented (e.g., Windows)
            log("Warning: Signal handlers not fully supported on this platform.")


async def periodic_publish(client: MQTTClient, last_pub_ts: int, pub_freq_sec: int = 1):
    """Publish a message periodically"""
    ok = True
    if time() - last_pub_ts >= pub_freq_sec:
        message = f"Periodic message #{last_pub_ts} from MicroPython"
        ok = await client.publish("micropython/test", message, qos=1)
        last_pub_ts = time()
    return last_pub_ts, ok


async def client_connect(config: Config, stats: MqttStats) -> MQTTClient:
    server = config.mqtt_broker
    client_id = f"esp32_client_{random.randint(1000, 9999)}"
    port = config.mqtt_port
    username = config.mqtt_username
    password = config.mqtt_password
    ssl = config.mqtt_tls
    keepalive = 15
    verbose: int = 0
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


def print_stats_table(stats: dict):
    """Print MQTT stats in a clean ASCII table format."""

    rows = [
        ["Connections", "Started", stats["connections_sent"]],
        ["", "Failed", stats["connections_failed"]],
        ["Packets", "Sent", stats["packets_sent"]],
        ["", "Received", stats["packets_received"]],
        ["Bytes", "Sent", stats["bytes_sent"]],
        ["", "Received", stats["bytes_received"]],
        ["Subscribe", "Avg Size", stats["sub_package_avg_size"]],
        ["Publish", "OK Count", stats["pub_ok_count"]],
        ["", "Fail Count", stats["pub_fail_count"]],
        ["", "RTT (ms)", stats["pub_rtt_ms"]],
        ["", "Avg Size", stats["pub_package_avg_size"]],
        ["Ping", "Sent", stats["ping_sent_count"]],
        ["", "Received", stats["ping_received_count"]],
        ["", "RTT (ms)", stats["ping_rtt_ms"]],
    ]

    col_widths = [max(len(row[i]) for row in rows) if i < 2 else 10 for i in range(3)]

    def border():
        return "+-" + "-+-".join("-" * w for w in col_widths) + "-+"

    def format_row(row):
        return "| " + " | ".join(f"{str(cell):{w}}" for cell, w in zip(row, col_widths)) + " |"

    log("MQTT Client Stats")
    print(border())
    print(format_row(["Category", "Metric", "Value"]))
    print(border())
    for row in rows:
        print(format_row(row))
    print(border())


def print_client_stats(client: MQTTClient) -> dict:
    stats = client.stats.get_stats()
    print_stats_table(stats)
    return stats


async def publish_stats(client: MQTTClient, client_stats: dict, wifi_stats: dict, ram_stats: dict, uptime_stats: dict):
    """Publish stats to the broker"""
    client_stats["_id"] = client.client_id
    stats = {
        "client": client_stats,
        "wifi": wifi_stats,
        "ram": ram_stats,
        "uptime": uptime_stats,
    }
    message = json.dumps(stats, separators=(",", ":"))
    ok = await client.publish("micropython/stats", message, qos=1)
    if not ok:
        log("[MAIN] Failed to publish stats")
    return ok


async def main():
    log("Stating MQTT Example")
    await register_signal_handlers()
    config = Config()
    config.load()
    sta = wifi(config.wifi_ssid, config.wifi_password)

    log("Running... (Press Ctrl+C to exit)")
    global shutdown_requested
    check_ram_usage(quiet=True)
    last_put_ts = time()
    pub_freq_sec = 1
    try:
        while not shutdown_requested:
            client = await client_connect(config, mqtt_stats)
            ram_loop = 0
            max_ram_loop = 5
            uptime_stats = {}
            ram_stats = {}
            wifi_stats = {}
            while client.connected and not shutdown_requested:
                await asyncio.sleep(1)
                last_put_ts, ok = await periodic_publish(client, last_put_ts, pub_freq_sec)
                if not ok:
                    log("[MAIN] Failed to publish periodic message")
                    break
                ram_loop += 1
                if ram_loop >= max_ram_loop:
                    ram_loop = 0
                    quiet = False
                    client_stats = print_client_stats(client)
                    await publish_stats(client, client_stats, wifi_stats, ram_stats, uptime_stats)
                else:
                    quiet = True
                ram_stats = check_ram_usage(quiet=quiet)
                wifi_stats = check_wifi_signal(sta, quiet=quiet)
                uptime_stats = get_uptime()
            log("Disconnected from broker, stopping periodic publish task.")
            await client.disconnect()
            if not shutdown_requested:
                await asyncio.sleep(5)

    except KeyboardInterrupt:
        log("KeyboardInterrupt received, stopping.")
        shutdown_requested = True
        try:
            await client.disconnect()
        except Exception:
            pass


asyncio.run(main())
