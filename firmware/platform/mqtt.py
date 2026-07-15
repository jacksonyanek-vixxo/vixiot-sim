"""MQTT platform adapter (umqtt on MicroPython)."""

try:
    from umqtt.simple import MQTTClient
    _HAS_UMQTT = True
except ImportError:
    _HAS_UMQTT = False


class MqttClient:
    def __init__(self, client_id, broker, port=1883, user=None, password=None):
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.user = user
        self.password = password
        self._client = None
        self._connected = False
        self._callback = None

    def set_callback(self, fn):
        self._callback = fn

    def connect(self, lwt_topic=None, lwt_payload=None):
        if not _HAS_UMQTT:
            self._connected = True
            return True
        self._client = MQTTClient(
            self.client_id,
            self.broker,
            port=self.port,
            user=self.user,
            password=self.password,
            keepalive=60,
        )
        if lwt_topic:
            self._client.set_last_will(lwt_topic, lwt_payload or "offline", retain=True, qos=1)
        self._client.set_callback(self._on_message)
        self._client.connect()
        self._connected = True
        return True

    def _on_message(self, topic, msg):
        if self._callback:
            try:
                topic_str = topic.decode() if isinstance(topic, bytes) else topic
                msg_str = msg.decode() if isinstance(msg, bytes) else msg
                self._callback(topic_str, msg_str)
            except Exception:
                pass

    def subscribe(self, topic, qos=1):
        if self._client:
            self._client.subscribe(topic, qos=qos)

    def publish(self, topic, payload, retain=False, qos=1):
        if not _HAS_UMQTT:
            return
        data = payload if isinstance(payload, bytes) else payload.encode()
        self._client.publish(topic, data, retain=retain, qos=qos)

    def check_msg(self):
        if self._client:
            self._client.check_msg()

    def disconnect(self):
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    @property
    def connected(self):
        return self._connected
