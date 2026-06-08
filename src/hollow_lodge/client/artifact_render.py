from __future__ import annotations

from typing import Any

from hollow_lodge.client.render_packets import RenderAction, RenderPacket


_ARTIFACT_CONTEXT_FIELDS = (
    "artifact_id",
    "contract_id",
    "title",
    "kind",
    "public_summary",
    "full_text",
    "source_chain",
    "visible_flags",
    "proof_lanes",
    "phase_relevance",
    "copy_policy",
    "source_artifact_id",
    "contamination_flags",
    "is_copy",
)


def _shape_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: artifact[key]
        for key in _ARTIFACT_CONTEXT_FIELDS
        if key in artifact
    }


def _shape_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        key: edge[key]
        for key in ("source_id", "target_id", "relation", "public_summary")
        if key in edge
    }


def _shape_artifact_graph(graph: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: graph[key]
        for key in ("contract_id",)
        if key in graph
    }
    shaped["artifacts"] = [
        _shape_artifact(artifact)
        for artifact in graph.get("artifacts", [])
    ]
    shaped["edges"] = [
        _shape_edge(edge)
        for edge in graph.get("edges", [])
    ]
    return shaped


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
        agent_context={"artifact": _shape_artifact(artifact)},
        suggested_prompts=[
            "Compare this artifact against the known graph",
            "Review the source material",
            "Check whether visible material supports a working hypothesis",
        ],
        actions=[
            RenderAction(label="Review source material", intent="review_artifact"),
            RenderAction(label="Compare artifacts", intent="check_artifact"),
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
        agent_context={"artifact_graph": _shape_artifact_graph(graph)},
        suggested_prompts=[
            "Compare two artifacts",
            "Open a source artifact",
            "Review visible source connections",
        ],
        actions=[
            RenderAction(label="Compare artifacts", intent="check_artifact"),
        ],
    )
