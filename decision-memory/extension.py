import re


EXTENSION_DESCRIPTION = "Adds small project decision memory tools for durable architecture and strategy choices."

_STATE_NAME = "decisions"
_MAX_TOPICS = 40
_MAX_DECISIONS_PER_TOPIC = 20
_MAX_TOPIC_CHARS = 64
_MAX_DECISION_CHARS = 300


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.tool(
        name="remember_decision",
        description=(
            "Save one short, durable project decision under a stable topic key. "
            "Use only for strong user-confirmed architecture, strategy, product, "
            "or implementation decisions that should survive across chats. Do not "
            "save transient plans, routine facts, tool output, summaries, guesses, "
            "secrets, or facts easily rediscovered from the repo."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Stable lowercase topic key, e.g. compaction or authentication.",
                },
                "decision": {
                    "type": "string",
                    "description": "One concise sentence stating the durable decision.",
                },
            },
            "required": ["topic", "decision"],
        },
        execute=remember_decision,
        approval="once",
    )
    registry.tool(
        name="recall_decisions",
        description="Return all remembered project decisions for one topic key.",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic key to recall, e.g. compaction or authentication.",
                },
            },
            "required": ["topic"],
        },
        execute=recall_decisions,
        parallel_safe=True,
    )
    registry.tool(
        name="list_decision_topics",
        description="List topic keys that have remembered project decisions.",
        input_schema={
            "type": "object",
            "properties": {},
        },
        execute=list_decision_topics,
        parallel_safe=True,
    )
    registry.context("Decision memory", decision_memory_context)


def remember_decision(ctx, inputs):
    topic = _normalize_topic(inputs.get("topic"))
    decision = _normalize_decision(inputs.get("decision"))
    if not topic:
        return "[tool error] remember_decision requires a non-empty topic key."
    if not decision:
        return "[tool error] remember_decision requires a non-empty decision sentence."
    if len(topic) > _MAX_TOPIC_CHARS:
        return f"[tool error] topic is too long; keep it under {_MAX_TOPIC_CHARS} characters."
    if len(decision) > _MAX_DECISION_CHARS:
        return f"[tool error] decision is too long; keep it under {_MAX_DECISION_CHARS} characters."

    data = _load_decisions(ctx.storage)
    if topic not in data and len(data) >= _MAX_TOPICS:
        return f"[tool error] decision memory is capped at {_MAX_TOPICS} topics."

    items = data.setdefault(topic, [])
    folded = {item.casefold() for item in items}
    if decision.casefold() in folded:
        return f"Decision already remembered under {topic!r}."
    if len(items) >= _MAX_DECISIONS_PER_TOPIC:
        return (
            f"[tool error] topic {topic!r} already has "
            f"{_MAX_DECISIONS_PER_TOPIC} decisions."
        )

    items.append(decision)
    _save_decisions(ctx.storage, data)
    return f"Remembered decision under {topic!r}."


def recall_decisions(ctx, inputs):
    topic = _normalize_topic(inputs.get("topic"))
    if not topic:
        return "[tool error] recall_decisions requires a non-empty topic key."
    items = _load_decisions(ctx.storage).get(topic, [])
    if not items:
        return f"(no decisions remembered for {topic!r})"
    lines = [f"Decisions for {topic!r}:"]
    lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def list_decision_topics(ctx, inputs):
    topics = sorted(_load_decisions(ctx.storage))
    if not topics:
        return "(no decision topics remembered)"
    return "Decision topics:\n" + "\n".join(f"- {topic}" for topic in topics)


def decision_memory_context(ctx):
    topics = sorted(_load_decisions(ctx.storage))
    topic_text = ", ".join(topics[:30]) if topics else "none yet"
    if len(topics) > 30:
        topic_text += f", ... ({len(topics)} total)"
    return (
        "Decision memory is enabled for this workspace. Use recall_decisions "
        "before revisiting a durable architecture, product, strategy, or "
        "implementation topic that may have prior decisions. Use "
        "remember_decision only when the user clearly makes or confirms a "
        "strong durable decision; save one short sentence under a stable "
        "lowercase topic key. Do not remember transient plans, routine "
        "implementation details, tool output, guesses, summaries, secrets, or "
        "facts easily rediscovered from the repo. Use list_decision_topics "
        f"when you need to discover topics. Known decision topics: {topic_text}."
    )


def _load_decisions(storage):
    data = storage.load_state(_STATE_NAME)
    decisions = {}
    for raw_topic, raw_items in data.items():
        topic = _normalize_topic(raw_topic)
        if not topic or not isinstance(raw_items, list):
            continue
        items = []
        seen = set()
        for raw_item in raw_items:
            item = _normalize_decision(raw_item)
            folded = item.casefold()
            if item and folded not in seen:
                items.append(item)
                seen.add(folded)
        if items:
            decisions[topic] = items[:_MAX_DECISIONS_PER_TOPIC]
    return decisions


def _save_decisions(storage, data):
    storage.save_state(dict(sorted(data.items())), _STATE_NAME)


def _normalize_topic(value):
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalize_decision(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()
