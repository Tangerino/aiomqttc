"""
Example usage of the MQTT client library.

This example demonstrates how to create a client, connect to a broker,
subscribe to topics, and publish messages. It runs continuously and
handles graceful shutdown on Ctrl+C.
"""

import asyncio
import gc
import random

from config import Config
from wifi import wifi

try:
    import signal
except ImportError:
    # For platforms that don't support signal (like MicroPython)
    signal = None

from aiomqttc import MQTTClient, log, _IS_MICROPYTHON

# Flag to indicate shutdown
shutdown_requested = False
lowest_ram_free = None
max_ram_usage = 0


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


def check_ram_usage(quiet: bool = False):
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
        log(f"    Free RAM...........: {mem_free // 1024:6d} Kb")
        log(f"    Allocated RAM......: {mem_alloc // 1024:6d} Kb")
        log(f"    Lowest Free RAM....: {lowest_ram_free // 1024:6d} Kb")
        log(f"    Max Allocated RAM..: {max_ram_usage // 1024:6d} Kb")


# Define callback for successful connection
async def on_connect(client, return_code):
    log(f"Connected with code {return_code}")
    await client.subscribe("test/test", qos=1)


async def on_ping(client, request: bool, rtt_ms: int):
    if request:
        log("PING sent to broker")
    else:
        log(f"PING response received from broker in {rtt_ms} ms")


# Define callback for disconnection
async def on_disconnect(return_code):
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


async def periodic_publish(client: MQTTClient, config: Config):
    """Publish a message periodically"""
    log("Starting periodic publish task...")
    count = 0
    while not shutdown_requested:
        count += 1
        message = f"Periodic message #{count} from MicroPython"
        log(f"Publishing: {message}")
        pid = await client.publish("micropython/test", message, qos=1)
        if pid is None:
            log("Failed to publish message")
        await asyncio.sleep(1)
    log("Periodic publish task stopped.")


async def client_connect(config: Config) -> MQTTClient:
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
    )
    # ================
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_ping = on_ping
    while True:
        log("Connecting to broker...")
        if await client.connect():
            log("Connected to broker")
            break
        log("Failed to connect to broker, retrying...")
        await asyncio.sleep(5)
    return client


async def main():
    log("Stating MQTT Example")
    await register_signal_handlers()
    config = Config()
    config.load()
    wifi(config.wifi_ssid, config.wifi_password)

    log("Running... (Press Ctrl+C to exit)")
    global shutdown_requested
    check_ram_usage(quiet=True)
    try:
        while not shutdown_requested:
            client = await client_connect(config)
            periodic_publish_task = asyncio.create_task(
                periodic_publish(client, config)
            )
            ram_loop = 0
            max_ram_loop = 5
            while client.connected and not shutdown_requested:
                await asyncio.sleep(1)
                ram_loop += 1
                if ram_loop >= max_ram_loop:
                    ram_loop = 0
                    quiet = False
                else:
                    quiet = True
                check_ram_usage(quiet=quiet)
            await periodic_publish_task
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
