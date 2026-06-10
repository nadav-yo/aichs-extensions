import re
from datetime import datetime, timezone


EXTENSION_DESCRIPTION = "Stores compact handoff notes and spools large tool outputs to extension artifacts."

_HANDOFF_STATE = "handoff"
_OUTPUT_INDEX_STATE = "output_index"
_DEFAULT_SPOOL_THRESHOLD = 12000
_PREVIEW_CHARS = 2000
_MAX_SUMMARY_CHARS = 1200
_MAX_ITEM_CHARS = 240
_MAX_ITEMS = 20
_MAX_OUTPUT_RECORDS = 30


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.tool(
        name="save_handoff",
        description=(
            "Save a compact continuation handoff for the current task. Use this "
            "for explicit working state: goal, decisions, findings, blockers, "
            "next steps, and references to large outputs. Do not store hidden "
            "reasoning, secrets, raw transcripts, or facts that are easy to "
            "rediscover from the repo."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Short task-state summary, ideally under a few paragraphs.",
                },
                "next": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concrete next steps to resume from.",
                },
                "decisions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Decisions or constraints that should carry forward.",
                },
                "blockers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Known blockers or open questions.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relevant workspace files or artifact paths.",
                },
            },
            "required": ["summary"],
        },
        execute=save_handoff,
    )
    registry.tool(
        name="read_handoff",
        description="Read the compact continuation handoff saved for this workspace/conversation.",
        input_schema={"type": "object", "properties": {}},
        execute=read_handoff,
        parallel_safe=True,
    )
    registry.tool(
        name="clear_handoff",
        description="Clear the saved continuation handoff after it is obsolete.",
        input_schema={"type": "object", "properties": {}},
        execute=clear_handoff,
    )
    registry.tool(
        name="list_spooled_outputs",
        description="List recent large tool outputs saved as extension artifacts.",
        input_schema={"type": "object", "properties": {}},
        execute=list_spooled_outputs,
        parallel_safe=True,
    )
    registry.context("Context handoff", handoff_context)
    registry.hook("after_tool_result", spool_large_tool_output)
    registry.status_badge(name="context_resilience", provider=context_badge)
    registry.panel(name="context_resilience", title="Context Resilience", provider=context_panel)


def save_handoff(ctx, inputs):
    summary = _clean_text(inputs.get("summary"), _MAX_SUMMARY_CHARS)
    if not summary:
        return "[tool error] save_handoff requires a non-empty summary."

    handoff = {
        "updated_at": _now(),
        "summary": summary,
        "next": _clean_items(inputs.get("next")),
        "decisions": _clean_items(inputs.get("decisions")),
        "blockers": _clean_items(inputs.get("blockers")),
        "files": _clean_items(inputs.get("files")),
    }
    ctx.storage.save_state(handoff, _HANDOFF_STATE)
    return "Handoff saved."


def read_handoff(ctx, inputs):
    handoff = ctx.storage.load_state(_HANDOFF_STATE)
    if not handoff:
        return "(no handoff saved)"
    return _render_handoff(handoff)


def clear_handoff(ctx, inputs):
    ctx.storage.save_state({}, _HANDOFF_STATE)
    return "Handoff cleared."


def list_spooled_outputs(ctx, inputs):
    records = _load_output_records(ctx.storage)
    if not records:
        return "(no spooled outputs)"
    lines = ["Spooled outputs:"]
    for record in records[-_MAX_OUTPUT_RECORDS:]:
        lines.append(
            "- {created_at} {tool_name}: {chars} chars -> {path}".format(
                created_at=record.get("created_at", "unknown"),
                tool_name=record.get("tool_name", "tool"),
                chars=record.get("chars", 0),
                path=record.get("path", ""),
            )
        )
    return "\n".join(lines)


def handoff_context(ctx):
    handoff = ctx.storage.load_state(_HANDOFF_STATE)
    if not handoff:
        return ""
    return (
        "A compact continuation handoff is saved for this workspace. "
        "Use read_handoff before resuming work after context loss.\n\n"
        + _render_handoff(handoff)
    )


def spool_large_tool_output(ctx):
    if not ctx.output:
        return
    threshold = _spool_threshold(ctx.storage)
    if len(ctx.output) <= threshold:
        return

    created = datetime.now(timezone.utc)
    filename = "{stamp}-{tool}.txt".format(
        stamp=created.strftime("%Y%m%dT%H%M%SZ"),
        tool=_safe_name(ctx.tool_name or "tool"),
    )
    path = ctx.storage.save_artifact(filename, ctx.output)
    record = {
        "created_at": created.isoformat(),
        "tool_name": ctx.tool_name or "tool",
        "chars": len(ctx.output),
        "path": path,
    }
    records = _load_output_records(ctx.storage)
    records.append(record)
    ctx.storage.save_state({"outputs": records[-_MAX_OUTPUT_RECORDS:]}, _OUTPUT_INDEX_STATE)

    preview = ctx.output[:_PREVIEW_CHARS].rstrip()
    ctx.output = (
        "[large tool output saved by context-resilience]\n"
        f"Tool: {record['tool_name']}\n"
        f"Characters: {record['chars']}\n"
        f"Path: {path}\n\n"
        f"Preview:\n{preview}"
    )


def context_badge(ctx):
    handoff = ctx.storage.load_state(_HANDOFF_STATE)
    records = _load_output_records(ctx.storage)
    if handoff:
        return {
            "label": "Handoff",
            "tooltip": "Context handoff is saved",
            "tone": "accent",
            "panel": "context_resilience",
        }
    if records:
        return {
            "label": "Outputs",
            "tooltip": "Large outputs have been spooled",
            "tone": "",
            "panel": "context_resilience",
        }
    return {
        "label": "Handoff",
        "tooltip": "No handoff saved yet",
        "tone": "",
        "panel": "context_resilience",
        "visible": False,
    }


def context_panel(ctx):
    handoff = ctx.storage.load_state(_HANDOFF_STATE)
    records = _load_output_records(ctx.storage)
    sections = []
    if handoff:
        sections.append({
            "heading": "Saved handoff",
            "items": [{
                "title": _clean_text(handoff.get("summary"), 160) or "Handoff",
                "subtitle": handoff.get("updated_at", ""),
                "body": _render_handoff(handoff),
            }],
        })
    else:
        sections.append({
            "heading": "Saved handoff",
            "items": [{"title": "None"}],
        })

    output_items = []
    for record in records[-5:]:
        output_items.append({
            "title": f"{record.get('tool_name', 'tool')} output",
            "subtitle": f"{record.get('chars', 0)} chars",
            "body": record.get("path", ""),
            "action": {"type": "copy", "label": "Copy path", "text": record.get("path", "")},
        })
    sections.append({
        "heading": "Recent spooled outputs",
        "items": output_items or [{"title": "None"}],
    })
    sections.append({
        "heading": "Tools",
        "items": [
            {"title": "save_handoff", "subtitle": "Persist compact task state."},
            {"title": "read_handoff", "subtitle": "Read saved task state."},
            {"title": "list_spooled_outputs", "subtitle": "List large output artifacts."},
            {"title": "clear_handoff", "subtitle": "Clear obsolete handoff state."},
        ],
    })
    return {
        "title": "Context Resilience",
        "body": "Stores explicit handoff state and keeps bulky outputs out of model context.",
        "sections": sections,
    }


def _render_handoff(handoff):
    lines = []
    updated = _clean_text(handoff.get("updated_at"), 80)
    if updated:
        lines.append(f"Updated: {updated}")
    summary = _clean_text(handoff.get("summary"), _MAX_SUMMARY_CHARS)
    if summary:
        lines.extend(["", "Summary:", summary])
    for key, title in (
        ("decisions", "Decisions"),
        ("blockers", "Blockers"),
        ("files", "Files and artifacts"),
        ("next", "Next steps"),
    ):
        items = _clean_items(handoff.get(key))
        if not items:
            continue
        lines.extend(["", f"{title}:"])
        lines.extend(f"- {item}" for item in items)
    return "\n".join(lines).strip()


def _spool_threshold(storage):
    config = storage.load_config()
    try:
        value = int(config.get("spool_threshold", _DEFAULT_SPOOL_THRESHOLD))
    except (TypeError, ValueError):
        value = _DEFAULT_SPOOL_THRESHOLD
    return max(1000, value)


def _load_output_records(storage):
    data = storage.load_state(_OUTPUT_INDEX_STATE)
    records = data.get("outputs", []) if isinstance(data, dict) else []
    if not isinstance(records, list):
        return []
    clean = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = _clean_text(record.get("path"), 1000)
        if not path:
            continue
        clean.append({
            "created_at": _clean_text(record.get("created_at"), 80),
            "tool_name": _safe_name(record.get("tool_name") or "tool"),
            "chars": _safe_int(record.get("chars")),
            "path": path,
        })
    return clean[-_MAX_OUTPUT_RECORDS:]


def _clean_items(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = []
    seen = set()
    for raw in value:
        item = _clean_text(raw, _MAX_ITEM_CHARS)
        folded = item.casefold()
        if item and folded not in seen:
            items.append(item)
            seen.add(folded)
        if len(items) >= _MAX_ITEMS:
            break
    return items


def _clean_text(value, max_chars):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "..."
    return text


def _safe_name(value):
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "tool")).strip("._-")
    return text or "tool"


def _safe_int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _now():
    return datetime.now(timezone.utc).isoformat()
