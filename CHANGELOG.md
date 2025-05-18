# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog] and this project adheres to [Semantic Versioning].

## [Unreleased]

## [1.0.3] - 2025-05-18

### Added

- Device send statistics to track the number of messages sent, received, and acknowledged, etc.
    - We can subscribe to the `micropython/stats` topic to receive the statistics.
    - To display the statistics in a nice way in the terminal, use:
      ```bash
       mosquitto_sub \
      --host <host> \
      --port <port> \
      -u <username> -P <password> \
      -t micropython/stats -q 1 |
      while read -r line; do
        date
        echo "$line" | jq -r '
          to_entries[] |
          .key as $section |
          .value | to_entries | sort_by(.key)[] |
          "\($section) | \(.key) | \(.value)"
        ' | column -t -s '|'
        echo
      done
      ```
- Enhance robustness on the `main()` application. Clean and organize the code.
- Add client statistics functionality to track the number of messages sent, received, and acknowledged.
- Tested under very low Wi-Fi signal conditions:
    - The device was placed in a location with very low Wi-Fi signal strength.
    - The device was able to connect to the broker and publish messages, but with high latency and packet drops.
    - The device was able to reconnect to the broker after a network disconnect.
- Notice the very low Wi-Fi signal as of -96 dBm. This is a good test case to see how the library handles low signal
  strength.
- ⚠️ At this signal level, expect:
    - Very high latency and jitter
    - Frequent packet drops, making MQTT with QoS > 0 unreliable
    - Difficulty maintaining TCP connections
    - Possible disconnects during idle periods

### Changed

- QoS 1 `publish()` method now tracks PUBACKs with a simple in-memory dict.
- PUBACKs now clear pending messages, unblocking retries and marking them acknowledged.

### Fixed

- Prevented multiple in-flight QoS 1 messages with conflicting PIDs.
- Enhanced error handling for MQTT connection failures and timeouts.
- Remove invalid `raise`
- Fix PID generation being called twice.

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