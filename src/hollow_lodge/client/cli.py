import json
from pathlib import Path

import typer

from hollow_lodge import __version__
from hollow_lodge.client.api import HollowLodgeApi, new_command_key
from hollow_lodge.client.artifact_render import (
    build_artifact_graph_packet,
    build_artifact_packet,
)
from hollow_lodge.client.codex_mcp_config import install_codex_mcp_server
from hollow_lodge.client.config import (
    ClientConfig,
    OnboardingConfig,
    load_config,
    save_config,
    save_onboarding_config,
)
from hollow_lodge.client.handler import normalize_action_draft
from hollow_lodge.client.local_log import LocalEventLog
from hollow_lodge.client.paths import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOCAL_LOG_PATH,
    DEFAULT_ONBOARDING_STATE_PATH,
)
from hollow_lodge.client.render import render_contract_board, render_crew_board, render_inbox
from hollow_lodge.client.render_packets import (
    build_deal_acceptance_preview_packet,
    build_deals_packet,
    build_contract_board_packet,
    build_crew_board_packet,
    build_inbox_packet,
    payload_matches_conversation,
)


DEFAULT_SERVER_URL = "https://server.thehollowlodge.com"

app = typer.Typer(
    name="hollow-lodge",
    help="The Hollow Lodge CLI.",
    no_args_is_help=True,
)
dossier_app = typer.Typer(help="Manage the crew proof dossier.", no_args_is_help=False)
proof_app = typer.Typer(help="Manage proof fragments.", no_args_is_help=True)
action_app = typer.Typer(help="Manage submitted actions.", no_args_is_help=True)
phase_app = typer.Typer(help="Preview and resolve contract phases.", no_args_is_help=True)
packet_lead_app = typer.Typer(help="Manage Packet Lead votes.", no_args_is_help=True)
admin_app = typer.Typer(help="Manage Lodge administration.", no_args_is_help=True)
codex_app = typer.Typer(help="Configure Codex integration.", no_args_is_help=True)
deal_app = typer.Typer(help="Manage escrowed artifact deals.", no_args_is_help=True)
app.add_typer(dossier_app, name="dossier")
app.add_typer(proof_app, name="proof")
app.add_typer(action_app, name="action")
app.add_typer(phase_app, name="phase")
app.add_typer(packet_lead_app, name="packet-lead")
app.add_typer(admin_app, name="admin")
app.add_typer(codex_app, name="codex")
app.add_typer(deal_app, name="deal")


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
            display_name=response["display_name"],
            token=response["token"],
        ),
    )
    typer.echo(response["player_id"])


@app.command()
def onboard(
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    name: str | None = typer.Option(None, "--name", help="Display name."),
    invite: str | None = typer.Option(None, "--invite", help="Invite code, if you already have one."),
    contact: str | None = typer.Option(
        None,
        "--contact",
        help="Contact handle or email for access-key requests.",
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    onboarding_state: Path = typer.Option(
        DEFAULT_ONBOARDING_STATE_PATH,
        "--onboarding-state",
        help="Pending onboarding state path.",
    ),
) -> None:
    """Register with an invite or request an access key."""
    display_name = name or typer.prompt("Display name")
    api = HollowLodgeApi(server_url=server)
    if invite:
        response = api.register(
            invite_code=invite,
            display_name=display_name,
            idempotency_key=new_command_key("register"),
        )
        save_config(
            config,
            ClientConfig(
                server_url=server,
                player_id=response["player_id"],
                display_name=response["display_name"],
                token=response["token"],
            ),
        )
        if onboarding_state.exists():
            onboarding_state.unlink()
        typer.echo(f"registered {response['player_id']}")
        return

    response = api.request_access_key(
        display_name=display_name,
        contact=contact,
        idempotency_key=new_command_key("key-request"),
    )
    save_onboarding_config(
        onboarding_state,
        OnboardingConfig(
            server_url=server,
            display_name=display_name,
            contact=contact,
            request_id=response["request_id"],
            status=response["status"],
        ),
    )
    typer.echo(f"pending {response['request_id']}")


@admin_app.command("invite-create")
def admin_invite_create(
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """Create a one-use invite code."""
    response = HollowLodgeApi(server_url=server).create_invite(
        admin_token=admin_token,
        idempotency_key=new_command_key("admin-invite-create"),
    )
    typer.echo(response["invite_code"])


@admin_app.command("key-requests")
def admin_key_requests(
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """List access-key requests."""
    response = HollowLodgeApi(server_url=server).list_key_requests(
        admin_token=admin_token,
    )
    for key_request in response["key_requests"]:
        contact = key_request.get("contact") or "-"
        typer.echo(
            f"{key_request['request_id']} {key_request['status']} "
            f"{key_request['display_name']} {contact}"
        )


@admin_app.command("invites")
def admin_invites(
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """List invite inventory without exposing invite codes."""
    response = HollowLodgeApi(server_url=server).list_invites(
        admin_token=admin_token,
    )
    for invite in response["invites"]:
        state = "used" if invite["used"] else "unused"
        typer.echo(f"{invite['invite_id']} {state}")


@admin_app.command("players")
def admin_players(
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """List registered players without token material."""
    response = HollowLodgeApi(server_url=server).list_players(
        admin_token=admin_token,
    )
    for player in response["players"]:
        state = "revoked" if player["token_revoked"] else "active"
        typer.echo(f"{player['player_id']} {state} {player['display_name']}")


@admin_app.command("event-log-verify")
def admin_event_log_verify(
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """Verify the authoritative event-log hash chain."""
    response = HollowLodgeApi(server_url=server).verify_event_log(
        admin_token=admin_token,
    )
    status_text = "ok" if response["ok"] else "failed"
    repair_note = " repaired" if response.get("repaired_trailing_row") else ""
    typer.echo(f"{status_text} {response['event_count']} events{repair_note}")


@admin_app.command("event-log-export")
def admin_event_log_export(
    output: Path = typer.Option(..., "--output", help="Destination JSON file."),
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """Export the authoritative event log as JSON."""
    response = HollowLodgeApi(server_url=server).export_event_log(
        admin_token=admin_token,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"wrote {output}")


@admin_app.command("key-request-approve")
def admin_key_request_approve(
    request_id: str = typer.Argument(..., help="Access-key request id."),
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """Approve an access-key request and print its invite code."""
    response = HollowLodgeApi(server_url=server).approve_key_request(
        request_id=request_id,
        admin_token=admin_token,
        idempotency_key=new_command_key("admin-key-request-approve"),
    )
    typer.echo(response["invite_code"])


@admin_app.command("contract-activate")
def admin_contract_activate(
    seed_file: Path = typer.Option(..., "--seed-file", help="Contract seed JSON file."),
    server: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server",
        help="Authoritative server URL. Defaults to the official Lodge.",
    ),
    admin_token: str = typer.Option(
        ...,
        "--admin-token",
        envvar="HOLLOW_LODGE_ADMIN_TOKEN",
        help="Server admin token.",
    ),
) -> None:
    """Activate a contract content seed on the authoritative server."""
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    response = HollowLodgeApi(server_url=server).activate_contract_seed(
        seed=seed,
        admin_token=admin_token,
        idempotency_key=new_command_key("admin-contract-activate"),
    )
    typer.echo(f"{response['contract_id']} {response['lifecycle_status']}")


@codex_app.command("install-mcp")
def codex_install_mcp(
    config: Path = typer.Option(
        Path.home() / ".codex" / "config.toml",
        "--config",
        help="Codex config.toml path.",
    ),
) -> None:
    """Register The Hollow Lodge MCP server with Codex."""
    changed = install_codex_mcp_server(config)
    typer.echo("registered the-hollow-lodge MCP server" if changed else "the-hollow-lodge MCP server already registered")


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
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show the contract board."""
    board = _api_from_config(load_config(config)).contracts()
    if as_json:
        _echo_packet(build_contract_board_packet(board), as_json=True)
    else:
        typer.echo(render_contract_board(board))


@app.command()
def inbox(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show the personal inbox."""
    current = load_config(config)
    inbox_data = _api_from_config(current).inbox()
    if current.display_name:
        inbox_data.setdefault("display_name", current.display_name)
    if as_json:
        _echo_packet(build_inbox_packet(inbox_data), as_json=True)
    else:
        typer.echo(render_inbox(inbox_data))


@app.command("crew-board")
def crew_board(
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show the active crew board."""
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    board = _api_from_config(current).crew_board(crew_id=target_crew_id)
    if as_json:
        _echo_packet(build_crew_board_packet(board), as_json=True)
    else:
        typer.echo(render_crew_board(board))


@app.command()
def artifacts(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show visible artifacts and known connections."""
    packet = build_artifact_graph_packet(_api_from_config(load_config(config)).artifacts())
    _echo_packet(packet, as_json=as_json)


@app.command()
def artifact(
    artifact_id: str = typer.Argument(..., help="Artifact id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Inspect a visible artifact."""
    packet = build_artifact_packet(
        _api_from_config(load_config(config)).artifact(artifact_id=artifact_id)
    )
    _echo_packet(packet, as_json=as_json)


@app.command("artifact-transfer")
def artifact_transfer(
    artifact_id: str = typer.Argument(..., help="Artifact id."),
    recipient: str = typer.Argument(..., help="Recipient player id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Transfer a copy of a visible artifact to another player."""
    response = _api_from_config(load_config(config)).transfer_artifact(
        artifact_id=artifact_id,
        recipient_player_id=recipient,
        idempotency_key=new_command_key("artifact-transfer"),
    )
    typer.echo(f"{response['artifact_id']} transferred")


@app.command()
def sync(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    local_log: Path = typer.Option(
        DEFAULT_LOCAL_LOG_PATH,
        "--local-log",
        help="Local perspective log path.",
    ),
) -> None:
    """Sync visible server events into the local perspective log."""
    log = LocalEventLog(local_log)
    events = _api_from_config(load_config(config)).visible_events()
    synced = log.sync_visible_server_events(events)
    typer.echo(f"synced {synced} events")


@app.command()
def replay(
    since: int = typer.Option(0, "--since", help="Replay server events after this sequence."),
    local_log: Path = typer.Option(
        DEFAULT_LOCAL_LOG_PATH,
        "--local-log",
        help="Local perspective log path.",
    ),
) -> None:
    """Replay the local perspective log."""
    for line in LocalEventLog(local_log).render_replay(since_sequence=since):
        typer.echo(line)


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


@proof_app.command("transfer")
def proof_transfer(
    fragment_id: str = typer.Argument(..., help="Proof fragment id."),
    recipient: str = typer.Argument(..., help="Recipient player id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Transfer a proof fragment to another player."""
    response = _api_from_config(load_config(config)).transfer_proof_fragment(
        fragment_id=fragment_id,
        recipient_player_id=recipient,
        idempotency_key=new_command_key("proof-transfer"),
    )
    typer.echo(f"{response['fragment_id']} transferred")


@app.command()
def act(
    intent: str = typer.Argument(..., help="Freeform action intent."),
    confirm: bool = typer.Option(False, "--confirm", help="Submit after normalization."),
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    local_log: Path = typer.Option(
        DEFAULT_LOCAL_LOG_PATH,
        "--local-log",
        help="Local perspective log path.",
    ),
) -> None:
    """Normalize and optionally submit a freeform action."""
    current = load_config(config)
    target_crew_id = crew_id or current.active_crew_id
    if target_crew_id is None:
        raise typer.BadParameter("crew id required when no active crew is configured")
    frame = normalize_action_draft(
        local_log=LocalEventLog(local_log),
        intent=intent,
        actor_player_id=current.player_id,
        crew_id=target_crew_id,
    )
    if not confirm:
        typer.echo(f"draft {frame.scope}: {frame.approach}")
        return
    response = _api_from_config(current).submit_action(
        crew_id=target_crew_id,
        intent=intent,
        idempotency_key=new_command_key("action-submit"),
    )
    typer.echo(response["action_id"])


@action_app.command("edit")
def action_edit(
    action_id: str = typer.Argument(..., help="Submitted action id."),
    intent: str = typer.Argument(..., help="Replacement action intent."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Edit a submitted action before phase lock."""
    response = _api_from_config(load_config(config)).edit_action(
        action_id=action_id,
        intent=intent,
        idempotency_key=new_command_key("action-edit"),
    )
    typer.echo(f"{response['action_id']} {response['status']}")


@action_app.command("cancel")
def action_cancel(
    action_id: str = typer.Argument(..., help="Submitted action id."),
    confirm: bool = typer.Option(False, "--confirm", help="Cancel the action on the server."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Cancel a submitted action before phase lock."""
    if not confirm:
        typer.echo(f"no server mutation occurred; rerun with --confirm to cancel {action_id}")
        return
    response = _api_from_config(load_config(config)).cancel_action(
        action_id=action_id,
        idempotency_key=new_command_key("action-cancel"),
    )
    typer.echo(f"{response['action_id']} {response['status']}")


@phase_app.command("preview-lock")
def phase_preview_lock(
    contract_id: str = typer.Argument("contract_false_finger", help="Contract id."),
    hours_elapsed: int = typer.Option(6, "--hours-elapsed", help="Elapsed hours to submit on lock."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Preview phase lock consequences without mutation."""
    current = load_config(config)
    api = _api_from_config(current)
    board = api.contracts()
    _echo_phase_lock_preview(
        contract=_contract_for_preview(board, contract_id),
        contract_id=contract_id,
        hours_elapsed=hours_elapsed,
    )


@phase_app.command("lock")
def phase_lock(
    contract_id: str = typer.Argument("contract_false_finger", help="Contract id."),
    hours_elapsed: int = typer.Option(6, "--hours-elapsed", help="Elapsed hours to submit on lock."),
    confirm: bool = typer.Option(False, "--confirm", help="Perform the server phase lock."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Lock and resolve a phase when confirmed."""
    if not confirm:
        typer.echo(f"no server mutation occurred; rerun with --confirm to lock {contract_id}")
        return
    response = _api_from_config(load_config(config)).lock_auction_preview_phase(
        contract_id=contract_id,
        hours_elapsed=hours_elapsed,
        idempotency_key=new_command_key("phase-lock"),
    )
    typer.echo(f"{response.get('status', 'resolved')} {len(response.get('standings', []))} standings")


@deal_app.command("list")
def deal_list(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """List visible escrowed artifact deals."""
    response = _api_from_config(load_config(config)).deals()
    deals = response.get("deals", [])
    if not deals:
        typer.echo("no deals")
        return
    for deal in deals:
        typer.echo(f"{deal['deal_id']} {deal['status']}")


@deal_app.command("show")
def deal_show(
    deal_id: str = typer.Argument(..., help="Deal id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Show full escrowed artifact deal terms."""
    deal = _deal_by_id(_api_from_config(load_config(config)).deals(), deal_id)
    typer.echo(build_deals_packet({"deals": [deal]}).player_markdown)


@deal_app.command("preview-accept")
def deal_preview_accept(
    deal_id: str = typer.Argument(..., help="Deal id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Preview consequences of accepting an escrowed artifact deal."""
    current = load_config(config)
    deal = _deal_by_id(_api_from_config(current).deals(), deal_id)
    viewer_crew_ids = [current.active_crew_id] if current.active_crew_id else []
    packet = build_deal_acceptance_preview_packet(
        {
            "deal": deal,
            "viewer_crew_ids": viewer_crew_ids,
        }
    )
    typer.echo(packet.player_markdown)


@deal_app.command("propose")
def deal_propose(
    from_crew: str | None = typer.Option(
        None,
        "--from-crew",
        help="Proposing crew id; defaults to active crew.",
    ),
    to_crew: str = typer.Option(..., "--to-crew", help="Recipient crew id."),
    offer: list[str] = typer.Option(..., "--offer", help="Offered artifact id."),
    request: list[str] = typer.Option(..., "--request", help="Requested artifact id."),
    soft_term: list[str] | None = typer.Option(None, "--soft-term", help="Non-binding soft term."),
    contract_id: str = typer.Option(
        "contract_false_finger",
        "--contract-id",
        help="Contract id for the deal.",
    ),
    expires_phase: str | None = typer.Option(
        None,
        "--expires-phase",
        help="Phase after which the deal expires.",
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Propose an escrowed artifact deal."""
    current = load_config(config)
    proposer_crew_id = from_crew or current.active_crew_id
    if proposer_crew_id is None:
        raise typer.BadParameter("from crew required when no active crew is configured")
    response = _api_from_config(current).propose_deal(
        contract_id=contract_id,
        proposer_crew_id=proposer_crew_id,
        recipient_crew_id=to_crew,
        offered_artifact_ids=offer,
        requested_artifact_ids=request,
        soft_terms=soft_term or [],
        expires_phase=expires_phase,
        idempotency_key=new_command_key("deal-propose"),
    )
    typer.echo(f"{response['deal_id']} {response['status']}")


@deal_app.command("accept")
def deal_accept(
    deal_id: str = typer.Argument(..., help="Deal id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Accept an escrowed artifact deal."""
    response = _api_from_config(load_config(config)).accept_deal(
        deal_id=deal_id,
        idempotency_key=new_command_key("deal-accept"),
    )
    typer.echo(f"{response['deal_id']} {response['status']}")


@deal_app.command("decline")
def deal_decline(
    deal_id: str = typer.Argument(..., help="Deal id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Decline an escrowed artifact deal."""
    response = _api_from_config(load_config(config)).decline_deal(
        deal_id=deal_id,
        idempotency_key=new_command_key("deal-decline"),
    )
    typer.echo(f"{response['deal_id']} {response['status']}")


@deal_app.command("cancel")
def deal_cancel(
    deal_id: str = typer.Argument(..., help="Deal id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Cancel an escrowed artifact deal."""
    response = _api_from_config(load_config(config)).cancel_deal(
        deal_id=deal_id,
        idempotency_key=new_command_key("deal-cancel"),
    )
    typer.echo(f"{response['deal_id']} {response['status']}")


@dossier_app.callback(invoke_without_command=True)
def dossier(
    ctx: typer.Context,
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Show the crew proof dossier."""
    if ctx.invoked_subcommand is not None:
        return
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    typer.echo(_api_from_config(current).dossier(crew_id=target_crew_id))


@dossier_app.command("add-evidence")
def dossier_add_evidence(
    fragment_id: str,
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Add evidence to the crew proof dossier."""
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    response = _api_from_config(current).add_dossier_evidence(
        crew_id=target_crew_id,
        fragment_id=fragment_id,
        idempotency_key=new_command_key("dossier-evidence"),
    )
    typer.echo(response)


@dossier_app.command("claim")
def dossier_claim(
    text: str,
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Set the dossier claim."""
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    response = _api_from_config(current).update_dossier_claim(
        crew_id=target_crew_id,
        claim=text,
        idempotency_key=new_command_key("dossier-claim"),
    )
    typer.echo(response)


@dossier_app.command("cite-artifact")
def dossier_cite_artifact(
    artifact_id: str = typer.Argument(..., help="Artifact id."),
    claim: str = typer.Option(..., "--claim", help="Claim supported by the artifact."),
    quote: str = typer.Option(..., "--quote", help="Short quoted support from the artifact."),
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Cite an artifact directly in the crew proof dossier."""
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    response = _api_from_config(current).cite_artifact_in_dossier(
        crew_id=target_crew_id,
        artifact_id=artifact_id,
        claim=claim,
        quote=quote,
        idempotency_key=new_command_key("dossier-cite-artifact"),
    )
    typer.echo(response)


@dossier_app.command("frame")
def dossier_frame(
    claim: str | None = typer.Option(None, "--claim", help="Dossier claim."),
    evidence_id: list[str] | None = typer.Option(None, "--evidence-id", help="Evidence id."),
    reasoning: str | None = typer.Option(None, "--reasoning", help="Dossier reasoning."),
    weaknesses: str | None = typer.Option(None, "--weaknesses", help="Known weaknesses."),
    provenance_concerns: str | None = typer.Option(
        None,
        "--provenance-concerns",
        help="Known provenance concerns.",
    ),
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Update supplied dossier framing fields."""
    if (
        claim is None
        and evidence_id is None
        and reasoning is None
        and weaknesses is None
        and provenance_concerns is None
    ):
        raise typer.BadParameter("at least one framing field is required")
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    response = _api_from_config(current).update_dossier_framing(
        crew_id=target_crew_id,
        claim=claim,
        evidence_ids=evidence_id,
        reasoning=reasoning,
        weaknesses=weaknesses,
        provenance_concerns=provenance_concerns,
        idempotency_key=new_command_key("dossier-frame"),
    )
    typer.echo(response)


@packet_lead_app.command("vote")
def packet_lead_vote(
    player_id: str,
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Vote to replace the Packet Lead."""
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    response = _api_from_config(current).vote_packet_lead(
        crew_id=target_crew_id,
        player_id=player_id,
        idempotency_key=new_command_key("packet-lead-vote"),
    )
    typer.echo(response)


def _api_from_config(config: ClientConfig) -> HollowLodgeApi:
    return HollowLodgeApi(server_url=config.server_url, token=config.token)


def _target_crew_id(config: ClientConfig, crew_id: str | None) -> str:
    target_crew_id = crew_id or config.active_crew_id
    if target_crew_id is None:
        raise typer.BadParameter("crew id required when no active crew is configured")
    return target_crew_id


def _deal_by_id(response: dict, deal_id: str) -> dict:
    for deal in response.get("deals", []):
        if deal["deal_id"] == deal_id:
            return deal
    raise typer.BadParameter("deal not found")


def _contract_for_preview(response: dict, contract_id: str) -> dict:
    contracts = response.get("contracts", [])
    for contract in contracts:
        if contract.get("contract_id") == contract_id:
            return contract
    if len(contracts) == 1:
        return contracts[0]
    raise typer.BadParameter("contract not found")


def _echo_phase_lock_preview(*, contract: dict, contract_id: str, hours_elapsed: int) -> None:
    phase = contract.get("phase", {})
    phase_name = phase.get("name", "Auction Preview")
    remaining_hours = phase.get("remaining_hours")
    typer.echo(f"preview only: {contract_id} {phase_name}")
    if remaining_hours is not None:
        typer.echo(f"remaining hours: {remaining_hours}")
    typer.echo(f"lock request would use hours_elapsed={hours_elapsed}")
    typer.echo("no server mutation occurred; use `phase lock --confirm` to lock and resolve")


def _echo_packet(packet, *, as_json: bool) -> None:
    if as_json:
        typer.echo(packet.model_dump_json())
    else:
        typer.echo(packet.player_markdown)


def _payload_matches_conversation(payload: dict, conversation_id: str) -> bool:
    return payload_matches_conversation(payload, conversation_id)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
