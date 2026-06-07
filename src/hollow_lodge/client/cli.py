from pathlib import Path

import typer

from hollow_lodge import __version__
from hollow_lodge.client.api import HollowLodgeApi, new_command_key
from hollow_lodge.client.config import ClientConfig, load_config, save_config
from hollow_lodge.client.render import render_contract_board, render_inbox


app = typer.Typer(
    name="hollow-lodge",
    help="The Hollow Lodge CLI.",
    no_args_is_help=True,
)


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "hollow-lodge" / "config.json"


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed Hollow Lodge version.",
    ),
) -> None:
    """The Hollow Lodge command-line client."""
    if version:
        typer.echo(f"The Hollow Lodge {__version__}")
        raise typer.Exit()


@app.command()
def register(
    server: str = typer.Option(..., "--server", help="Authoritative server URL."),
    invite: str = typer.Option(..., "--invite", help="Invite code."),
    name: str = typer.Option(..., "--name", help="Display name."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Register an invited player and save the local token."""
    api = HollowLodgeApi(server_url=server)
    response = api.register(
        invite_code=invite,
        display_name=name,
        idempotency_key=new_command_key("register"),
    )
    save_config(
        config,
        ClientConfig(
            server_url=server,
            player_id=response["player_id"],
            token=response["token"],
        ),
    )
    typer.echo(response["player_id"])


@app.command("crew-create")
def crew_create(
    name: str = typer.Argument(..., help="Crew name."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Create a stable crew."""
    current = load_config(config)
    api = _api_from_config(current)
    response = api.create_crew(
        name=name,
        idempotency_key=new_command_key("crew-create"),
    )
    save_config(config, current.model_copy(update={"active_crew_id": response["crew_id"]}))
    join_code = response.get("join_code")
    typer.echo(f"{response['crew_id']} {join_code}" if join_code else response["crew_id"])


@app.command("crew-join")
def crew_join(
    crew_id: str = typer.Argument(..., help="Crew id."),
    join_code: str = typer.Option(..., "--join-code", help="Crew join code."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Join a crew with its join code."""
    current = load_config(config)
    api = _api_from_config(current)
    response = api.join_crew(
        crew_id=crew_id,
        join_code=join_code,
        idempotency_key=new_command_key("crew-join"),
    )
    save_config(config, current.model_copy(update={"active_crew_id": response["crew_id"]}))
    typer.echo(response["crew_id"])


@app.command()
def msg(
    recipient: str = typer.Argument(..., help="Recipient player handle or id."),
    body: str = typer.Argument(..., help="Message body."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Send a direct brokered message."""
    response = _api_from_config(load_config(config)).send_direct_message(
        recipient_player_id=recipient,
        body=body,
        idempotency_key=new_command_key("chat-direct"),
    )
    typer.echo(response["message_id"])


@app.command()
def crew(
    body: str = typer.Argument(..., help="Crew message body."),
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Send a brokered message to your crew."""
    current = load_config(config)
    target_crew_id = crew_id or current.active_crew_id
    if target_crew_id is None:
        raise typer.BadParameter("crew id required when no active crew is configured")
    response = _api_from_config(current).send_crew_message(
        crew_id=target_crew_id,
        body=body,
        idempotency_key=new_command_key("chat-crew"),
    )
    typer.echo(response["message_id"])


@app.command("crew-msg")
def crew_msg(
    crew_id: str = typer.Argument(..., help="Recipient crew id."),
    body: str = typer.Argument(..., help="Message body."),
    sender_crew_id: str | None = typer.Option(
        None,
        "--sender-crew-id",
        help="Sending crew id; defaults to active crew.",
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Send a targeted brokered crew-to-crew message."""
    current = load_config(config)
    from_crew_id = sender_crew_id or current.active_crew_id
    if from_crew_id is None:
        raise typer.BadParameter("sender crew id required when no active crew is configured")
    response = _api_from_config(current).send_crew_to_crew_message(
        sender_crew_id=from_crew_id,
        recipient_crew_id=crew_id,
        body=body,
        idempotency_key=new_command_key("chat-crew-to-crew"),
    )
    typer.echo(response["message_id"])


@app.command()
def thread(
    conversation_id: str = typer.Argument(..., help="Conversation id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Show a brokered conversation thread."""
    events = _api_from_config(load_config(config)).visible_events()
    for event in events:
        payload = event.get("payload", {})
        if _payload_matches_conversation(payload, conversation_id):
            typer.echo(f"{event['sequence']} {payload.get('sender_player_id')}: {payload.get('body')}")


@app.command()
def contracts(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Show the contract board."""
    typer.echo(render_contract_board(_api_from_config(load_config(config)).contracts()))


@app.command()
def inbox(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Show the personal inbox."""
    typer.echo(render_inbox(_api_from_config(load_config(config)).inbox()))


@app.command()
def check(
    fragment_id: str = typer.Argument(..., help="Proof fragment id."),
    check_type: str = typer.Argument(..., help="Check type."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Spend a side action on a proof check."""
    if check_type != "provenance":
        raise typer.BadParameter("only provenance checks are available")
    result = _api_from_config(load_config(config)).check_provenance(
        fragment_id=fragment_id,
        idempotency_key=new_command_key("proof-provenance"),
    )
    typer.echo(f"{result['fragment_id']} provenance: {', '.join(result['provenance_flags'])}")


def _api_from_config(config: ClientConfig) -> HollowLodgeApi:
    return HollowLodgeApi(server_url=config.server_url, token=config.token)


def _payload_matches_conversation(payload: dict, conversation_id: str) -> bool:
    if payload.get("message_id") == conversation_id:
        return True
    sender_crew_id = payload.get("sender_crew_id")
    recipient_crew_id = payload.get("recipient_crew_id")
    if sender_crew_id and recipient_crew_id:
        return conversation_id in {
            f"{sender_crew_id}:{recipient_crew_id}",
            f"{recipient_crew_id}:{sender_crew_id}",
        }
    return sender_crew_id == conversation_id


def main() -> None:
    app()


if __name__ == "__main__":
    main()
