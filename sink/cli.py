#!/usr/bin/env python3
"""Push set_config downlink commands to a device via MQTT."""

import argparse
import json
import sys
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "firmware" / "config.json"
AGGRESSIVE_CONFIG = ROOT / "firmware" / "config.aggressive.json"


def push_config(broker, port, device_id, config_path, overrides=None):
    with open(config_path) as f:
        config = json.load(f)
    command = {"cmd": "set_config"}
    command.update(config)
    if overrides:
        command.update(overrides)
    command["device_id"] = device_id

    topic = "vixiot/%s/cmd" % device_id
    ack_topic = "vixiot/%s/cmd/ack" % device_id
    ack_received = []

    def on_message(client, userdata, msg):
        if msg.topic == ack_topic:
            ack_received.append(json.loads(msg.payload.decode()))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(broker, port, keepalive=60)
    client.subscribe(ack_topic, qos=1)
    client.loop_start()
    client.publish(topic, json.dumps(command), qos=1)
    import time
    time.sleep(2)
    client.loop_stop()
    client.disconnect()
    if ack_received:
        print(json.dumps(ack_received[0], indent=2))
        return 0 if ack_received[0].get("success") else 1
    print("No ack received within timeout", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(description="Push config downlink to VixIoT device")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device", default="espresso-001")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--aggressive", action="store_true", help="Use firmware/config.aggressive.json (all faults, fast intervals)")
    parser.add_argument("--enable-scaling", action="store_true")
    parser.add_argument("--sample-interval-ms", type=int, default=None)
    parser.add_argument("--publish-interval-s", type=int, default=None)
    args = parser.parse_args()

    config_path = str(AGGRESSIVE_CONFIG) if args.aggressive else args.config
    overrides = {}
    if args.enable_scaling:
        overrides["irregularities"] = {"scaling": {"enabled": True, "mtbf_hours": 1, "severity": 0.8}}
    if args.sample_interval_ms:
        overrides["sample_interval_ms"] = args.sample_interval_ms
    if args.publish_interval_s:
        overrides["publish_interval_s"] = args.publish_interval_s

    sys.exit(push_config(args.broker, args.port, args.device, config_path, overrides or None))


if __name__ == "__main__":
    main()
