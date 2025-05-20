![Keep a Changelog](https://img.shields.io/badge/changelog-keep-blue?style=flat-square)

[Keep a Changelog]: https://keepachangelog.com/en/1.0.0/

[Semantic Versioning]: https://semver.org/spec/v2.0.0.html

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog] and this project adheres to [Semantic Versioning].

## [Unreleased]

## [1.0.4] - 2025-05-20

### Added

- Support to `clean_session` parameter in the class constructor.
- Support to last will message in the class constructor.
- Integrated [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.
    - Added optional [dev] dependencies in pyproject.toml for development tools:
    - ruff for linting and formatting
    - pre-commit for enforcing code quality on commits

### Changed

- Reorganized `CHANGELOG.md` with badges, proper Markdown formatting, and clarified descriptions for all past releases.
- Reformatted codebase to comply with Ruff's default style rules.
- Updated pyproject.toml to follow the latest Ruff configuration structure ([tool.ruff.lint] instead of top-level
  extend-select).
- Disabled Ruff rule RUF012 to maintain MicroPython compatibility (no ClassVar).
- The main application now publishes a copy of each stats message to /test/test, creating a feedback loop for
  stress-testing both publish and subscribe paths.

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
        - You will see a nice table with the statistics such as:
          ```bash
            Tue May 20 00:15:08 -03 2025
            client    _id                     esp32_client_8378
            client    bytes_received          1337
            client    bytes_sent              21351635
            client    connections_failed      12
            client    connections_sent        18
            client    packets_received        140
            client    packets_sent            155652
            client    ping_received_count     18710
            client    ping_rtt_ms             70
            client    ping_sent_count         18713
            client    pub_fail_count          5
            client    pub_ok_count            155647
            client    pub_package_avg_size    95
            client    pub_rtt_ms              121
            client    sub_package_avg_size    9
            wifi      ip                      192.168.86.21
            wifi      mac                     c8:c9:a3:d4:85:ec
            wifi      signal                  -79
            wifi      signal_lowest           -98
            uptime    uptime                  1d 18h 6m 19s
            uptime    uptime_sec              151579
            ram       allocated               40736
            ram       free                    4068960
            ram       free_lowest             3932192
            ram       max_allocated           112000

- Refactored `main()` for robustness and clarity; added support for client statistics reporting.
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
- Removed invalid raise statement
- Fixed PID generation being called twice.

## [1.0.1] - 2025-05-16

### Changed

- Transform all MQTT callbacks to async functions.
- All callbacks are now passed the client instance as the first argument.

### Added

- Changelog file.
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

