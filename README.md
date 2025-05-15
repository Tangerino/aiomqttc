# aiomqttc - Asynchronous MQTT Client

An asynchronous MQTT client implementation compatible with both standard Python (CPython) and MicroPython environments, particularly optimized for ESP32 platforms.

## Features

- Fully asynchronous operation using Python's `asyncio`
- Support for both CPython and MicroPython runtimes
- Automatic reconnection with configurable backoff strategy
- QoS 0 and QoS 1 message support
- SSL/TLS connection support
- Topic subscription and message callback handling
- Keep-alive and ping management
- Clean connection termination

## Installation

```bash
# For CPython environments:
pip install aiomqttc

# For MicroPython environments:
# Copy aiomqttc.py to your device
```

## Basic Usage

```python
import asyncio
from aiomqttc import MQTTClient

async def on_connect_callback(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to a topic
    await client.subscribe("home/+/status", qos=1)
    
async def message_callback(topic, message, retain):
    print(f"Received message on {topic}: {message}")

async def main():
    # Create an MQTT client
    client = MQTTClient(
        client_id="my_client",
        server="mqtt.example.com",
        port=1883,
        user="username",
        password="password",
        keepalive=60
    )
    
    # Set up callback for incoming messages
    client.on_connect = on_connect_callback
    client.on_message = message_callback
    
    # Connect to broker
    await client.connect()
    
    # Keep the connection alive
    try:
        while True:
            # Publish a message
            await client.publish("home/status", "online", qos=1, retain=True)
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```