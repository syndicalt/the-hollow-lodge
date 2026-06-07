import importlib

from typer.testing import CliRunner


def test_server_app_imports_without_side_effects():
    module = importlib.import_module("hollow_lodge.server.app")

    assert module.app.title == "The Hollow Lodge"


def test_cli_help_renders_without_server_connection():
    cli = importlib.import_module("hollow_lodge.client.cli")
    runner = CliRunner()

    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "The Hollow Lodge" in result.output
