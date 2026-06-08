from __future__ import annotations

from typing import Any

from hollow_lodge.client.render_packets import RenderAction, RenderPacket


def build_artifact_packet(artifact: dict[str, Any]) -> RenderPacket:
    lines = [
        f"Artifact: {artifact['title']}",
        f"ID: {artifact['artifact_id']}",
        f"Type: {artifact['kind']}",
        "",
        artifact.get("public_summary") or "No public summary.",
    ]
    full_text = artifact.get("full_text")
    if full_text:
        lines.extend(["", f"Source: {full_text}"])
    source_chain = artifact.get("source_chain", [])
    if source_chain:
        lines.extend(["", "Provenance:"])
        lines.extend(f"- {source}" for source in source_chain)
    visible_flags = artifact.get("visible_flags", [])
    if visible_flags:
        lines.extend(["", "Visible flags:"])
        lines.extend(f"- {flag}" for flag in visible_flags)
    return RenderPacket(
        surface="artifact",
        player_markdown="\n".join(lines),
        agent_context={"artifact": artifact},
        suggested_prompts=[
            "Compare this artifact against the known graph",
            "Check whether this is safe to cite",
            "Draft a dossier citation",
            "Consider a transfer request",
        ],
        actions=[
            RenderAction(label="Check citation safety", intent="check_artifact"),
            RenderAction(label="Draft dossier citation", intent="cite_artifact"),
            RenderAction(
                label="Request artifact transfer",
                intent="transfer_artifact",
                requires_confirmation=True,
            ),
        ],
    )


def build_artifact_graph_packet(graph: dict[str, Any]) -> RenderPacket:
    lines = ["Known Artifacts"]
    contract_id = graph.get("contract_id")
    if contract_id:
        lines.append(f"Contract: {contract_id}")
    lines.append("")
    artifacts = graph.get("artifacts", [])
    if artifacts:
        for artifact in artifacts:
            lines.append(
                f"- {artifact['title']} ({artifact['artifact_id']}, {artifact['kind']}): "
                f"{artifact.get('public_summary') or 'No public summary.'}"
            )
    else:
        lines.append("- none")
    edges = graph.get("edges", [])
    lines.extend(["", "Known Connections:"])
    if edges:
        for edge in edges:
            summary = edge.get("public_summary")
            suffix = f": {summary}" if summary else ""
            lines.append(
                f"- {edge['source_id']} {edge['relation']} {edge['target_id']}{suffix}"
            )
    else:
        lines.append("- none")
    return RenderPacket(
        surface="artifact_graph",
        player_markdown="\n".join(lines),
        agent_context={"artifact_graph": graph},
        suggested_prompts=[
            "Compare two artifacts",
            "Open a source artifact",
            "Check whether an artifact is safe to cite",
        ],
        actions=[
            RenderAction(label="Compare artifacts", intent="check_artifact"),
            RenderAction(label="Draft dossier citation", intent="cite_artifact"),
            RenderAction(
                label="Request artifact transfer",
                intent="transfer_artifact",
                requires_confirmation=True,
            ),
        ],
    )
