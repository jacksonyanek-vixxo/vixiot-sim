# Copy to secrets.py and fill in before flashing firmware.

WIFI_SSID = "your-ssid"
WIFI_PASSWORD = "your-password"

# Local Mosquitto
# MQTT_BROKER = "192.168.1.100"
# MQTT_PORT = 1883
# MQTT_SSL = False
# MQTT_USER = None
# MQTT_PASSWORD = None

# HiveMQ Cloud (TLS required on port 8883)
MQTT_BROKER = "YOUR_CLUSTER.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_SSL = True
MQTT_USER = "your-hivemq-username"
MQTT_PASSWORD = "your-hivemq-password"

DEVICE_ID = "espresso-001"

# Status LED (Seeed XIAO ESP32S3 user LED = GPIO21, active low)
LED_ENABLED = True
LED_PIN = 21
LED_ACTIVE_LOW = True
