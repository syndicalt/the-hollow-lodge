from __future__ import annotations

from pathlib import Path


def test_install_script_bootstraps_cli_and_runs_onboarding():
    script = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "uv tool install" in script
    assert "${HOLLOW_LODGE_PACKAGE:-the-hollow-lodge}" in script
    assert "hollow-lodge onboard" in script
    assert "HOLLOW_LODGE_SKIP_ONBOARD" in script
