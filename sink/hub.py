"""Shared MQTT sink and in-memory dashboard state."""

import json
import threading
from collections import defaultdict, deque
from pathlib import Path

import jsonschema

from sink.mqtt_util import configure_client, connect_client, make_client
from sink.workorders import WorkOrderManager

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema" / "telemetry.schema.json"
EVENT_SCHEMA_PATH = ROOT / "schema" / "event.schema.json"
DATA_DIR = ROOT / "data"
TELEMETRY_PATH = DATA_DIR / "telemetry.jsonl"
EVENTS_PATH = DATA_DIR / "events.jsonl"
STATE_PATH = DATA_DIR / "state.jsonl"


def load_schema(path=SCHEMA_PATH):
    with open(path) as schema_file:
        return json.load(schema_file)


def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as output:
        output.write(json.dumps(record) + "\n")


def build_set_config(device_id, config):
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    command = dict(config)
    command["cmd"] = "set_config"
    command["device_id"] = device_id
    return command


class SinkHub:
    """Own MQTT, persistence, work orders, and current per-device state."""

    def __init__(
        self,
        broker="localhost",
        port=1883,
        device_filter=None,
        username=None,
        password=None,
        tls=False,
        client=None,
        telemetry_path=TELEMETRY_PATH,
        events_path=EVENTS_PATH,
        state_path=STATE_PATH,
        workorder_path=None,
        persist=True,
        history_size=500,
        broadcast=None,
    ):
        self.broker = broker
        self.port = port
        self.device_filter = device_filter
        self.schema = load_schema()
        self.event_schema = load_schema(EVENT_SCHEMA_PATH)
        self.telemetry_path = Path(telemetry_path)
        self.events_path = Path(events_path)
        self.state_path = Path(state_path)
        self.persist = persist
        self._broadcast = broadcast
        self._lock = threading.RLock()
        self._history = defaultdict(lambda: deque(maxlen=history_size))
        self._event_history = defaultdict(lambda: deque(maxlen=history_size))
        self._snapshots = {}
        self._states = {}
        self._configs = {}
        self._pending_configs = {}
        self._acks = {}
        self._workorders = defaultdict(lambda: {"open": {}, "closed": []})

        self._client = client or make_client()
        configure_client(self._client, username, password, tls)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._wo = WorkOrderManager(
            publish_fn=self._handle_workorder,
            persist_path=workorder_path,
            persist=persist,
        )

    @property
    def client(self):
        return self._client

    def set_broadcast(self, callback):
        self._broadcast = callback

    def _emit(self, event_type, device_id, payload):
        callback = self._broadcast
        if callback:
            callback({"type": event_type, "device_id": device_id, "data": payload})

    def _handle_workorder(self, record):
        device_id = record["device_id"]
        with self._lock:
            orders = self._workorders[device_id]
            if record["status"] == "open":
                orders["open"][record["wo_id"]] = dict(record)
            else:
                orders["open"].pop(record["wo_id"], None)
                orders["closed"].append(dict(record))
        self._client.publish(
            "vixiot/%s/workorder" % device_id, json.dumps(record), qos=1
        )
        self._emit("workorder", device_id, record)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        print("[sink] connected to %s:%s" % (self.broker, self.port))
        client.subscribe("vixiot/+/telemetry", qos=1)
        client.subscribe("vixiot/+/event", qos=1)
        client.subscribe("vixiot/+/state", qos=1)
        client.subscribe("vixiot/+/cmd/ack", qos=1)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("[sink] invalid JSON on %s" % topic)
            return

        parts = topic.split("/")
        if len(parts) < 3:
            return
        device_id = parts[1]
        channel = "/".join(parts[2:])
        if self.device_filter and device_id != self.device_filter:
            return

        if channel == "state":
            self.ingest_state(device_id, payload)
        elif channel == "telemetry":
            self.ingest_telemetry(device_id, payload)
        elif channel == "event":
            self.ingest_event(device_id, payload)
        elif channel == "cmd/ack":
            self.ingest_ack(device_id, payload)

    def ingest_state(self, device_id, payload):
        status = payload.get("status", "unknown")
        with self._lock:
            self._states[device_id] = dict(payload)
        if self.persist:
            append_jsonl(self.state_path, payload)
        print("[state] %s -> %s" % (device_id, status))
        self._emit("state", device_id, payload)

    def ingest_telemetry(self, device_id, payload):
        try:
            jsonschema.validate(payload, self.schema)
        except jsonschema.ValidationError as error:
            print("[sink] schema validation failed: %s" % error)
            return False
        if payload.get("device_id") != device_id:
            print("[sink] device_id does not match topic: %s" % device_id)
            return False

        record = dict(payload)
        with self._lock:
            self._snapshots[device_id] = record
            self._history[device_id].append(record)
        if self.persist:
            append_jsonl(self.telemetry_path, record)
        self._wo.process_telemetry(record)
        print(
            "[telemetry] %s seq=%s state=%s faults=%s"
            % (
                device_id,
                record.get("seq"),
                record.get("state"),
                record.get("active_faults") or [],
            )
        )
        self._emit("telemetry", device_id, record)
        return True

    def ingest_event(self, device_id, payload):
        try:
            jsonschema.validate(payload, self.event_schema)
        except jsonschema.ValidationError as error:
            print("[sink] event schema validation failed: %s" % error)
            return False
        if payload.get("device_id") != device_id:
            print("[sink] event device_id does not match topic: %s" % device_id)
            return False

        record = dict(payload)
        with self._lock:
            self._event_history[device_id].append(record)
        if self.persist:
            append_jsonl(self.events_path, record)
        self._wo.process_event(record)
        event = record.get("event", {})
        print(
            "[event] %s seq=%s %s %s module=%s"
            % (
                device_id,
                record.get("seq"),
                event.get("name"),
                event.get("transition"),
                event.get("module"),
            )
        )
        self._emit("event", device_id, record)
        return True

    def ingest_ack(self, device_id, payload):
        ack = dict(payload)
        with self._lock:
            self._acks[device_id] = ack
            pending = self._pending_configs.pop(device_id, None)
            if ack.get("success"):
                applied = ack.get("config", pending)
                if applied is not None:
                    self._configs[device_id] = dict(applied)
        self._emit("cmd_ack", device_id, ack)

    def set_config(self, device_id, config):
        command = build_set_config(device_id, config)
        applied_config = {
            key: value
            for key, value in command.items()
            if key not in ("cmd", "device_id")
        }
        with self._lock:
            self._pending_configs[device_id] = applied_config
        self._client.publish(
            "vixiot/%s/cmd" % device_id, json.dumps(command), qos=1
        )
        return command

    def devices(self):
        with self._lock:
            ids = (
                set(self._states)
                | set(self._snapshots)
                | set(self._configs)
                | set(self._workorders)
            )
            return [
                {
                    "device_id": device_id,
                    "online": self._states.get(device_id, {}).get("status") == "online",
                    "status": self._states.get(device_id, {}).get("status", "unknown"),
                }
                for device_id in sorted(ids)
            ]

    def snapshot(self, device_id):
        with self._lock:
            telemetry = self._snapshots.get(device_id)
            state = self._states.get(device_id)
            if telemetry is None and state is None:
                return None
            result = dict(telemetry or {})
            result.update(
                {
                    "device_id": device_id,
                    "online": (state or {}).get("status") == "online",
                    "connection_status": (state or {}).get("status", "unknown"),
                    "connection_state": dict(state) if state else None,
                    "config": self._configs.get(device_id),
                    "cmd_ack": self._acks.get(device_id),
                }
            )
            return result

    def telemetry(self, device_id):
        with self._lock:
            return list(self._history.get(device_id, ()))

    def events(self, device_id):
        with self._lock:
            return list(self._event_history.get(device_id, ()))

    def workorders(self, device_id):
        with self._lock:
            orders = self._workorders.get(device_id)
            if not orders:
                return {"open": [], "closed": []}
            return {
                "open": list(orders["open"].values()),
                "closed": list(orders["closed"]),
            }

    def backfill(self):
        return {
            device["device_id"]: {
                "snapshot": self.snapshot(device["device_id"]),
                "telemetry": self.telemetry(device["device_id"]),
                "events": self.events(device["device_id"]),
                "workorders": self.workorders(device["device_id"]),
            }
            for device in self.devices()
        }

    def connect(self):
        connect_client(self._client, self.broker, self.port)

    def start(self):
        self.connect()
        self._client.loop_start()

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()

    def run(self):
        self.connect()
        print(
            "[sink] listening on vixiot/+/telemetry, vixiot/+/event, vixiot/+/state, "
            "and vixiot/+/cmd/ack"
        )
        self._client.loop_forever()


Sink = SinkHub
