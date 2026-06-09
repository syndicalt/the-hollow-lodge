import importlib.util
from pathlib import Path

from hollow_lodge.client.backend_smoke import (
    CURRENT_PROJECTION_READ_SURFACES,
    CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
    CURRENT_PROJECTION_SCHEMA_VERSION,
)


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
            },
        },
        expected_backend="postgres",
        expected_event_backend="postgres",
        require_projection_reads=True,
        require_current_projection_read_surfaces=True,
        require_current_projection_schema=True,
        require_sequence_alignment=True,
    )

    assert result["event_log"] == {
        "backend": "postgres",
        "status": "available",
        "event_count": 23,
    }
    assert result["projection"]["backend"] == "postgres"
    assert result["projection"]["lag"] == 0
    assert result["projection"]["schema_version"] == CURRENT_PROJECTION_SCHEMA_VERSION


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
