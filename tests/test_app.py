"""REST API tests using an in-memory hub and MQTT client."""

import json

from sink.app import create_app
from fastapi.testclient import TestClient
from sink.hub import SinkHub


class FakeMqttClient:
    def __init__(self):
        self.on_connect = None
        self.on_message = None
        self.published = []
        self.subscriptions = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, json.loads(payload), qos))

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))


def telemetry(seq=1):
    return {
        "schema_version": "1.0",
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "timestamp": "2026-07-15T12:00:00Z",
        "seq": seq,
        "event": "telemetry",
        "metrics": {
            "brew_pressure": {"value": 9.1, "unit": "bar", "quality": "good"}
        },
        "counters": {
            "total_shots": 100,
            "shots_since_descale": 20,
            "operating_hours": 12.5,
        },
        "state": "idle",
        "active_faults": [],
    }


def device_event(seq=1, number=20001):
    return {
        "schema_version": "1.0",
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "timestamp": "2026-07-15T12:00:01Z",
        "seq": seq,
        "event": {
            "number": number,
            "name": "Device connected",
            "severity": "Info",
            "category": "Connectivity Events",
            "module": "StatusManager",
            "source": "StatusManager",
            "stateful": True,
            "transition": "momentary",
        },
    }


def make_client():
    mqtt = FakeMqttClient()
    hub = SinkHub(client=mqtt, persist=False)
    hub.ingest_state(
        "espresso-001",
        {
            "schema_version": "1.0",
            "device_id": "espresso-001",
            "timestamp": "2026-07-15T12:00:00Z",
            "status": "online",
        },
    )
    hub.ingest_telemetry("espresso-001", telemetry())
    hub.ingest_telemetry("espresso-001", telemetry(seq=2))
    return TestClient(create_app(hub, manage_hub=False)), mqtt


def test_devices_and_snapshot():
    client, _ = make_client()
    with client:
        devices = client.get("/api/devices")
        assert devices.status_code == 200
        assert devices.json() == [
            {"device_id": "espresso-001", "online": True, "status": "online"}
        ]

        snapshot = client.get("/api/snapshot/espresso-001")
        assert snapshot.status_code == 200
        assert snapshot.json()["seq"] == 2
        assert snapshot.json()["online"] is True
        assert client.get("/api/snapshot/missing").status_code == 404


def test_telemetry_history_and_workorders():
    client, _ = make_client()
    with client:
        history = client.get("/api/telemetry/espresso-001")
        assert [record["seq"] for record in history.json()] == [1, 2]
        assert client.get("/api/workorders/espresso-001").json() == {
            "open": [],
            "closed": [],
        }


def test_events_history_and_ingest():
    client, _ = make_client()
    with client:
        assert client.get("/api/events/espresso-001").json() == []
        hub = client.app.state.hub
        assert hub.ingest_event("espresso-001", device_event()) is True
        events = client.get("/api/events/espresso-001").json()
        assert len(events) == 1
        assert events[0]["event"]["name"] == "Device connected"


def test_config_push_builds_set_config_command():
    client, mqtt = make_client()
    config = {
        "sample_interval_ms": 250,
        "publish_interval_s": 5,
        "irregularities": {
            "scaling": {"enabled": True, "mtbf_hours": 1, "severity": 0.8}
        },
    }
    with client:
        response = client.post("/api/config/espresso-001", json=config)

    assert response.status_code == 200
    topic, command, qos = mqtt.published[-1]
    assert topic == "vixiot/espresso-001/cmd"
    assert qos == 1
    assert command == {
        "cmd": "set_config",
        "device_id": "espresso-001",
        **config,
    }
