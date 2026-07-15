#!/usr/bin/env python3
"""MQTT sink: validate telemetry, persist JSONL, track online/offline, manage work orders."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sink.workorders import WorkOrderManager
SCHEMA_PATH = ROOT / "schema" / "telemetry.schema.json"
DATA_DIR = ROOT / "data"
TELEMETRY_PATH = DATA_DIR / "telemetry.jsonl"
STATE_PATH = DATA_DIR / "state.jsonl"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


class Sink:
    def __init__(self, broker, port, device_filter=None):
        self.broker = broker
        self.port = port
        self.device_filter = device_filter
        self.schema = load_schema()
        self.devices_online = {}
        self._wo = WorkOrderManager(publish_fn=self._publish_workorder)
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _publish_workorder(self, record):
        device_id = record["device_id"]
        topic = "vixiot/%s/workorder" % device_id
        self._client.publish(topic, json.dumps(record), qos=1)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print("[sink] connected to %s:%s" % (self.broker, self.port))
        client.subscribe("vixiot/+/telemetry", qos=1)
        client.subscribe("vixiot/+/state", qos=1)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print("[sink] invalid JSON on %s" % topic)
            return

        parts = topic.split("/")
        if len(parts) < 3:
            return
        device_id = parts[1]
        channel = parts[2]

        if self.device_filter and device_id != self.device_filter:
            return

        if channel == "state":
            status = payload.get("status", "unknown")
            self.devices_online[device_id] = status
            append_jsonl(STATE_PATH, payload)
            print("[state] %s -> %s" % (device_id, status))
            return

        if channel == "telemetry":
            try:
                jsonschema.validate(payload, self.schema)
            except jsonschema.ValidationError as e:
                print("[sink] schema validation failed: %s" % e)
                return
            append_jsonl(TELEMETRY_PATH, payload)
            self._wo.process_telemetry(payload)
            faults = payload.get("active_faults") or []
            print(
                "[telemetry] %s seq=%s state=%s faults=%s"
                % (device_id, payload.get("seq"), payload.get("state"), faults)
            )

    def run(self):
        self._client.connect(self.broker, self.port, keepalive=60)
        print("[sink] listening on vixiot/+/telemetry and vixiot/+/state")
        self._client.loop_forever()


def main():
    parser = argparse.ArgumentParser(description="VixIoT MQTT sink subscriber")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device", default=None, help="Filter to one device_id")
    args = parser.parse_args()
    Sink(args.broker, args.port, args.device).run()


if __name__ == "__main__":
    main()
