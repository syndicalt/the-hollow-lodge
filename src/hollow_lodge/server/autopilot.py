"""Server autopilot: keeps the game running without a GM.

Each pass does two things, in order:

1. Resolve every published contract whose phase timer (tracked from the
   contract's publish timestamp) has expired.
2. Publish queued packaged contract seeds until the board has at least
   HOLLOW_LODGE_MIN_ACTIVE_CONTRACTS open contracts.

The background loop is enabled by setting
HOLLOW_LODGE_AUTOPILOT_INTERVAL_SECONDS to a positive number (production
deployments should set it; it defaults to off so tests and local tooling
control the world explicitly).
"""

from __future__ import annotations

import json
import logging
import os
import threading

from importlib import resources

from fastapi import FastAPI

from hollow_lodge.server.contract_seed import ContractSeed

logger = logging.getLogger(__name__)

AUTOPILOT_INTERVAL_ENV = "HOLLOW_LODGE_AUTOPILOT_INTERVAL_SECONDS"
MIN_ACTIVE_CONTRACTS_ENV = "HOLLOW_LODGE_MIN_ACTIVE_CONTRACTS"

# Curated release order; packaged seeds not listed here are appended
# alphabetically, so dropping a new JSON file into contract_seeds/ is enough
# to put it at the end of the queue.
CONTRACT_RELEASE_ORDER = (
    "ash_window",
    "ninth_mourner_receipt",
    "wax_eclipse_bond",
    "violet_hour_inventory",
)


def packaged_contract_seeds() -> list[ContractSeed]:
    root = resources.files("hollow_lodge.contract_seeds")
    entries = {
        entry.name.removesuffix(".json"): entry
        for entry in root.iterdir()
        if entry.name.endswith(".json")
    }
    ordered = [name for name in CONTRACT_RELEASE_ORDER if name in entries]
    ordered.extend(
        sorted(name for name in entries if name not in CONTRACT_RELEASE_ORDER)
    )
    return [
        ContractSeed.model_validate(
            json.loads(entries[name].read_text(encoding="utf-8"))
        )
        for name in ordered
    ]


def autopilot_interval_seconds() -> float:
    raw = os.environ.get(AUTOPILOT_INTERVAL_ENV, "0")
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning("invalid %s=%r; autopilot disabled", AUTOPILOT_INTERVAL_ENV, raw)
        return 0.0


def minimum_active_contracts() -> int:
    raw = os.environ.get(MIN_ACTIVE_CONTRACTS_ENV, "1")
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("invalid %s=%r; using 1", MIN_ACTIVE_CONTRACTS_ENV, raw)
        return 1


def run_autopilot_pass(app: FastAPI) -> dict:
    contract_service = getattr(app.state, "contract_service", None)
    if contract_service is None:
        return {"resolved_contract_ids": [], "activated_contract_ids": []}
    resolved = contract_service.resolve_due_phases()
    activated = contract_service.ensure_active_contracts(
        seeds=packaged_contract_seeds(),
        minimum_active=minimum_active_contracts(),
    )
    if resolved or activated:
        logger.info(
            "autopilot pass resolved=%s activated=%s",
            resolved,
            activated,
        )
        _refresh_projections(app)
    return {
        "resolved_contract_ids": resolved,
        "activated_contract_ids": activated,
    }


def start_autopilot(app: FastAPI) -> threading.Thread | None:
    interval = autopilot_interval_seconds()
    if interval <= 0:
        return None
    stop_event = threading.Event()
    app.state.autopilot_stop = stop_event

    def loop() -> None:
        while True:
            try:
                run_autopilot_pass(app)
            except Exception:
                logger.exception("autopilot pass failed")
            if stop_event.wait(interval):
                return

    thread = threading.Thread(
        target=loop,
        name="hollow-lodge-autopilot",
        daemon=True,
    )
    thread.start()
    return thread


def _refresh_projections(app: FastAPI) -> None:
    projection_store = getattr(app.state, "projection_store", None)
    event_store = getattr(app.state, "event_store", None)
    if projection_store is None or event_store is None:
        return
    try:
        projection_store.rebuild(event_store.read())
    except Exception:
        logger.exception("autopilot projection refresh failed")
