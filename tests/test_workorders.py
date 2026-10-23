"""Tests for sink work-order manager."""

import re
from datetime import datetime, timedelta, timezone

from sink.workorders import HANDOFF_OPENED, HANDOFF_SENT, WorkOrderManager


def _event_payload(number, name, severity, transition, module="CoffeeModule1", seq=1):
    return {
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": seq,
        "event": {
            "number": number,
            "name": name,
            "severity": severity,
            "category": "Machine Issue",
            "module": module,
            "source": module,
            "stateful": True,
            "transition": transition,
        },
    }


def test_opens_one_wo_per_fault(tmp_path):
    wo_path = tmp_path / "wo.jsonl"
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=wo_path, promote_delay_s=0)

    payload = {
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 10,
        "active_faults": ["scaling"],
    }
    mgr.process_telemetry(payload)
    mgr.process_telemetry(payload)

    opens = [e for e in emitted if e["action"] == "created"]
    assert len(opens) == 1
    assert opens[0]["fault"] == "scaling"


def test_closes_wo_when_fault_clears(tmp_path):
    wo_path = tmp_path / "wo.jsonl"
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=wo_path, promote_delay_s=0)

    mgr.process_telemetry({
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 1,
        "active_faults": ["scaling"],
    })
    mgr.process_telemetry({
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 2,
        "active_faults": [],
    })

    closes = [e for e in emitted if e["action"] == "closed"]
    assert len(closes) == 1
    assert closes[0]["status"] == "closed"


def test_opens_one_wo_per_event_module(tmp_path):
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=tmp_path / "wo.jsonl", promote_delay_s=0)

    mgr.process_event(_event_payload(56, "SteamOutletNotAvailable", "Error", "raised", "SteamManager"))
    mgr.process_event(_event_payload(56, "SteamOutletNotAvailable", "Error", "raised", "SteamManager"))

    opens = [e for e in emitted if e["action"] == "created"]
    assert len(opens) == 1
    assert opens[0]["module"] == "SteamManager"
    assert opens[0]["source"] == "event"


def test_closes_event_wo_on_clear(tmp_path):
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=tmp_path / "wo.jsonl", promote_delay_s=0)

    mgr.process_event(_event_payload(56, "SteamOutletNotAvailable", "Error", "raised", "SteamManager", seq=1))
    mgr.process_event(_event_payload(55, "SteamOutletAvailable", "Info", "cleared", "SteamManager", seq=2))

    closes = [e for e in emitted if e["action"] == "closed"]
    assert len(closes) == 1
    assert closes[0]["event_name"] == "SteamOutletNotAvailable"


def test_separate_modules_get_separate_event_wos(tmp_path):
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=tmp_path / "wo.jsonl", promote_delay_s=0)

    mgr.process_event(_event_payload(19, "GroundsDrawerFull", "Error", "raised", "GroundsDrawer1"))
    mgr.process_event(_event_payload(19, "GroundsDrawerFull", "Error", "raised", "GroundsDrawer2"))

    opens = [e for e in emitted if e["action"] == "created"]
    assert len(opens) == 1
    assert {issue["module"] for issue in emitted[-1]["issues"]} == {
        "GroundsDrawer1",
        "GroundsDrawer2",
    }
    assert emitted[-1]["work_order_number"] == opens[0]["work_order_number"]


def test_groups_faults_inside_two_minutes(tmp_path):
    emitted = []
    mgr = WorkOrderManager(
        publish_fn=lambda r: emitted.append(r),
        persist_path=tmp_path / "wo.jsonl",
        promote_delay_s=0,
    )
    base = {
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
    }
    mgr.process_telemetry({**base, "seq": 1, "active_faults": ["pump_degradation"]})
    mgr.process_telemetry({
        **base,
        "seq": 2,
        "active_faults": ["pump_degradation", "heater_degradation", "clogged_group"],
    })

    created = [item for item in emitted if item["action"] == "created"]
    assert len(created) == 1
    latest = emitted[-1]
    assert latest["work_order_number"] == created[0]["work_order_number"]
    assert len([issue for issue in latest["issues"] if issue["active"]]) == 3


def test_new_ticket_after_two_minutes(tmp_path):
    clock = {"now": datetime(2026, 10, 23, 19, 0, tzinfo=timezone.utc)}
    emitted = []
    mgr = WorkOrderManager(
        publish_fn=lambda r: emitted.append(r),
        persist_path=tmp_path / "wo.jsonl",
        promote_delay_s=0,
        now_fn=lambda: clock["now"],
    )
    base = {
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
    }
    mgr.process_telemetry({**base, "seq": 1, "active_faults": ["scaling"]})
    clock["now"] = clock["now"] + timedelta(seconds=121)
    mgr.process_telemetry({**base, "seq": 2, "active_faults": ["scaling", "grinder_wear"]})

    created = [item for item in emitted if item["action"] == "created"]
    assert len(created) == 2
    assert created[0]["work_order_number"] != created[1]["work_order_number"]


def test_vixxonow_handoff_uses_live_number_and_statuses(tmp_path):
    emitted = []
    mgr = WorkOrderManager(
        publish_fn=lambda r: emitted.append(r),
        persist_path=tmp_path / "wo.jsonl",
        promote_delay_s=0,
    )
    mgr.process_telemetry({
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 3,
        "active_faults": ["scaling"],
    })

    sent = emitted[0]
    assert re.fullmatch(r"WO-\d{8}-\d{4}", sent["work_order_number"])
    assert sent["wo_id"] == sent["work_order_number"]
    assert re.fullmatch(r"1-\d{10}", sent["siebel_sr_number"])
    assert sent["handoff_label"] == HANDOFF_SENT
    assert sent["asset_type"] == "Brewing"
    assert sent["vixxonow_status"] is None

    mgr._promote(next(iter(mgr._open)))
    opened = emitted[-1]
    assert opened["handoff_label"] == HANDOFF_OPENED
    assert opened["vixxonow_status"] == "submitted"
    assert opened["vixxonow_status_display"] == "Submitted"
    assert opened["work_order_number"] == sent["work_order_number"]
    assert opened["status"] == "open"
