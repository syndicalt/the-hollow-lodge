from __future__ import annotations


def deterministic_provenance_read(fragment_id: str) -> dict:
    return {
        "fragment_id": fragment_id,
        "authority": "local-guidance",
        "guidance": "This may merit a provenance check; spend a side action for an official result.",
    }


def handler_provenance_summary(fragment_id: str) -> dict:
    return {
        "origin": "handler",
        "type": "handler.provenance_summary",
        "fragment_id": fragment_id,
        "summary": "This local read can inform player intent but is not an official result.",
    }
