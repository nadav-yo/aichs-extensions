EXTENSION_DESCRIPTION = "Adds compact canvas context for graph chat and run agents."


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.canvas_context("Canvas briefing", canvas_briefing)


def canvas_briefing(ctx):
    canvas = ctx.canvas
    graph = canvas.get("graph", {})
    nodes = graph.get("nodes", [])
    active_id = canvas.get("active_node_id")
    scoped_goal_id = canvas.get("scope_goal_id")
    run_node = canvas.get("node") or {}
    run_line = ""
    if run_node:
        run_line = (
            f" Current run node: #{run_node.get('id')} "
            f"{run_node.get('kind')} '{run_node.get('title')}'."
        )
    return (
        f"Canvas mode: {canvas.get('kind') or 'graph'}. "
        f"Graph nodes: {len(nodes)}. "
        f"Active node: {active_id or 'none'}. "
        f"Scoped goal: {scoped_goal_id or 'none'}."
        f"{run_line} Keep canvas changes compact and graph-native."
    )
