import json


class Config:
    def __init__(self):
        self.wifi_ssid = ""
        self.wifi_password = ""
        self.mqtt_broker = ""
        self.mqtt_port = 0
        self.mqtt_username = ""
        self.mqtt_password = ""
        self.mqtt_tls = False

    def load(self):
        try:
            with open('config.json', 'r') as config_file:
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

    def save(self):
        config = {
            "wifi": {
                "ssid": self.wifi_ssid,
                "password": self.wifi_password
            },
            "mqtt": {
                "broker": self.mqtt_broker,
                "port": self.mqtt_port,
                "username": self.mqtt_username,
                "password": self.mqtt_password,
                "tls": self.mqtt_tls
            }
        }
        with open('config.json', 'w') as config_file:
            json.dump(config, config_file, indent=4)
        print("Config file created with default values.")
        return config
