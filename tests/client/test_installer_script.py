from __future__ import annotations

from pathlib import Path


def test_install_script_bootstraps_cli_and_runs_onboarding():
    script = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "uv tool install" in script
    assert "git+https://github.com/syndicalt/the-hollow-lodge.git" in script
    assert "hollow-lodge onboard" in script
    assert "HOLLOW_LODGE_SKIP_ONBOARD" in script


def test_site_serves_install_script_from_public_root():
    public_script = Path("site/install.sh")

    assert public_script.read_text(encoding="utf-8") == Path("scripts/install.sh").read_text(
        encoding="utf-8"
    )
    assert public_script.stat().st_mode & 0o111


def test_site_is_self_contained_for_railway_static_deploy():
    assert Path("site/Dockerfile").exists()
    assert Path("site/nginx.conf").exists()
    assert Path("site/docs/assets/the-hollow-lodge-x-banner.png").exists()
