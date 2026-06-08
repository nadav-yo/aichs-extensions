"""Prototype extension-managed long-running processes for aichs."""

from __future__ import annotations

import json
import sys

from services.processes import ManagedProcessError, RuntimeProcessApi, get_process_manager


EXTENSION_DESCRIPTION = (
    "Manages named long-running workspace processes through the core process runtime."
)

_DEFAULT_SESSION = "demo"


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.command(
        name="process",
        description="Manage extension-owned named processes",
        execute=process_command,
        capabilities=["process_control", "shell"],
    )
    registry.tool(
        name="process_status",
        description="Return the status of configured extension-managed processes.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Optional process name."},
            },
        },
        execute=lambda ctx, inputs: _status_text(_tool_processes(ctx), _sessions(ctx), inputs.get("name") or ""),
        parallel_safe=True,
    )
    registry.tool(
        name="process_logs",
        description="Read recent logs from an extension-managed process.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Process name."},
                "lines": {"type": "integer", "description": "Number of log lines."},
            },
            "required": ["name"],
        },
        execute=lambda ctx, inputs: _logs_text(
            _tool_processes(ctx),
            str(inputs.get("name") or ""),
            int(inputs.get("lines") or 80),
        ),
        parallel_safe=True,
    )
    registry.tool(
        name="process_start",
        description="Start a configured extension-managed process.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Process name."},
            },
            "required": ["name"],
        },
        execute=lambda ctx, inputs: _start_text(
            _tool_processes(ctx),
            _sessions(ctx),
            str(inputs.get("name") or ""),
        ),
        approval="once",
    )
    registry.tool(
        name="process_stop",
        description="Stop a running extension-managed process.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Process name."},
            },
            "required": ["name"],
        },
        execute=lambda ctx, inputs: _stop_text(_tool_processes(ctx), str(inputs.get("name") or "")),
        approval="once",
    )
    registry.tool(
        name="process_write",
        description="Write text to a running extension-managed process stdin.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Process name."},
                "text": {"type": "string", "description": "Text to write."},
            },
            "required": ["name", "text"],
        },
        execute=lambda ctx, inputs: _write_text(
            _tool_processes(ctx),
            str(inputs.get("name") or ""),
            str(inputs.get("text") or ""),
        ),
        approval="once",
    )
    registry.status_badge(name="process_sessions", provider=process_badge)
    registry.panel(name="process_sessions", title="Processes", provider=process_panel)


def process_command(ctx, args):
    parts = str(args or "").split()
    if not parts:
        return _help_text(ctx)

    action = parts[0].lower()
    name = parts[1] if len(parts) > 1 else _DEFAULT_SESSION
    sessions = _sessions(ctx)

    if action in {"help", "usage"}:
        return _help_text(ctx)
    if action == "config":
        return _config_text(ctx)
    runtime = getattr(ctx, "runtime", None)
    processes = getattr(runtime, "processes", None) or _context_processes(ctx)
    if action == "status":
        return _status_text(processes, sessions, "" if len(parts) == 1 else name)
    if action == "logs":
        lines = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 80
        return _logs_text(processes, name, lines)
    if action == "start":
        return _start_text(processes, sessions, name)
    if action == "stop":
        return _stop_text(processes, name)
    if action == "restart":
        stopped = _stop_text(processes, name)
        started = _start_text(processes, sessions, name, restart=True)
        return f"{stopped}\n\n{started}"
    if action == "write":
        text = str(args or "").split(maxsplit=2)[2] if len(parts) > 2 else ""
        return _write_text(processes, name, text)

    return f"Unknown process action: {action}\n\n{_help_text(ctx)}"


def process_badge(ctx):
    running = [info for info in _context_processes(ctx).status() if info.running]
    if running:
        return {
            "label": f"{len(running)} proc",
            "tooltip": "Open extension-managed process sessions",
            "tone": "success",
            "panel": "process_sessions",
        }
    return {
        "label": "Processes",
        "tooltip": "Open extension-managed process sessions",
        "tone": "",
        "panel": "process_sessions",
    }


def process_panel(ctx):
    processes = _context_processes(ctx)
    sessions = _sessions(ctx)
    statuses = {info.name: info for info in processes.status()}
    items = []
    for name, spec in sessions.items():
        info = statuses.get(name)
        running = bool(info and info.running)
        pid = str(info.pid) if info and info.pid else ""
        status = "running" if running else "stopped"
        actions = [
            {"label": "Refresh", "type": "refresh_panel"},
            {
                "label": "Logs",
                "type": "run_extension_command",
                "command": "process",
                "args": f"logs {name}",
            },
        ]
        if running:
            actions.append({
                "label": "Stop",
                "type": "run_extension_command",
                "command": "process",
                "args": f"stop {name}",
                "refresh": True,
            })
        else:
            actions.append({
                "label": "Start",
                "type": "run_extension_command",
                "command": "process",
                "args": f"start {name}",
                "refresh": True,
            })
        items.append({
            "title": name,
            "subtitle": f"{status}" + (f" pid {pid}" if pid else ""),
            "body": f"Command: {_command_display(spec)}",
            "actions": actions,
        })

    return {
        "title": "Processes",
        "body": (
            "Prototype process manager from .aichs/extensions/process_sessions.py. "
            "Use /process config to see the workspace process recipe format."
        ),
        "sections": [
            {
                "heading": "Sessions",
                "items": items or [{"title": "No configured sessions"}],
            },
            {
                "heading": "Commands",
                "items": [
                    {"title": "/process status"},
                    {"title": "/process start demo"},
                    {"title": "/process logs demo"},
                    {"title": "/process stop demo"},
                    {"title": "/process write demo text"},
                ],
            },
        ],
    }


def _help_text(ctx):
    return (
        "Usage:\n"
        "/process status [name]\n"
        "/process start <name>\n"
        "/process stop <name>\n"
        "/process restart <name>\n"
        "/process logs <name> [lines]\n"
        "/process write <name> <text>\n"
        "/process config\n\n"
        f"Configured sessions: {', '.join(_sessions(ctx))}"
    )


def _config_text(ctx):
    config = ctx.storage.load_config()
    if not config.get("sessions"):
        config = {"sessions": _default_sessions()}
        ctx.storage.save_config(config)
    return (
        "Config: .aichs/extensions/process_sessions.json\n\n"
        "Edit this file to add named workspace processes. A session can use a "
        "string command or an argv list. Set allow_stdin=true for interactive "
        "processes.\n\n"
        f"{json.dumps(config, indent=2)}"
    )


def _status_text(processes, sessions, name):
    statuses = {info.name: info for info in processes.status(name)}
    names = [name] if name else list(sessions)
    lines = []
    for item in names:
        if item not in sessions:
            lines.append(f"{item}: not configured")
            continue
        info = statuses.get(item)
        if info is None:
            lines.append(f"{item}: stopped")
            continue
        status = "running" if info.running else "stopped"
        detail = f" pid={info.pid}" if info.pid else ""
        if info.exit_code is not None:
            detail += f" exit={info.exit_code}"
        lines.append(f"{item}: {status}{detail}")
    return "\n".join(lines) if lines else "No configured sessions."


def _logs_text(processes, name, lines):
    if not name:
        return "[process error] name is required"
    try:
        text = processes.tail(name, lines)
    except ManagedProcessError as exc:
        return f"[process error] {exc}"
    return text or f"No logs yet for {name}."


def _start_text(processes, sessions, name, restart=False):
    if name not in sessions:
        return f"[process error] session not configured: {name}"
    spec = sessions[name]
    command = spec.get("command")
    if not command:
        return f"[process error] missing command for session: {name}"
    try:
        info = processes.start(
            name,
            command,
            allow_stdin=bool(spec.get("allow_stdin")),
            restart=restart,
        )
    except ManagedProcessError as exc:
        return f"[process error] {exc}"
    return f"Started {name} with pid {info.pid}."


def _stop_text(processes, name):
    try:
        info = processes.stop(name)
    except ManagedProcessError as exc:
        return f"[process error] {exc}"
    return f"Stopped {name}." if info.name else f"Stopped {name}."


def _write_text(processes, name, text):
    try:
        processes.write(name, text)
    except ManagedProcessError as exc:
        return f"[process error] {exc}"
    return f"Wrote {len(text)} chars to {name}."


def _sessions(ctx):
    config = ctx.storage.load_config()
    sessions = config.get("sessions")
    if not isinstance(sessions, dict) or not sessions:
        sessions = _default_sessions()
    clean = {}
    for name, spec in sessions.items():
        safe = _safe_name(name)
        if safe and isinstance(spec, dict):
            clean[safe] = dict(spec)
    return clean


def _default_sessions():
    return {
        _DEFAULT_SESSION: {
            "command": [
                sys.executable,
                "-u",
                "-c",
                (
                    "import time\n"
                    "i = 0\n"
                    "while True:\n"
                    "    print(f'demo tick {i}', flush=True)\n"
                    "    i += 1\n"
                    "    time.sleep(2)\n"
                ),
            ],
        }
    }


def _context_processes(ctx):
    return getattr(ctx, "processes", None) or RuntimeProcessApi(
        get_process_manager(),
        workspace=ctx.cwd,
        extension_id=getattr(ctx, "extension_id", "process_sessions"),
    )


def _tool_processes(ctx):
    return RuntimeProcessApi(
        get_process_manager(),
        workspace=ctx.cwd,
        extension_id=getattr(ctx, "extension_id", "process_sessions"),
    )


def _safe_name(value):
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(value or "")).strip("_-")


def _command_display(spec):
    command = spec.get("command")
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command or "")
