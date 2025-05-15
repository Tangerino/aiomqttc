"""
Example usage of the MQTT client library.

This example demonstrates how to create a client, connect to a broker,
subscribe to topics, and publish messages. It runs continuously and
handles graceful shutdown on Ctrl+C.
"""

import asyncio
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


# Define callback for received messages
def on_message(topic, payload, retain):
    log(f"Received message on {topic}: {payload.decode()}")


# Define callback for successful connection
def on_connect(client, return_code):
    log(f"Connected with code {return_code}")
    asyncio.create_task(client.subscribe("test/test", qos=1))


# Define callback for disconnection
def on_disconnect(return_code):
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
        log("Signal handlers are not supported in MicroPython. Using KeyboardInterrupt fallback.")
        return
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # For systems where add_signal_handler is not implemented (e.g., Windows)
            log("Warning: Signal handlers not fully supported on this platform.")

            # Fallback for Windows
            def win_handler(signum, frame):
                signal_handler()

            signal.signal(sig, win_handler)


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
    keepalive = 60
    verbose: int = 0
    # ================
    client = MQTTClient(client_id=client_id, server=server, ssl=ssl, keepalive=keepalive, user=username, password=password, port=port, verbose=verbose)
    # ================
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
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
    try:
        while not shutdown_requested:
            client = await client_connect(config)
            periodic_publish_task = asyncio.create_task(periodic_publish(client, config))
            while client.connected and not shutdown_requested:
                await asyncio.sleep(1)
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
