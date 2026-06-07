from hollow_lodge.workflows.deterministic_handler import (
    deterministic_provenance_read,
    handler_provenance_summary,
)


def test_deterministic_shallow_provenance_read_for_starter_ledger():
    result = deterministic_provenance_read("fragment_starter_ledger")

    assert result["fragment_id"] == "fragment_starter_ledger"
    assert result["authority"] == "local-guidance"
    assert "provenance_flags" not in result
    assert "spend a side action" in result["guidance"]


def test_handler_summary_is_not_an_official_provenance_event():
    summary = handler_provenance_summary("fragment_starter_ledger")

    assert summary["origin"] == "handler"
    assert summary["type"] == "handler.provenance_summary"
    assert summary["type"] != "proof.provenance.checked"
