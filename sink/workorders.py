"""Work-order manager: fault -> WO with dedup and close-on-clear."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.events_catalog import pairing_group

DEFAULT_WO_PATH = Path(__file__).parent / "data" / "workorders.jsonl"


class WorkOrderManager:
    def __init__(self, publish_fn=None, persist_path=None, persist=True):
        self._open = {}
        self._publish = publish_fn
        self._path = Path(persist_path) if persist_path else DEFAULT_WO_PATH
        self._persist_enabled = persist
        if self._persist_enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _now(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _persist(self, record):
        if not self._persist_enabled:
            return
        with open(self._path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def _emit(self, record):
        self._persist(record)
        if self._publish:
            self._publish(record)

    def _event_severity(self, severity):
        if severity == "Fatal":
            return "critical"
        if severity == "Error":
            return "high"
        if severity == "Warning":
            return "medium"
        return "low"

    def process_telemetry(self, payload):
        device_id = payload["device_id"]
        faults = set(payload.get("active_faults") or [])
        equipment = payload.get("equipment_type", "super_automatic_espresso")
        seq = payload.get("seq")
        key_prefix = device_id

        for fault in faults:
            key = (key_prefix, fault)
            if key in self._open:
                continue
            wo = {
                "wo_id": str(uuid.uuid4()),
                "device_id": device_id,
                "equipment_type": equipment,
                "fault": fault,
                "severity": "high" if fault in (
                    "pump_degradation", "clogged_group", "heater_degradation"
                ) else "medium",
                "opened_at": self._now(),
                "closed_at": None,
                "status": "open",
                "trigger_seq": seq,
                "action": "created",
                "source": "fault",
            }
            self._open[key] = wo
            self._emit(wo)
            print("[WO OPEN] %s fault=%s wo_id=%s" % (device_id, fault, wo["wo_id"]))

        to_close = []
        for key, wo in self._open.items():
            if key[0] == key_prefix and len(key) == 2 and key[1] not in faults:
                to_close.append(key)

        for key in to_close:
            wo = self._open.pop(key)
            closed = dict(wo)
            closed["status"] = "closed"
            closed["closed_at"] = self._now()
            closed["action"] = "closed"
            self._emit(closed)
            print("[WO CLOSE] %s fault=%s wo_id=%s" % (key[0], key[1], wo["wo_id"]))

    def process_event(self, payload):
        event = payload.get("event") or {}
        transition = event.get("transition")
        severity = event.get("severity")
        if transition not in ("raised", "cleared"):
            return

        device_id = payload["device_id"]
        equipment = payload.get("equipment_type", "super_automatic_espresso")
        seq = payload.get("seq")
        number = event.get("number")
        module = event.get("module", "Gui")
        group = pairing_group(number)
        key = (device_id, "event", group, module)

        if transition == "raised":
            if severity not in ("Error", "Fatal"):
                return
            if key in self._open:
                return
            wo = {
                "wo_id": str(uuid.uuid4()),
                "device_id": device_id,
                "equipment_type": equipment,
                "fault": event.get("name"),
                "event_number": number,
                "event_name": event.get("name"),
                "event_category": event.get("category"),
                "module": module,
                "severity": self._event_severity(severity),
                "opened_at": self._now(),
                "closed_at": None,
                "status": "open",
                "trigger_seq": seq,
                "action": "created",
                "source": "event",
            }
            self._open[key] = wo
            self._emit(wo)
            print(
                "[WO OPEN] %s event=%s module=%s wo_id=%s"
                % (device_id, event.get("name"), module, wo["wo_id"])
            )
            return

        if key not in self._open:
            return
        wo = self._open.pop(key)
        closed = dict(wo)
        closed["status"] = "closed"
        closed["closed_at"] = self._now()
        closed["action"] = "closed"
        self._emit(closed)
        print(
            "[WO CLOSE] %s event=%s module=%s wo_id=%s"
            % (device_id, event.get("name"), module, wo["wo_id"])
        )
