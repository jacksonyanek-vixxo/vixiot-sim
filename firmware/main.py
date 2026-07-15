"""ESP32-S3 MicroPython main loop."""

import json

from core.runtime import DeviceRuntime
from core.schema import build_state_message

try:
    from firmware.platform import clock, mqtt, storage, wifi
except ImportError:
    import clock, mqtt, storage, wifi  # MicroPython: platform/*.py on device path

try:
    import led
except ImportError:
    led = None

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


def _make_led():
    if led is None:
        return None
    return led.create_from_secrets(secrets)


def _tick_led(status_led):
    if status_led:
        status_led.tick()


def _idle_blink(status_led, loop_ms=100):
    """Keep blinking the status LED (e.g. after WiFi/MQTT failure)."""
    while True:
        _tick_led(status_led)
        clock.sleep_ms(loop_ms)


def _fail(status_led, state, message):
    print("FATAL:", message)
    if status_led and led:
        status_led.set_state(state)
        _idle_blink(status_led)


def main():
    status_led = _make_led()
    if status_led:
        status_led.self_test()
        status_led.set_state(led.BOOT)

    print("boot: loading config")
    cfg = _load_initial_config()
    runtime = DeviceRuntime(cfg)
    runtime.buffer.load_records(storage.load_buffer())

    if secrets:
        print("boot: wifi connect", repr(secrets.WIFI_SSID))
        if status_led:
            status_led.set_state(led.WIFI_CONNECTING)
        wifi_ok = wifi.connect(
            secrets.WIFI_SSID,
            secrets.WIFI_PASSWORD,
            tick_fn=lambda: _tick_led(status_led),
        )
        if not wifi_ok:
            _fail(status_led, led.ERROR, "WiFi connect failed")
            return
        print("boot: wifi ok")
        try:
            import network
            print("boot: ip", network.WLAN(network.STA_IF).ifconfig())
        except Exception:
            pass
        if status_led:
            status_led.set_state(led.WIFI_OK)
            for _ in range(8):
                _tick_led(status_led)
                clock.sleep_ms(50)
    elif status_led:
        status_led.set_state(led.WIFI_OK)

    print("boot: ntp sync")
    clock.sync_ntp(tick_fn=lambda: _tick_led(status_led))

    device_id = runtime.config["device_id"]
    topics = _topics(device_id)
    broker = getattr(secrets, "MQTT_BROKER", "localhost") if secrets else "localhost"
    port = getattr(secrets, "MQTT_PORT", 1883) if secrets else 1883
    use_ssl = getattr(secrets, "MQTT_SSL", port == 8883) if secrets else False
    print("boot: mqtt broker", broker, port, "ssl=", use_ssl)

    if status_led:
        status_led.set_state(led.MQTT_CONNECTING)

    client = mqtt.MqttClient(
        device_id,
        broker,
        port=port,
        user=getattr(secrets, "MQTT_USER", None) if secrets else None,
        password=getattr(secrets, "MQTT_PASSWORD", None) if secrets else None,
        ssl=use_ssl,
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
    mqtt_ok = client.connect(
        lwt_topic=topics["state"],
        lwt_payload=lwt,
        tick_fn=lambda: _tick_led(status_led),
        sleep_fn=clock.sleep_ms,
    )
    if not mqtt_ok:
        _fail(status_led, led.ERROR, "MQTT connect failed — check broker, port, SSL, credentials")
        return

    client.subscribe(topics["cmd"])
    client.publish(topics["state"], birth, retain=True, qos=1)
    print("boot: online — simulation running")

    if status_led:
        status_led.set_state(led.RUNNING)

    loop_ms = 100
    pub_count = 0
    while True:
        _tick_led(status_led)
        client.check_msg()
        messages = runtime.tick(loop_ms, clock.now_iso())
        faults = runtime.irregularities.active_faults()
        if status_led:
            if faults:
                status_led.set_state(led.FAULT)
            elif status_led.state == led.FAULT:
                status_led.set_state(led.RUNNING)
        for payload in messages:
            def _pub(p, c=client, t=topics["telemetry"]):
                c.publish(t, json.dumps(p), qos=1)
            runtime.enqueue_or_publish(payload, _pub)
            storage.save_buffer(runtime.buffer.dump_records())
            pub_count += 1
            if pub_count <= 3 or pub_count % 10 == 0:
                print("pub seq=%s event=%s faults=%s" % (
                    payload.get("seq"), payload.get("event"), payload.get("active_faults")))
        clock.sleep_ms(loop_ms)


if __name__ == "__main__":
    main()
