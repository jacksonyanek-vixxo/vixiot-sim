"""Shared paho-mqtt TLS/auth helpers for sink tools."""

import ssl

import paho.mqtt.client as mqtt

try:
    import certifi
except ImportError:
    certifi = None


def make_client(client_id=None):
    kwargs = {"callback_api_version": mqtt.CallbackAPIVersion.VERSION2}
    if client_id is not None:
        kwargs["client_id"] = client_id
    return mqtt.Client(**kwargs)


def configure_client(client, username=None, password=None, tls=False):
    if username:
        client.username_pw_set(username, password)
    if tls:
        if certifi:
            client.tls_set(ca_certs=certifi.where())
        else:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)


def connect_client(client, broker, port, keepalive=60):
    client.connect(broker, port, keepalive=keepalive)
