"""MQTT platform adapter (umqtt on MicroPython)."""

try:
    from umqtt.simple import MQTTClient
    _HAS_UMQTT = True
except ImportError:
    _HAS_UMQTT = False

try:
    import socket
except ImportError:
    socket = None

try:
    import ssl as _ssl
except ImportError:
    _ssl = None


class MqttClient:
    def __init__(self, client_id, broker, port=1883, user=None, password=None, ssl=False):
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self._client = None
        self._connected = False
        self._callback = None

    def set_callback(self, fn):
        self._callback = fn

    def _probe_broker(self, timeout_s=8, tick_fn=None, sleep_fn=None):
        """TCP reachability check with optional LED tick between attempts."""
        if not socket:
            return True
        try:
            import time

            end = time.ticks_add(time.ticks_ms(), int(timeout_s * 1000))
        except Exception:
            return True
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            if tick_fn:
                tick_fn()
            try:
                addr = socket.getaddrinfo(self.broker, self.port)[0][-1]
                s = socket.socket()
                s.settimeout(2)
                s.connect(addr)
                s.close()
                return True
            except Exception:
                if sleep_fn:
                    sleep_fn(150)
                else:
                    try:
                        time.sleep_ms(150)
                    except Exception:
                        pass
        return False

    def connect(self, lwt_topic=None, lwt_payload=None, timeout_s=12, tick_fn=None, sleep_fn=None):
        if not _HAS_UMQTT:
            print("MQTT: umqtt.simple missing — running without broker")
            self._connected = True
            return True

        if not self._probe_broker(timeout_s, tick_fn=tick_fn, sleep_fn=sleep_fn):
            print("MQTT: broker unreachable %s:%s" % (self.broker, self.port))
            self._connected = False
            return False

        if tick_fn:
            tick_fn()

        kwargs = {
            "client_id": self.client_id,
            "server": self.broker,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "keepalive": 60,
        }
        if self.ssl:
            kwargs["ssl"] = True
            if _ssl:
                # ESP32 lacks full CA bundle; skip verify for HiveMQ Cloud demo
                kwargs["ssl_params"] = {
                    "cert_reqs": _ssl.CERT_NONE,
                    "server_hostname": self.broker,
                }

        self._client = MQTTClient(**kwargs)
        if lwt_topic:
            self._client.set_last_will(lwt_topic, lwt_payload or "offline", retain=True, qos=1)
        self._client.set_callback(self._on_message)
        try:
            if socket and hasattr(socket, "setdefaulttimeout"):
                socket.setdefaulttimeout(10)
            self._client.connect()
            self._connected = True
            print("MQTT: connected (ssl=%s)" % self.ssl)
            return True
        except Exception as e:
            print("MQTT: connect failed —", e)
            self._connected = False
            self._client = None
            return False

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
        if not _HAS_UMQTT or not self._client:
            return
        data = payload if isinstance(payload, bytes) else payload.encode()
        self._client.publish(topic, data, retain=retain, qos=qos)

    def check_msg(self):
        if self._client:
            try:
                self._client.check_msg()
            except Exception:
                pass

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
