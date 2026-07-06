"""Trade Coverage Matrix + generic all-trade lane tests."""

from __future__ import annotations

import sqlite3

from app.config import settings
from tests.conftest import prepare_verified_project


def test_general_trade_is_registered(client):
    body = client.get("/api/v1/trades").json()
    codes = {trade["trade_code"] for trade in body["trades"]}
    assert "general_trade" in codes
    generic = client.get("/api/v1/trades/general_trade").json()
    assert generic["trade_code"] == "general_trade"
    assert "allowance" in generic["scope_categories"]
    assert "09" in generic["csi_divisions"]


def test_trade_coverage_table_migrates(client):
    conn = sqlite3.connect(settings.db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert "trade_coverage_rows" in tables


def test_create_list_update_and_validate_coverage_row(client):
    pid = prepare_verified_project(client)

    created = client.post(
        f"/api/v1/projects/{pid}/coverage",
        json={
            "trade_code": "electrical",
            "trade_name": "Electrical",
            "csi_divisions": ["26"],
            "detected_from": ["sheet_discipline", "spec_division"],
            "disposition": "undispositioned",
            "status": "draft",
            "confidence": 0.62,
        },
    )
    assert created.status_code == 201
    row = created.json()
    assert row["trade_code"] == "electrical"
    assert row["detected_from"] == ["sheet_discipline", "spec_division"]

    listing = client.get(f"/api/v1/projects/{pid}/coverage").json()
    assert listing["total"] == 1

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is False
    assert validation["critical_count"] == 1
    assert validation["findings"][0]["code"] == "undispositioned_trade"

    patched = client.patch(
        f"/api/v1/projects/{pid}/coverage/{row['id']}",
        json={
            "disposition": "allowance",
            "status": "ready",
            "basis_note": "Automation v1 carries electrical as a labeled allowance pending customer revision.",
            "confidence": 0.5,
        },
    )
    assert patched.status_code == 200
    updated = patched.json()
    assert updated["disposition"] == "allowance"
    assert updated["basis_note"].startswith("Automation v1")

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is True
    assert validation["findings"] == []


def test_blocked_coverage_row_requires_blockers(client):
    pid = prepare_verified_project(client)
    row = client.post(
        f"/api/v1/projects/{pid}/coverage",
        json={
            "trade_code": "low_voltage",
            "trade_name": "Low Voltage",
            "csi_divisions": ["27"],
            "detected_from": ["interface_implication"],
            "disposition": "blocked_needs_info",
            "status": "blocked",
        },
    ).json()

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is False
    assert validation["critical_count"] == 1
    assert validation["findings"][0]["code"] == "blocked_without_blockers"

    client.patch(
        f"/api/v1/projects/{pid}/coverage/{row['id']}",
        json={"blockers": ["Customer must confirm whether low-voltage is included."]},
    )
    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is True


def test_duplicate_coverage_trade_rejected(client):
    pid = prepare_verified_project(client)
    payload = {
        "trade_code": "electrical",
        "trade_name": "Electrical",
        "csi_divisions": ["26"],
        "detected_from": ["sheet_discipline"],
    }
    assert client.post(f"/api/v1/projects/{pid}/coverage", json=payload).status_code == 201
    duplicate = client.post(f"/api/v1/projects/{pid}/coverage", json=payload)
    assert duplicate.status_code == 409



def test_unknown_project_coverage_404(client):
    resp = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/coverage")
    assert resp.status_code == 404
