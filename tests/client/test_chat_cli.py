from typer.testing import CliRunner

from hollow_lodge.client import cli


def test_chat_commands_are_registered():
    runner = CliRunner()

    result = runner.invoke(cli.app, ["msg", "--help"])

    assert result.exit_code == 0
    assert "Send a direct brokered message" in result.output


def test_thread_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli.app, ["thread", "--help"])

    assert result.exit_code == 0
    assert "Show a brokered conversation thread" in result.output
