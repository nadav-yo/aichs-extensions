EXTENSION_DESCRIPTION = "Adds canvas-only note tools that are available to canvas agents."


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.canvas_tool(
        name="canvas_project_note",
        description="Read the saved project note for canvas agents.",
        input_schema={"type": "object", "properties": {}},
        execute=canvas_project_note,
        parallel_safe=True,
    )
    registry.canvas_tool(
        name="remember_canvas_note",
        description="Save a short project note for later canvas runs.",
        input_schema={
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "Short project note to remember for canvas work.",
                }
            },
            "required": ["note"],
        },
        execute=remember_canvas_note,
    )


def canvas_project_note(ctx, inputs):
    note = str(ctx.storage.load_config().get("note") or "").strip()
    if not note:
        return "No canvas project note is configured yet."
    return note


def remember_canvas_note(ctx, inputs):
    note = str((inputs or {}).get("note") or "").strip()
    if not note:
        return "[tool error] note is required."
    ctx.storage.save_config({"note": note})
    return "Saved canvas project note."
