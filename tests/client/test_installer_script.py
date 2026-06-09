from __future__ import annotations

from pathlib import Path


def test_install_script_bootstraps_cli_and_runs_onboarding():
    script = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "uv tool install" in script
    assert "git+https://github.com/syndicalt/the-hollow-lodge.git" in script
    assert "hollow-lodge codex install-mcp" in script
    assert "hollow-lodge onboard" in script
    assert "hollow-lodge doctor" in script
    assert "server, auth, MCP, and Codex render readiness" in script
    assert "HOLLOW_LODGE_SKIP_ONBOARD" in script
    assert "HOLLOW_LODGE_SKIP_DOCTOR" in script


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


def test_site_copy_includes_public_installer_and_agent_boundary():
    html = Path("site/index.html").read_text(encoding="utf-8")

    assert "curl -fsSL https://www.thehollowlodge.com/install.sh | sh" in html
    assert "Your local agent helps you with organization, but the decisions are yours." in html


def test_operations_docs_describe_current_doctor_readiness_checks():
    operations = Path("docs/operations.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "saved auth status" in operations
    assert "inbox readiness" in operations
    assert "local event-sync cache" in operations
    assert "Codex inbox render readiness" in operations
    assert "hollow-lodge doctor --strict" in operations
    assert "exits non-zero unless a registered player is fully ready" in operations
    assert "runs a non-strict `hollow-lodge doctor` readiness report" in operations
    assert "HOLLOW_LODGE_SKIP_DOCTOR=1" in operations
    assert "runs a redacted `hollow-lodge doctor` readiness" in readme
    assert "saved auth, inbox readiness" in readme
    assert "Codex MCP" in readme
    assert "doctor --strict" in readme


def test_codex_play_guide_describes_doctor_and_mcp_render_readiness():
    guide = Path("docs/codex-play.md").read_text(encoding="utf-8")

    assert "hollow-lodge doctor" in guide
    assert "hollow-lodge doctor --strict" in guide
    assert "installer already runs the non-strict form" in guide
    assert "HOLLOW_LODGE_SKIP_DOCTOR=1" in guide
    assert "saved auth" in guide
    assert "local event-sync cache" in guide
    assert "codex inbox render: ok surface=inbox" in guide
    assert "MCP `render_inbox` tool" in guide
    assert "tokens, invite codes, contract titles, event bodies" in guide
