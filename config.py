import json


class Config:
    """
    Configuration manager for Wi-Fi and MQTT settings.

    This class handles loading and saving configuration data from/to a `config.json` file.
    It stores Wi-Fi credentials and MQTT broker settings used by the application.

    Attributes:
        wifi_ssid (str): SSID of the Wi-Fi network.
        wifi_password (str): Password for the Wi-Fi network.
        mqtt_broker (str): Hostname or IP of the MQTT broker.
        mqtt_port (int): Port number of the MQTT broker.
        mqtt_username (str): Username for MQTT authentication.
        mqtt_password (str): Password for MQTT authentication.
        mqtt_tls (bool): Whether to use TLS for MQTT connection.
    """

    def __init__(self):
        """
        Initialize the Config object with default (empty) values.
        """
        self.wifi_ssid = ""
        self.wifi_password = ""
        self.mqtt_broker = ""
        self.mqtt_port = 0
        self.mqtt_username = ""
        self.mqtt_password = ""
        self.mqtt_tls = False

    def __repr__(self):
        return f"mqtt_broker={self.mqtt_broker}, mqtt_port={self.mqtt_port})"

    def load(self):
        """
        Load configuration from 'config.json'. If the file is missing or invalid,
        default values are kept and a new config file is created with these defaults.

        Returns:
            Config: The current instance (self) for chaining.
        """
        try:
            with open("config.json") as config_file:
                config = json.load(config_file)
                self.wifi_ssid = config.get("wifi", {}).get("ssid", "")
                self.wifi_password = config.get("wifi", {}).get("password", "")
                self.mqtt_broker = config.get("mqtt", {}).get("broker", "")
                self.mqtt_port = config.get("mqtt", {}).get("port", 0)
                self.mqtt_username = config.get("mqtt", {}).get("username", "")
                self.mqtt_password = config.get("mqtt", {}).get("password", "")
                self.mqtt_tls = config.get("mqtt", {}).get("tls", False)
                print("Config loaded successfully.")

        except Exception as e:
            print(f"Error reading config file: {e}")
            self.save()
        return self

    def save(self):
        """
        Save the current configuration to 'config.json'.

        If the file already exists, it will be overwritten.

        Returns:
            dict: The configuration dictionary that was written to the file.
        """
        config = {
            "wifi": {"ssid": self.wifi_ssid, "password": self.wifi_password},
            "mqtt": {
                "broker": self.mqtt_broker,
                "port": self.mqtt_port,
                "username": self.mqtt_username,
                "password": self.mqtt_password,
                "tls": self.mqtt_tls,
            },
        }
        with open("config.json", "w") as config_file:
            json.dump(config, config_file, indent=4)
        print("Config file created with default values.")
        return config
