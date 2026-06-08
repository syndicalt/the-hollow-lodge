import importlib
import subprocess
import sys

from typer.testing import CliRunner


def test_server_app_imports_without_side_effects(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import hollow_lodge.server.app as app; "
                "print(app.app.title); "
                "print(Path('.hollow-lodge').exists())"
            ),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert result.stdout.splitlines() == ["The Hollow Lodge", "False"]


def test_cli_help_renders_without_server_connection():
    cli = importlib.import_module("hollow_lodge.client.cli")
    runner = CliRunner()

    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "The Hollow Lodge" in result.output
