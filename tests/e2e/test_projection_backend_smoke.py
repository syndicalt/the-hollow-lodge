import importlib.util
from pathlib import Path


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
                },
                "projection_reads": {
                    "global_enabled": True,
                    "surfaces": {"contract_board": True, "crew_summary": True},
                },
            },
        },
        expected_backend="postgres",
        require_projection_reads=True,
    )

    assert result["backend"] == "postgres"
    assert result["lag"] == 0
    assert result["last_sequence"] == 23
    assert result["projection_reads"]["surfaces"]["contract_board"] is True


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
