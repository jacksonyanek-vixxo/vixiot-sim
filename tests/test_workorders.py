"""Tests for sink work-order manager."""

from sink.workorders import WorkOrderManager


def test_opens_one_wo_per_fault(tmp_path):
    wo_path = tmp_path / "wo.jsonl"
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=wo_path)

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
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=wo_path)

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
