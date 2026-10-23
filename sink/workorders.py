"""Work-order manager: fault -> VixxoNow-shaped ticket, with dedup and close-on-clear."""

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _BUSINESS_TZ = ZoneInfo("America/Phoenix")
except Exception:
    _BUSINESS_TZ = timezone.utc

from core.events_catalog import pairing_group

DEFAULT_WO_PATH = Path(__file__).parent / "data" / "workorders.jsonl"

# A new VixxoNow work order is created as Submitted. The number is
# WO-YYYYMMDD-NNNN on the America/Phoenix business day.
HANDOFF_SENT = "Sent to VixxoNow"
HANDOFF_OPENED = "Opened in VixxoNow"
VIXVONOW_OPEN_STATUS = "submitted"
VIXVONOW_OPEN_STATUS_DISPLAY = "Submitted"
ASSET_TYPE = "Brewing"
GROUP_WINDOW_S = 120
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

FAULT_SUMMARIES = {
    "scaling": "Scale is building up in the brew boiler.",
    "grinder_wear": "The grinder is wearing and shot quality is drifting.",
    "pump_degradation": "The brew pump is losing pressure.",
    "clogged_group": "The group head is restricting water flow.",
    "heater_degradation": "A boiler is struggling to hold temperature.",
    "spike": "A sensor reading jumped outside its normal range.",
    "drift": "A sensor reading is slowly moving out of range.",
    "stuck": "A sensor reading has stopped changing.",
    "dropout": "A sensor reading dropped out.",
    "out_of_range": "A sensor reading is outside its normal range.",
    "noise": "A sensor reading is unusually noisy.",
}


def _plain_name(value):
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value or "")
    text = text.replace("_", " ").strip()
    if not text:
        return "Machine issue"
    return text[0].upper() + text[1:]


class WorkOrderManager:
    def __init__(
        self,
        publish_fn=None,
        persist_path=None,
        persist=True,
        promote_delay_s=1.4,
        now_fn=None,
        group_window_s=GROUP_WINDOW_S,
    ):
        self._open = {}
        self._publish = publish_fn
        self._path = Path(persist_path) if persist_path else DEFAULT_WO_PATH
        self._persist_enabled = persist
        self._promote_delay_s = promote_delay_s
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._group_window_s = group_window_s
        self._timers = {}
        self._seq_day = None
        self._seq = 0
        if self._persist_enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _now_dt(self):
        current = self._now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current

    def _now(self):
        return self._now_dt().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _higher_severity(self, left, right):
        if _SEVERITY_RANK.get(right, 0) > _SEVERITY_RANK.get(left, 0):
            return right
        return left

    def _key_id(self, key):
        return "|".join(str(part) for part in key)

    def _refresh_summary(self, ticket):
        active = [issue for issue in ticket.get("issues") or [] if issue.get("active", True)]
        if not active:
            return
        ticket["fault"] = active[0]["name"]
        if len(active) == 1:
            ticket["summary"] = active[0]["summary"]
            return
        ticket["summary"] = "%d issues within 2 minutes: %s" % (
            len(active),
            "; ".join(issue["summary"] for issue in active),
        )

    def _recent_ticket(self, device_id):
        cutoff = self._now_dt() - timedelta(seconds=self._group_window_s)
        best = None
        seen = set()
        for ticket in self._open.values():
            number = ticket["wo_id"]
            if number in seen or ticket.get("device_id") != device_id:
                continue
            seen.add(number)
            opened = datetime.strptime(ticket["sent_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            if opened < cutoff:
                continue
            if best is None or ticket["sent_at"] > best["sent_at"]:
                best = ticket
        return best

    def _allocate_number(self):
        day = datetime.now(_BUSINESS_TZ).strftime("%Y%m%d")
        if day != self._seq_day:
            self._seq_day = day
            self._seq = 0
        self._seq += 1
        # Same shape as a live VixxoNow number, e.g. WO-20261023-1160.
        number = "WO-%s-%04d" % (day, self._seq)
        # Siebel service requests on a VixxoNow ticket are 1- plus 10 digits.
        # 9xxxxxxxxx stays in that shape without copying a live SR.
        sr = "1-%010d" % (9000000000 + self._seq)
        return number, sr

    def _persist(self, record):
        if not self._persist_enabled:
            return
        with open(self._path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def _emit(self, record):
        snapshot = dict(record)
        if record.get("issues") is not None:
            snapshot["issues"] = [dict(issue) for issue in record["issues"]]
        self._persist(snapshot)
        if self._publish:
            self._publish(snapshot)

    def _event_severity(self, severity):
        if severity == "Fatal":
            return "critical"
        if severity == "Error":
            return "high"
        if severity == "Warning":
            return "medium"
        return "low"

    def _summary(self, fault):
        if fault in FAULT_SUMMARIES:
            return FAULT_SUMMARIES[fault]
        return _plain_name(fault)

    def _new_ticket(self, device_id, equipment, fault, severity, seq, source, extra=None):
        number, sr = self._allocate_number()
        now = self._now()
        ticket = {
            "wo_id": number,
            "work_order_number": number,
            "siebel_sr_number": sr,
            "asset_type": ASSET_TYPE,
            "device_id": device_id,
            "equipment_type": equipment,
            "fault": fault,
            "summary": self._summary(fault),
            "severity": severity,
            "sent_at": now,
            "opened_at": now,
            "opened_in_vixxonow_at": None,
            "closed_at": None,
            "status": "open",
            "handoff": "sent",
            "handoff_label": HANDOFF_SENT,
            "vixxonow_status": None,
            "vixxonow_status_display": None,
            "trigger_seq": seq,
            "action": "created",
            "source": source,
            "issues": [],
        }
        if extra:
            ticket.update(extra)
        return ticket

    def _issue(self, key, name, summary, source, module=None):
        return {
            "id": self._key_id(key),
            "name": name,
            "summary": summary,
            "source": source,
            "module": module,
            "active": True,
        }

    def _open_or_group(self, key, device_id, equipment, name, severity, seq, source, module=None, extra=None):
        if key in self._open:
            return None
        summary = self._summary(name) if source == "fault" else _plain_name(name)
        issue = self._issue(key, name, summary, source, module)
        ticket = self._recent_ticket(device_id)
        if ticket is not None:
            ticket["issues"].append(issue)
            ticket["severity"] = self._higher_severity(ticket.get("severity"), severity)
            ticket["action"] = "updated"
            self._refresh_summary(ticket)
            self._open[key] = ticket
            self._emit(ticket)
            print(
                "[WO GROUP] %s %s -> %s"
                % (device_id, name, ticket["work_order_number"])
            )
            return ticket

        wo = self._new_ticket(device_id, equipment, name, severity, seq, source, extra)
        wo["issues"] = [issue]
        self._refresh_summary(wo)
        self._open[key] = wo
        self._emit(wo)
        self._schedule_promote(key)
        print(
            "[WO SENT] %s %s %s"
            % (device_id, name, wo["work_order_number"])
        )
        return wo

    def _schedule_promote(self, key):
        if not self._promote_delay_s:
            return
        timer = threading.Timer(self._promote_delay_s, self._promote, args=(key,))
        timer.daemon = True
        self._timers[key] = timer
        timer.start()

    def _cancel_promote(self, key):
        timer = self._timers.pop(key, None)
        if timer:
            timer.cancel()

    def _promote(self, key):
        self._timers.pop(key, None)
        current = self._open.get(key)
        if not current or current.get("handoff") == "opened":
            return
        updated = dict(current)
        updated["handoff"] = "opened"
        updated["handoff_label"] = HANDOFF_OPENED
        updated["vixxonow_status"] = VIXVONOW_OPEN_STATUS
        updated["vixxonow_status_display"] = VIXVONOW_OPEN_STATUS_DISPLAY
        updated["opened_in_vixxonow_at"] = self._now()
        updated["action"] = "updated"
        self._open[key] = updated
        self._emit(updated)
        print(
            "[WO OPENED] %s %s"
            % (updated["device_id"], updated["work_order_number"])
        )

    def _stamp_opened(self, record, when):
        if record.get("handoff") == "opened":
            return record
        record["handoff"] = "opened"
        record["handoff_label"] = HANDOFF_OPENED
        record["vixxonow_status"] = VIXVONOW_OPEN_STATUS
        record["vixxonow_status_display"] = VIXVONOW_OPEN_STATUS_DISPLAY
        record["opened_in_vixxonow_at"] = when
        return record

    def process_telemetry(self, payload):
        device_id = payload["device_id"]
        faults = set(payload.get("active_faults") or [])
        equipment = payload.get("equipment_type", "super_automatic_espresso")
        seq = payload.get("seq")
        key_prefix = device_id

        for fault in sorted(faults):
            self._open_or_group(
                (key_prefix, fault),
                device_id,
                equipment,
                fault,
                "high" if fault in (
                    "pump_degradation", "clogged_group", "heater_degradation"
                ) else "medium",
                seq,
                "fault",
            )

        to_close = []
        for key in self._open:
            if key[0] == key_prefix and len(key) == 2 and key[1] not in faults:
                to_close.append(key)

        for key in to_close:
            self._deactivate(key)

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
            name = event.get("name")
            self._open_or_group(
                key,
                device_id,
                equipment,
                name,
                self._event_severity(severity),
                seq,
                "event",
                module=module,
                extra={
                    "event_number": number,
                    "event_name": name,
                    "event_category": event.get("category"),
                    "module": module,
                },
            )
            return

        self._deactivate(key)

    def _deactivate(self, key):
        ticket = self._open.get(key)
        if not ticket:
            return
        issue_id = self._key_id(key)
        for issue in ticket.get("issues") or []:
            if issue.get("id") == issue_id:
                issue["active"] = False
        self._open.pop(key, None)
        still_open = any(
            other["wo_id"] == ticket["wo_id"] for other in self._open.values()
        )
        if still_open:
            ticket["action"] = "updated"
            self._refresh_summary(ticket)
            self._emit(ticket)
            return
        self._cancel_promote(key)
        self._close_ticket(ticket)

    def _close_ticket(self, wo):
        closed = dict(wo)
        when = self._now()
        self._stamp_opened(closed, when)
        closed["status"] = "closed"
        closed["closed_at"] = when
        closed["action"] = "closed"
        closed["machine_recovered"] = True
        for timer_key in list(self._timers):
            current = self._open.get(timer_key)
            if current is None or current.get("wo_id") == closed["wo_id"]:
                self._cancel_promote(timer_key)
        self._emit(closed)
        print(
            "[WO CLOSE] %s %s"
            % (closed["device_id"], closed["work_order_number"])
        )
