"""ESP32-S3 MicroPython main loop."""

import json

from core.runtime import DeviceRuntime
from core.schema import build_state_message

try:
    from firmware.platform import clock, mqtt, storage, wifi
except ImportError:
    import clock, mqtt, storage, wifi  # MicroPython: platform/*.py on device path

try:
    import secrets
except ImportError:
    secrets = None


def _topics(device_id):
    base = "vixiot/%s" % device_id
    return {
        "telemetry": base + "/telemetry",
        "state": base + "/state",
        "cmd": base + "/cmd",
        "cmd_ack": base + "/cmd/ack",
    }


def _load_initial_config():
    defaults = storage.load_config()
    if defaults is None:
        try:
            with open("config.json", "r") as f:
                defaults = json.load(f)
        except Exception:
            defaults = {}
    device_id = getattr(secrets, "DEVICE_ID", "espresso-001") if secrets else "espresso-001"
    if defaults and "device_id" not in defaults:
        defaults["device_id"] = device_id
    return defaults or {"device_id": device_id}


def main():
    cfg = _load_initial_config()
    runtime = DeviceRuntime(cfg)
    runtime.buffer.load_records(storage.load_buffer())

    if secrets:
        wifi.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
    clock.sync_ntp()

    device_id = runtime.config["device_id"]
    topics = _topics(device_id)

    client = mqtt.MqttClient(
        device_id,
        getattr(secrets, "MQTT_BROKER", "localhost") if secrets else "localhost",
        port=getattr(secrets, "MQTT_PORT", 1883) if secrets else 1883,
        user=getattr(secrets, "MQTT_USER", None) if secrets else None,
        password=getattr(secrets, "MQTT_PASSWORD", None) if secrets else None,
    )

    def on_cmd(topic, msg):
        try:
            command = json.loads(msg)
            ack = runtime.handle_command(command)
            if command.get("cmd") == "set_config" and ack.get("success"):
                storage.save_config(runtime.config)
            client.publish(topics["cmd_ack"], json.dumps(ack), qos=1)
        except Exception as e:
            client.publish(
                topics["cmd_ack"],
                json.dumps({"success": False, "message": str(e)}),
                qos=1,
            )

    client.set_callback(on_cmd)
    birth = json.dumps(build_state_message(device_id, "online", clock.now_iso()))
    lwt = json.dumps(build_state_message(device_id, "offline", clock.now_iso()))
    client.connect(lwt_topic=topics["state"], lwt_payload=lwt)
    client.subscribe(topics["cmd"])
    client.publish(topics["state"], birth, retain=True, qos=1)

    loop_ms = 100
    while True:
        client.check_msg()
        messages = runtime.tick(loop_ms, clock.now_iso())
        for payload in messages:
            def _pub(p, c=client, t=topics["telemetry"]):
                c.publish(t, json.dumps(p), qos=1)
            runtime.enqueue_or_publish(payload, _pub)
            storage.save_buffer(runtime.buffer.dump_records())
        clock.sleep_ms(loop_ms)


if __name__ == "__main__":
    main()
