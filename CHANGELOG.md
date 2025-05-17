# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog] and this project adheres to [Semantic Versioning].

## [Unreleased]

## [1.0.2] - 2025-05-17

### Added

- Add client statistics functionality to track the number of messages sent, received, and acknowledged.
    - Example

```bash
2000-01-01 03:40:12.546 PUBACK received for PID 65
2000-01-01 03:40:13.655 PUBACK received for PID 66
2000-01-01 03:40:14.217 Received message on test/test: message-1
2000-01-01 03:40:14.255 Received message on test/test: message-10
2000-01-01 03:40:14.880 Received message on test/test: message-18
2000-01-01 03:40:14.894 Received message on test/test: message-2
2000-01-01 03:40:14.909 Received message on test/test: message-19
2000-01-01 03:40:15.086 Received message on test/test: message-6
2000-01-01 03:40:15.099 Received message on test/test: message-4
2000-01-01 03:40:15.114 Received message on test/test: message-9
2000-01-01 03:40:16.006 PUBACK received for PID 67
2000-01-01 03:40:16.840 MQTT Client Stats
+-------------+------------+------------+
| Category    | Metric     | Value      |
+-------------+------------+------------+
| Connections | Started    | 1          |
|             | Failed     | 0          |
| Packets     | Sent       | 66         |
|             | Received   | 20         |
| Bytes       | Sent       | 2433       |
|             | Received   | 191        |
| Subscribe   | Avg Size   | 9          |
| Publish     | OK Count   | 66         |
|             | Fail Count | 0          |
|             | RTT (ms)   | 260        |
|             | Avg Size   | 37         |
| Ping        | Sent       | 9          |
|             | Received   | 9          |
|             | RTT (ms)   | 60         |
+-------------+------------+------------+
2000-01-01 03:40:16.919 RAM Usage
2000-01-01 03:40:16.921     Free RAM............:   1952 Kb
2000-01-01 03:40:16.922     Allocated RAM.......:     45 Kb
2000-01-01 03:40:16.923     Lowest Free RAM.....:   1891 Kb
2000-01-01 03:40:16.935     Max Allocated RAM...:    106 Kb
2000-01-01 03:40:16.941 WiFi Signal Strength
2000-01-01 03:40:16.943     WiFi Signal Strength: -93 dBm
2000-01-01 03:40:16.944     Lowest WiFi Signal..: -96 dBm
2000-01-01 03:40:16.955     IP Address..........: 192.168.86.20
2000-01-01 03:40:16.957     MAC Address.........: 30:83:98:d6:1d:f0
2000-01-01 03:40:17.130 PUBACK received for PID 68
```

- Notice the very low Wi-Fi signal as of -96 dBm. This is a good test case to see how the library handles low signal
  strength.
- ⚠️ At this signal level, expect:
    - Very high latency and jitter
    - Frequent packet drops, making MQTT with QoS > 0 unreliable
    - Difficulty maintaining TCP connections
    - Possible disconnects during idle periods

- Tested network disconnects and reconnects conditions:
```bash
2000-01-01 04:00:06.426 PUBACK received for PID 629
2000-01-01 04:00:07.546 PUBACK received for PID 630
2000-01-01 04:00:08.710 Console not available
2000-01-01 04:00:08.712 Unhandled exception in handle_packet: -104
2000-01-01 04:00:08.713 Receive error, stopping loop
2000-01-01 04:00:08.715 Receive loop stopped
2000-01-01 04:00:08.997 Keep-alive loop stopped
2000-01-01 04:00:09.000 Periodic publish task cancelled.
2000-01-01 04:00:09.001 Disconnected from broker, stopping periodic publish task.
2000-01-01 04:00:14.008 Connecting to broker...
2000-01-01 04:00:14.010 MQTTClient:connect. Connecting to s1.eu.hivemq.cloud:8883
2000-01-01 04:00:14.261 MQTTProtocol:connect. Connection error: Write failed after 1 attempts: -29312
2000-01-01 04:00:14.270 Failed to connect to s1.eu.hivemq.cloud:8883: Write failed after 1 attempts: -29312
2000-01-01 04:00:14.277 Failed to connect to broker, retrying in 1 seconds...
2000-01-01 04:00:15.456 Connecting to broker...
2000-01-01 04:00:15.459 MQTTClient:connect. Connecting to s1.eu.hivemq.cloud:8883
2000-01-01 04:00:15.741 MQTTProtocol:connect. Connection error: Write failed after 1 attempts: -29312
2000-01-01 04:00:15.750 Failed to connect to s1.eu.hivemq.cloud:8883: Write failed after 1 attempts: -29312
2000-01-01 04:00:15.757 Failed to connect to broker, retrying in 2 seconds...
2000-01-01 04:00:18.567 Connecting to broker...
2000-01-01 04:00:18.569 MQTTClient:connect. Connecting to s1.eu.hivemq.cloud:8883
2000-01-01 04:00:18.821 MQTTProtocol:connect. Connection error: Write failed after 1 attempts: -29312
2000-01-01 04:00:18.830 Failed to connect to s1.eu.hivemq.cloud:8883: Write failed after 1 attempts: -29312
2000-01-01 04:00:18.836 Failed to connect to broker, retrying in 4 seconds...
2000-01-01 04:00:23.387 Connecting to broker...
2000-01-01 04:00:23.389 MQTTClient:connect. Connecting to s1.eu.hivemq.cloud:8883
2000-01-01 04:00:38.128 Connected (session_present=False)
2000-01-01 04:00:38.130 Connected with code 0
2000-01-01 04:00:38.140 Starting receive loop
2000-01-01 04:00:38.144 Starting keep-alive loop
2000-01-01 04:00:38.149 Subscribe request sent for topic test/test with PID 1
2000-01-01 04:00:38.150 Connected to broker
2000-01-01 04:00:38.154 Starting periodic publish task...
2000-01-01 04:00:38.407 SUBACK received for PID 1 with QoS 1
2000-01-01 04:00:38.409 Subscription to test/test confirmed
2000-01-01 04:00:38.446 PUBACK received for PID 2
2000-01-01 04:00:39.576 PUBACK received for PID 3
2000-01-01 04:00:40.716 PUBACK received for PID 4
```

### Changed

- QoS 1 `publish()` method now tracks PUBACKs with a simple in-memory dict.
- PUBACKs now clear pending messages, unblocking retries and marking them acknowledged.

### Fixed

- Prevented multiple in-flight QoS 1 messages with conflicting PIDs.
- Enhanced error handling for MQTT connection failures and timeouts.
-

## [1.0.1] - 2025-05-16

### Changed

- Transform all MQTT callbacks to async functions.
- All callbacks are now passed the client instance as the first argument.

### Added

- changelog file.
- New callback for `ping` events. Ping callback signature is `async def on_ping(client, request: bool, rtt_ms: int)`.
- Demo prints out ping RTT and RAM usage

```bash
2000-01-01 00:01:33.406 Published message to micropython/test with PID 69
2000-01-01 00:01:35.454 Published message to micropython/test with PID 71
2000-01-01 00:01:35.498 PUBACK received for PID 71
2000-01-01 00:01:35.745     Free RAM...........:   1910 Kb
2000-01-01 00:01:35.747     Allocated RAM......:     86 Kb
2000-01-01 00:01:35.749     Lowest Free RAM....:   1888 Kb
2000-01-01 00:01:35.756     Max Allocated RAM..:    109 Kb
2000-01-01 00:01:36.459 Publishing: Periodic message #71 from MicroPython
2000-01-01 00:01:36.476 Published message to micropython/test with PID 72
2000-01-01 00:01:37.589 PING sent to broker
2000-01-01 00:01:37.626 PING response received from broker in 46 ms
2000-01-01 00:01:38.520 Publishing: Periodic message #73 from MicroPython
2000-01-01 00:01:38.533 Published message to micropython/test with PID 74
2000-01-01 00:01:38.571 PUBACK received for PID 74
```

## [1.0.0] - 2025-05-15

### Added

- Initial public release.