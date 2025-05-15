"""
Example usage of the MQTT client library.

This example demonstrates how to create a client, connect to a broker,
subscribe to topics, and publish messages. It runs continuously and
handles graceful shutdown on Ctrl+C.
"""

import asyncio
import json
import random

from wifi import wifi

try:
    import signal
except ImportError:
    # For platforms that don't support signal (like MicroPython)
    signal = None

from aiomqttc import MQTTClient, log, _IS_MICROPYTHON

# Flag to indicate shutdown
shutdown_requested = False


def load_config():
    try:
        with open('config.json', 'r') as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        template = {
            "wifi": {
                "ssid": "ssid",
                "password": "wifi_pwd"
            },
            "mqtt": {
                "broker": "hivemq.cloud",
                "port": 8883,
                "username": "demo",
                "password": "pwd",
                "tls": True
            }
        }
        with open('config.json', 'w') as config_file:
            json.dump(template, config_file, indent=4)
        log("Config file not found. Created a template config.json")
        return template


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


async def periodic_publish(client: MQTTClient):
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


async def client_connect() -> MQTTClient:
    server = "15880ce84c254f03abe400915e786926.s1.eu.hivemq.cloud"
    client_id = f"esp32_client_{random.randint(1000, 9999)}"
    port = 8883
    username = "mp_demo"
    password = "Abigpwd1"
    keepalive = 60
    verbose: int = 0
    ssl = True
    # ================
    client = MQTTClient(client_id=client_id, server=server, ssl=ssl, keepalive=keepalive, user=username, password=password, port=port, verbose=verbose)
    # ================
    # client.reconnect_delay_set(min_delay=1, max_delay=60) # not fully tested!!!
    # Set callbacks
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    while True:
        log("Connecting to broker...")
        if await client.connect():
            log("Connected to broker!")
            break
        log("Failed to connect to broker, retrying...")
        # Wait for a bit before retrying
        await asyncio.sleep(5)
    return client


async def stop_task(task: asyncio.Task, timeout: float = 5.0):
    """Asynchronously stops a task with optional timeout."""
    if task.done():
        log(f"Task '{task.get_name()}' already done.")
        # Optional: check for exceptions if needed task.exception()
        return

    task.cancel()
    try:
        # Wait for the task to finish processing the cancellation (or timeout)
        # await task itself handles CancelledError propagation appropriately
        await asyncio.wait_for(task, timeout=timeout)
        # If wait_for completes without timeout or CancelledError,
        # it means the task finished normally *despite* cancellation attempt.
        log(f"Task '{task.get_name()}' finished normally after cancel request.")
    except asyncio.CancelledError:
        # This means the task *acknowledged* the cancellation.
        log(f"Task '{task.get_name()}' successfully cancelled.")
    except asyncio.TimeoutError:
        log(f"Timeout waiting for task '{task.get_name()}' to cancel.")
        # Task might still be running here if it didn't hit an await
    except Exception as e:
        # The task raised an exception *other* than CancelledError
        log(f"Task '{task.get_name()}' raised an error during cancellation wait: {e!r}")


def start_task(client, task_func) -> asyncio.Task:
    """
    Starts a coroutine function as an asyncio Task in MicroPython,
    passing the client and logging the start.

    Args:
        client: The MQTTClient instance (or similar).
        task_func: The coroutine function to run (e.g., async def my_worker(client): ...).

    Returns:
        asyncio.Task: The created task handle, or None if creation failed.
    """
    try:
        # Try to get the function name for clearer logs
        task_name = task_func.__name__
    except AttributeError:
        # If it's not a standard function (e.g., lambda), use repr
        task_name = repr(task_func)

    log(f"Creating task for: {task_name}")

    try:
        # Call the function to get the coroutine object
        coroutine_object = task_func(client)
        # Schedule the coroutine object as a task
        tcb = asyncio.create_task(coroutine_object)

        # --- Logging Success ---
        # Option 1:
        log(f"Task '{task_name}' created successfully.")
        return tcb
    except Exception as e:
        # --- Logging Failure ---
        err_msg = f"Failed to create task for {task_name}: {e}"
        log(err_msg)
        raise e  # Let the caller handle the exception


async def main():
    log("Stating MQTT Example")
    await register_signal_handlers()
    ssid = "lana"
    password = "putaputa"
    wifi(ssid, password)

    log("Running... (Press Ctrl+C to exit)")
    global shutdown_requested
    try:
        while not shutdown_requested:
            client = await client_connect()
            publish_task = start_task(client, periodic_publish)

            while client.connected and not shutdown_requested:
                await asyncio.sleep(1)

            await stop_task(publish_task)
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
