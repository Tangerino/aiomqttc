try:
    import network
except ImportError:
    # For platforms that don't support network (like MicroPython)
    network = None


def wifi(ssid: str, password: str) -> None:
    if network is None:
        return
    sta_if = network.WLAN(network.STA_IF)
    if sta_if.isconnected():
        print("Already connected to WiFi network, disconnecting...")
        sta_if.disconnect()
        sta_if.active(False)
    print("Connecting to WiFi network...")
    sta_if.active(True)
    sta_if.connect(ssid, password)
    while not sta_if.isconnected():
        pass

    print("Connected to WiFi network with IP address:", sta_if.ifconfig()[0])
    print(f"Signal strength: {sta_if.status('rssi')} dBm")
