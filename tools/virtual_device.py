#!/usr/bin/env python3
"""CPython virtual device runner for end-to-end demo without hardware."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.runtime import DeviceRuntime
from core.schema import build_state_message


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(path):
    if path and Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Virtual espresso machine MQTT publisher")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device", default="espresso-001")
    parser.add_argument("--config", default=str(ROOT / "firmware" / "config.json"))
    parser.add_argument("--fast", action="store_true", help="Use 1s publish interval for demo")
    parser.add_argument("--aggressive", action="store_true", help="Use firmware/config.aggressive.json")
    args = parser.parse_args()

    config_path = args.config
    if args.aggressive:
        config_path = str(ROOT / "firmware" / "config.aggressive.json")
    cfg = load_config(config_path)
    cfg["device_id"] = args.device
    if args.fast:
        cfg["sample_interval_ms"] = 500
        cfg["publish_interval_s"] = 5

    runtime = DeviceRuntime(cfg)
    device_id = runtime.config["device_id"]
    base = "vixiot/%s" % device_id
    topics = {
        "telemetry": base + "/telemetry",
        "state": base + "/state",
        "cmd": base + "/cmd",
        "cmd_ack": base + "/cmd/ack",
    }

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device_id)
    connected = {"ok": False}

    def on_connect(c, userdata, flags, reason_code, properties):
        connected["ok"] = True
        c.subscribe(topics["cmd"], qos=1)
        birth = json.dumps(build_state_message(device_id, "online", now_iso()))
        c.publish(topics["state"], birth, retain=True, qos=1)
        print("[virtual] online as %s" % device_id)

    def on_message(c, userdata, msg):
        if msg.topic != topics["cmd"]:
            return
        command = json.loads(msg.payload.decode())
        ack = runtime.handle_command(command)
        c.publish(topics["cmd_ack"], json.dumps(ack), qos=1)
        print("[virtual] config applied: %s" % ack.get("success"))

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(
        topics["state"],
        json.dumps(build_state_message(device_id, "offline", now_iso())),
        qos=1,
        retain=True,
    )
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    for _ in range(50):
        if connected["ok"]:
            break
        time.sleep(0.1)

    print("[virtual] publishing to %s (Ctrl+C to stop)" % topics["telemetry"])
    loop_ms = 100
    try:
        while True:
            messages = runtime.tick(loop_ms, now_iso())

            def publish_fn(payload):
                client.publish(topics["telemetry"], json.dumps(payload), qos=1)

            for payload in messages:
                runtime.enqueue_or_publish(payload, publish_fn)
                print(
                    "[virtual] pub seq=%s event=%s faults=%s"
                    % (payload["seq"], payload["event"], payload.get("active_faults"))
                )
            time.sleep(loop_ms / 1000.0)
    except KeyboardInterrupt:
        offline = json.dumps(build_state_message(device_id, "offline", now_iso()))
        client.publish(topics["state"], offline, retain=True, qos=1)
        client.loop_stop()
        client.disconnect()
        print("[virtual] stopped")


if __name__ == "__main__":
    main()
