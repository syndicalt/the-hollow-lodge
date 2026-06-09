import importlib.util
import json
from pathlib import Path

from hollow_lodge.client.event_log_migration import create_event_log_manifest
from hollow_lodge.client.backend_smoke import (
    CURRENT_PROJECTION_READ_SURFACES,
    CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
    CURRENT_PROJECTION_SCHEMA_VERSION,
)
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore


def _load_smoke_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "smoke_projection_backend.py"
    )
    spec = importlib.util.spec_from_file_location("smoke_projection_backend", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_projection_backend_smoke_accepts_available_zero_lag_backend():
    smoke = _load_smoke_module()

    result = smoke.validate_projection_diagnostics(
        {
            "server": {"version": "0.1.0"},
            "data": {
                "projection_db": {
                    "backend": "postgres",
                    "database_url": "postgresql://user:***@host:5432/db",
                    "status": "available",
                    "lag": 0,
                    "last_sequence": 23,
                    "authoritative_last_sequence": 23,
                    "schema_version": CURRENT_PROJECTION_SCHEMA_VERSION,
                    "schema_migration_count": CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
                    "latest_schema_migration": CURRENT_PROJECTION_SCHEMA_VERSION,
                },
                "projection_reads": {
                    "global_enabled": True,
                    "surfaces": {
                        surface: True for surface in CURRENT_PROJECTION_READ_SURFACES
                    },
                },
                "storage_guards": {
                    "require_postgres_event_log": True,
                    "require_postgres_projection": True,
                },
                "projection_refresh": {
                    "status": "ok",
                    "last_context": "startup",
                    "last_success_sequence": 23,
                    "failure_count": 0,
                    "last_failure": None,
                },
            },
        },
        expected_backend="postgres",
        require_projection_reads=True,
        require_current_projection_read_surfaces=True,
        require_current_projection_schema=True,
    )

    assert result["backend"] == "postgres"
    assert result["lag"] == 0
    assert result["schema_version"] == CURRENT_PROJECTION_SCHEMA_VERSION
    assert result["schema_migration_count"] == CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT
    assert result["last_sequence"] == 23
    assert result["projection_reads"]["surfaces"]["contract_board"] is True


def test_backend_smoke_accepts_event_and_projection_backends():
    smoke = _load_smoke_module()

    result = smoke.validate_backend_diagnostics(
        {
            "server": {"version": "0.1.0"},
            "data": {
                "event_log": {
                    "backend": "postgres",
                    "database_url": "postgresql://event:***@host:5432/db",
                    "status": "available",
                    "event_count": 23,
                    "last_sequence": 23,
                    "last_event_hash": "event-hash-23",
                    "event_hash_chain_sha256": "chain-digest-23",
                },
                "projection_db": {
                    "backend": "postgres",
                    "database_url": "postgresql://projection:***@host:5432/db",
                    "status": "available",
                    "lag": 0,
                    "last_sequence": 23,
                    "authoritative_last_sequence": 23,
                    "schema_version": CURRENT_PROJECTION_SCHEMA_VERSION,
                    "schema_migration_count": CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
                    "latest_schema_migration": CURRENT_PROJECTION_SCHEMA_VERSION,
                },
                "projection_reads": {
                    "global_enabled": True,
                    "surfaces": {
                        surface: True for surface in CURRENT_PROJECTION_READ_SURFACES
                    },
                },
                "storage_guards": {
                    "require_postgres_event_log": True,
                    "require_postgres_projection": True,
                },
                "projection_refresh": {
                    "status": "ok",
                    "last_context": "startup",
                    "last_success_sequence": 23,
                    "failure_count": 0,
                    "last_failure": None,
                },
            },
        },
        expected_backend="postgres",
        expected_event_backend="postgres",
        require_projection_reads=True,
        require_current_projection_read_surfaces=True,
        require_current_projection_schema=True,
        require_sequence_alignment=True,
        require_postgres_event_log_guard=True,
        require_postgres_projection_guard=True,
        require_projection_refresh_ok=True,
    )

    assert result["event_log"] == {
        "backend": "postgres",
        "status": "available",
        "event_count": 23,
        "last_sequence": 23,
        "last_event_hash": "event-hash-23",
        "event_hash_chain_sha256": "chain-digest-23",
    }
    assert result["projection"]["backend"] == "postgres"
    assert result["projection"]["lag"] == 0
    assert result["projection"]["schema_version"] == CURRENT_PROJECTION_SCHEMA_VERSION
    assert result["storage_guards"] == {
        "require_postgres_event_log": True,
        "require_postgres_projection": True,
    }
    assert result["projection_refresh"]["status"] == "ok"


def test_run_smoke_production_postgres_preset_forwards_required_checks(monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_run_backend_smoke(**kwargs):
        calls.append(kwargs)
        return {
            "event_log": {
                "backend": "postgres",
                "status": "available",
                "event_count": 23,
                "last_sequence": 23,
                "last_event_hash": "event-hash-23",
                "event_hash_chain_sha256": "chain-digest-23",
            },
            "projection": {
                "backend": "postgres",
                "status": "available",
                "lag": 0,
                "last_sequence": 23,
                "authoritative_last_sequence": 23,
                "schema_version": CURRENT_PROJECTION_SCHEMA_VERSION,
                "schema_migration_count": CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
                "latest_schema_migration": CURRENT_PROJECTION_SCHEMA_VERSION,
            },
        }

    monkeypatch.setattr(smoke, "run_backend_smoke", fake_run_backend_smoke)

    result = smoke.run_smoke(
        server_url="https://server.thehollowlodge.com",
        production_postgres=True,
    )

    assert result["event_log"]["backend"] == "postgres"
    assert calls == [
        {
            "server_url": "https://server.thehollowlodge.com",
            "expected_backend": "postgres",
            "expected_event_backend": "postgres",
            "require_projection_reads": True,
            "require_current_projection_read_surfaces": True,
            "require_current_projection_schema": True,
            "require_sequence_alignment": True,
            "event_log_manifest": None,
            "require_postgres_event_log_guard": True,
            "require_postgres_projection_guard": True,
            "require_projection_refresh_ok": True,
            "require_maintenance_read_only": False,
            "require_maintenance_read_write": True,
        }
    ]


def test_backend_smoke_accepts_required_maintenance_read_only():
    smoke = _load_smoke_module()

    result = smoke.validate_backend_diagnostics(
        {
            "data": {
                "event_log": {
                    "backend": "jsonl",
                    "status": "available",
                    "event_count": 23,
                },
                "projection_db": {
                    "backend": "postgres",
                    "status": "available",
                    "lag": 0,
                },
                "maintenance": {
                    "read_only": True,
                    "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
                },
            }
        },
        expected_backend="postgres",
        expected_event_backend="jsonl",
        require_maintenance_read_only=True,
    )

    assert result["maintenance"] == {
        "read_only": True,
        "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
    }


def test_backend_smoke_rejects_disabled_required_maintenance_read_only():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "jsonl",
                        "status": "available",
                        "event_count": 23,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                    "maintenance": {
                        "read_only": False,
                        "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="jsonl",
            require_maintenance_read_only=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("disabled maintenance mode should fail readiness smoke")

    assert "maintenance read-only mode is not enabled" in message


def test_backend_smoke_rejects_missing_required_maintenance_diagnostics():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "jsonl",
                        "status": "available",
                        "event_count": 23,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="jsonl",
            require_maintenance_read_only=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("missing maintenance diagnostics should fail")

    assert "diagnostics response did not include data.maintenance" in message
    assert "maintenance read-only mode is not enabled" in message


def test_backend_smoke_accepts_required_maintenance_read_write():
    smoke = _load_smoke_module()

    result = smoke.validate_backend_diagnostics(
        {
            "data": {
                "event_log": {
                    "backend": "postgres",
                    "status": "available",
                    "event_count": 23,
                },
                "projection_db": {
                    "backend": "postgres",
                    "status": "available",
                    "lag": 0,
                },
                "maintenance": {
                    "read_only": False,
                    "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
                },
            }
        },
        expected_backend="postgres",
        expected_event_backend="postgres",
        require_maintenance_read_write=True,
    )

    assert result["maintenance"] == {
        "read_only": False,
        "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
    }


def test_backend_smoke_rejects_frozen_required_maintenance_read_write():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "status": "available",
                        "event_count": 23,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                    "maintenance": {
                        "read_only": True,
                        "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            require_maintenance_read_write=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("frozen maintenance mode should fail read/write smoke")

    assert "maintenance read/write mode is not enabled" in message


def test_backend_smoke_rejects_conflicting_maintenance_requirements():
    smoke = _load_smoke_module()

    try:
        smoke.resolve_backend_smoke_options(
            expected_backend="postgres",
            require_maintenance_read_only=True,
            require_maintenance_read_write=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("conflicting maintenance smoke requirements should fail")

    assert "--require-maintenance-read-only" in message
    assert "--require-maintenance-read-write" in message


def test_backend_smoke_rejects_failed_projection_refresh():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "server": {"version": "0.1.0"},
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://event:***@host:5432/db",
                        "status": "available",
                        "event_count": 23,
                        "last_sequence": 23,
                        "last_event_hash": "event-hash-23",
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://projection:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                        "last_sequence": 23,
                        "authoritative_last_sequence": 23,
                    },
                    "projection_refresh": {
                        "status": "failed",
                        "last_context": "contracts",
                        "last_success_sequence": 22,
                        "failure_count": 1,
                        "last_failure": {
                            "context": "contracts",
                            "error_type": "OperationalError",
                            "message": "password=secret raw database error",
                        },
                    },
                },
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            require_projection_refresh_ok=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("failed projection refresh should fail readiness smoke")

    assert (
        "projection refresh status is failed; expected ok "
        "(context=contracts, error_type=OperationalError)"
    ) in message
    assert "password=secret" not in message
    assert "raw database error" not in message


def test_backend_smoke_rejects_missing_required_storage_guards():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "status": "available",
                        "event_count": 3,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            require_postgres_event_log_guard=True,
            require_postgres_projection_guard=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("missing storage guards should fail")

    assert "diagnostics response did not include data.storage_guards" in message
    assert "Postgres event-log startup guard is not enabled" in message
    assert "Postgres projection startup guard is not enabled" in message


def test_backend_smoke_rejects_disabled_required_storage_guards():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "status": "available",
                        "event_count": 3,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                    "storage_guards": {
                        "require_postgres_event_log": False,
                        "require_postgres_projection": False,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            require_postgres_event_log_guard=True,
            require_postgres_projection_guard=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("disabled storage guards should fail")

    assert "Postgres event-log startup guard is not enabled" in message
    assert "Postgres projection startup guard is not enabled" in message


def test_backend_smoke_rejects_event_log_guard_with_non_postgres_backend():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "jsonl",
                        "status": "available",
                        "event_count": 3,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                    "storage_guards": {
                        "require_postgres_event_log": True,
                        "require_postgres_projection": True,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="jsonl",
            require_postgres_event_log_guard=True,
            require_postgres_projection_guard=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("event-log guard with non-Postgres backend should fail")

    assert (
        "Postgres event-log guard is enabled but event-log backend is jsonl"
        in message
    )


def test_backend_smoke_rejects_projection_guard_with_non_postgres_backend():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "status": "available",
                        "event_count": 3,
                    },
                    "projection_db": {
                        "backend": "sqlite",
                        "status": "available",
                        "lag": 0,
                    },
                    "storage_guards": {
                        "require_postgres_event_log": True,
                        "require_postgres_projection": True,
                    },
                }
            },
            expected_backend="sqlite",
            expected_event_backend="postgres",
            require_postgres_event_log_guard=True,
            require_postgres_projection_guard=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("projection guard with non-Postgres backend should fail")

    assert (
        "Postgres projection guard is enabled but projection backend is sqlite"
        in message
    )


def test_backend_smoke_accepts_event_log_manifest_chain_head(tmp_path):
    smoke = _load_smoke_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = create_event_log_manifest(source)

    result = smoke.validate_backend_diagnostics(
        {
            "data": {
                "event_log": {
                    "backend": "postgres",
                    "database_url": "postgresql://event:***@host:5432/db",
                    "status": "available",
                    "event_count": 1,
                    "last_sequence": 1,
                    "last_event_hash": event.event_hash,
                    "event_hash_chain_sha256": manifest["event_hash_chain_sha256"],
                },
                "projection_db": {
                    "backend": "postgres",
                    "database_url": "postgresql://projection:***@host:5432/db",
                    "status": "available",
                    "lag": 0,
                    "last_sequence": 1,
                    "authoritative_last_sequence": 1,
                },
            },
        },
        expected_backend="postgres",
        expected_event_backend="postgres",
        event_log_manifest=manifest,
    )

    assert result["event_log"]["last_event_hash"] == event.event_hash
    assert (
        result["event_log"]["event_hash_chain_sha256"]
        == manifest["event_hash_chain_sha256"]
    )


def test_backend_smoke_rejects_malformed_event_log_manifest(tmp_path):
    smoke = _load_smoke_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = create_event_log_manifest(source)
    manifest["manifest_type"] = "not_hollow_lodge"

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://event:***@host:5432/db",
                        "status": "available",
                        "event_count": 1,
                        "last_sequence": 1,
                        "last_event_hash": event.event_hash,
                        "event_hash_chain_sha256": manifest["event_hash_chain_sha256"],
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://projection:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                },
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            event_log_manifest=manifest,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("malformed event-log manifest should fail")

    assert "event manifest type does not match Hollow Lodge event logs" in message


def test_backend_smoke_rejects_non_object_event_log_manifest():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://event:***@host:5432/db",
                        "status": "available",
                        "event_count": 0,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://projection:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                },
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            event_log_manifest=[],
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("non-object event-log manifest should fail")

    assert "event manifest must be a JSON object" in message


def test_backend_smoke_rejects_event_log_manifest_chain_digest_mismatch(tmp_path):
    smoke = _load_smoke_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = create_event_log_manifest(source)

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://event:***@host:5432/db",
                        "status": "available",
                        "event_count": 1,
                        "last_sequence": 1,
                        "last_event_hash": event.event_hash,
                        "event_hash_chain_sha256": "different-digest",
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://projection:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                },
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            event_log_manifest=manifest,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("manifest chain digest mismatch should fail")

    assert (
        "event log event_hash_chain_sha256 does not match manifest "
        "event_hash_chain_sha256"
    ) in message


def test_backend_smoke_rejects_event_log_manifest_chain_head_mismatch(tmp_path):
    smoke = _load_smoke_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = create_event_log_manifest(source)

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://event:***@host:5432/db",
                        "status": "available",
                        "event_count": 1,
                        "last_sequence": 1,
                        "last_event_hash": "different-hash",
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://projection:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                },
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            event_log_manifest=manifest,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("manifest chain-head mismatch should fail")

    assert "event log last_event_hash does not match manifest last_event_hash" in message


def test_backend_smoke_rejects_event_backend_mismatch():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "jsonl",
                        "status": "available",
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "status": "available",
                        "lag": 0,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("event backend mismatch should fail the smoke")

    assert "expected event-log backend postgres, got jsonl" in message


def test_backend_smoke_rejects_unredacted_event_database_url_password():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:secret@host:5432/db",
                        "status": "available",
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("unredacted event DB password should fail the smoke")

    assert "event-log diagnostics expose an unredacted database URL password" in message
    assert "secret" not in message


def test_projection_backend_smoke_rejects_backend_mismatch():
    smoke = _load_smoke_module()

    try:
        smoke.validate_projection_diagnostics(
            {
                "data": {
                    "projection_db": {
                        "backend": "sqlite",
                        "status": "available",
                        "lag": 0,
                    }
                }
            },
            expected_backend="postgres",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("backend mismatch should fail the smoke")

    assert "expected projection backend postgres, got sqlite" in message


def test_projection_backend_smoke_rejects_stale_projection():
    smoke = _load_smoke_module()

    try:
        smoke.validate_projection_diagnostics(
            {
                "data": {
                    "projection_db": {
                        "backend": "postgres",
                        "status": "stale",
                        "lag": 2,
                    }
                }
            },
            expected_backend="postgres",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("stale projection should fail the smoke")

    assert "projection status is stale" in message
    assert "projection lag is 2" in message


def test_projection_backend_smoke_rejects_unredacted_database_url_password():
    smoke = _load_smoke_module()

    try:
        smoke.validate_projection_diagnostics(
            {
                "data": {
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:secret@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    }
                }
            },
            expected_backend="postgres",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("unredacted database password should fail the smoke")

    assert "projection diagnostics expose an unredacted database URL password" in message
    assert "secret" not in message


def test_projection_backend_smoke_rejects_disabled_projection_read_surfaces():
    smoke = _load_smoke_module()

    try:
        smoke.validate_projection_diagnostics(
            {
                "data": {
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                    "projection_reads": {
                        "global_enabled": True,
                        "surfaces": {
                            "contract_board": True,
                            "crew_summary": False,
                        },
                    },
                }
            },
            expected_backend="postgres",
            require_projection_reads=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("disabled projection read surfaces should fail the smoke")

    assert "projection read surfaces disabled: crew_summary" in message


def test_projection_backend_smoke_rejects_missing_projection_read_surfaces():
    smoke = _load_smoke_module()
    surfaces = {surface: True for surface in CURRENT_PROJECTION_READ_SURFACES}
    surfaces.pop("visible_events")

    try:
        smoke.validate_projection_diagnostics(
            {
                "data": {
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                    "projection_reads": {
                        "global_enabled": True,
                        "surfaces": surfaces,
                    },
                }
            },
            expected_backend="postgres",
            require_current_projection_read_surfaces=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("missing projection read surfaces should fail the smoke")

    assert "projection read surfaces missing from diagnostics: visible_events" in message


def test_projection_backend_smoke_rejects_unexpected_projection_read_surfaces():
    smoke = _load_smoke_module()
    surfaces = {surface: True for surface in CURRENT_PROJECTION_READ_SURFACES}
    surfaces["future_surface"] = True

    try:
        smoke.validate_projection_diagnostics(
            {
                "data": {
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                    },
                    "projection_reads": {
                        "global_enabled": True,
                        "surfaces": surfaces,
                    },
                }
            },
            expected_backend="postgres",
            require_current_projection_read_surfaces=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("unexpected projection read surfaces should fail the smoke")

    assert "projection read surfaces unexpected in diagnostics: future_surface" in message


def test_projection_backend_smoke_rejects_stale_projection_schema():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "jsonl",
                        "status": "available",
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://user:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                        "schema_version": CURRENT_PROJECTION_SCHEMA_VERSION - 1,
                        "schema_migration_count": (
                            CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT - 1
                        ),
                        "latest_schema_migration": CURRENT_PROJECTION_SCHEMA_VERSION - 1,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="jsonl",
            require_current_projection_schema=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("stale projection schema should fail the smoke")

    assert (
        "projection schema_version is "
        f"{CURRENT_PROJECTION_SCHEMA_VERSION - 1}; "
        f"expected {CURRENT_PROJECTION_SCHEMA_VERSION}"
    ) in message
    assert (
        "projection schema_migration_count is "
        f"{CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT - 1}; "
        f"expected {CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT}"
    ) in message
    assert (
        "projection latest_schema_migration is "
        f"{CURRENT_PROJECTION_SCHEMA_VERSION - 1}; "
        f"expected {CURRENT_PROJECTION_SCHEMA_VERSION}"
    ) in message


def test_backend_smoke_rejects_sequence_alignment_mismatch():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "postgres",
                        "database_url": "postgresql://event:***@host:5432/db",
                        "status": "available",
                        "event_count": 24,
                    },
                    "projection_db": {
                        "backend": "postgres",
                        "database_url": "postgresql://projection:***@host:5432/db",
                        "status": "available",
                        "lag": 0,
                        "last_sequence": 22,
                        "authoritative_last_sequence": 23,
                    },
                }
            },
            expected_backend="postgres",
            expected_event_backend="postgres",
            require_sequence_alignment=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("sequence alignment mismatch should fail the smoke")

    assert (
        "event log event_count 24 does not match projection "
        "authoritative_last_sequence 23"
    ) in message
    assert (
        "projection last_sequence 22 does not match "
        "authoritative_last_sequence 23"
    ) in message
    assert "projection lag 0 does not match authoritative-last delta 1" in message


def test_backend_smoke_rejects_missing_sequence_alignment_fields():
    smoke = _load_smoke_module()

    try:
        smoke.validate_backend_diagnostics(
            {
                "data": {
                    "event_log": {
                        "backend": "jsonl",
                        "status": "available",
                    },
                    "projection_db": {
                        "backend": "sqlite",
                        "status": "available",
                        "lag": "not-a-number",
                    },
                }
            },
            expected_backend="sqlite",
            require_sequence_alignment=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("missing sequence fields should fail the smoke")

    assert "event log event_count is missing or invalid" in message
    assert "projection last_sequence is missing or invalid" in message
    assert "projection authoritative_last_sequence is missing or invalid" in message
    assert "projection lag is missing or invalid" in message
