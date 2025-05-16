# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog] and this project adheres to [Semantic Versioning].

## [Unreleased]
### Added
- 

### Changed
- 

### Fixed
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