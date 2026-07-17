"""
MultiAgent TUI — chat + side config/help panels that push the main column.

- Enter sends · Shift+Enter newline
- Mouse text selection in chat history
- Growing multi-line prompt (hidden scrollbar)
- Config / Help: sibling of chat (pushes text), drag left edge to resize
- Compact/config/help via Footer bindings (ctrl+k / ctrl+o / F1)
- Chat history: one selectable Static per message (drag-select + copy)
- Lightweight chrome updates (config data only on open / refresh)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    Markdown,
    RadioButton,
    RadioSet,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from cli_app.commands import chat_turn, dispatch
from cli_app.session import ConversationSession
from cli_app.tools import ToolCall
from core.clients import get_provider_meta, list_provider_names
from core.config_editor import (
    ensure_defaults_snapshot,
    get_cli_settings,
    known_providers,
    list_roles,
    reset_role_to_default,
    set_role,
)
from core.keys import get_key_status, set_api_key

# Config panel width bounds (cells)
_PIP_MIN_W = 34
_PIP_DEFAULT_W = 46
_CUSTOM_MODEL = "__custom__"

# Prompt area height (rows)
_PROMPT_MIN_H = 3
_PROMPT_MAX_H = 12

# Drag handle width (cells) on the left edge of overlays
_DRAG_EDGE = 2

# Cap chat message widgets to keep the DOM light
_LOG_MAX_LINES = 800

# Module-level caches (providers/models rarely change mid-session)
_provider_opts_cache: Optional[list[tuple[str, str]]] = None
_planner_opts_cache: Optional[list[tuple[str, str]]] = None
_known_providers_cache: Optional[list[tuple[str, str]]] = None
_models_cache: dict[str, list[str]] = {}


def _invalidate_option_caches() -> None:
    global _provider_opts_cache, _planner_opts_cache, _known_providers_cache
    _provider_opts_cache = None
    _planner_opts_cache = None
    _known_providers_cache = None
    _models_cache.clear()


def _provider_options() -> list[tuple[str, str]]:
    global _provider_opts_cache
    if _provider_opts_cache is None:
        try:
            _provider_opts_cache = [(n, n) for n in list_provider_names()]
        except Exception:
            _provider_opts_cache = []
    return _provider_opts_cache


def _known_provider_options() -> list[tuple[str, str]]:
    global _known_providers_cache
    if _known_providers_cache is None:
        try:
            _known_providers_cache = [(n, n) for n in known_providers()]
        except Exception:
            _known_providers_cache = _provider_options()
    return _known_providers_cache


def _planner_options() -> list[tuple[str, str]]:
    global _planner_opts_cache
    if _planner_opts_cache is None:
        opts: list[tuple[str, str]] = []
        try:
            for name in list_provider_names():
                meta = get_provider_meta(name)
                for m in meta.get("models") or []:
                    opts.append((f"{name}/{m}", f"{name}::{m}"))
        except Exception:
            pass
        _planner_opts_cache = opts or [
            ("groq/openai/gpt-oss-120b", "groq::openai/gpt-oss-120b")
        ]
    return _planner_opts_cache


def _models_for_provider(provider: str) -> list[str]:
    if provider not in _models_cache:
        try:
            meta = get_provider_meta(provider)
            _models_cache[provider] = list(meta.get("models") or [])
        except Exception:
            _models_cache[provider] = []
    return _models_cache[provider]


def _short_cwd(max_len: int = 40) -> str:
    try:
        cwd = Path.cwd()
        home = Path.home()
        try:
            s = "~/" + str(cwd.relative_to(home))
        except ValueError:
            s = str(cwd)
        if len(s) > max_len:
            s = "…" + s[-(max_len - 1) :]
        return s
    except Exception:
        return "."


def _planner_label(session: ConversationSession) -> str:
    try:
        from cli_app.commands import _resolve_planner

        p, m = _resolve_planner(session)
        short = m.split("/")[-1][:22]
        return f"{p}/{short}"
    except Exception:
        return "planner?"


def _role_badge(system: str, role: str) -> str:
    sys_tag = {
        "vibe_coding": "A",
        "deep_research": "B",
        "cli": "CLI",
    }.get(system, system[:3].upper())
    return f"[{sys_tag}] {role}"


def _session_info_text(session: ConversationSession) -> str:
    try:
        settings = get_cli_settings()
        skills_s = "none"
        try:
            from core.skills import active_skills

            active = active_skills()
            if active:
                skills_s = ", ".join(s.name for s in active)
        except Exception:
            pass
        g_on = "on" if settings.get("use_graphify") else "off"
        g_state = "cached" if session.graph_used else "not yet"
        return (
            f"{session.status_line()}\n"
            f"graphify={g_on} ({g_state})  "
            f"budget={settings.get('graphify_budget')}\n"
            f"skills={skills_s}"
        )
    except Exception:
        return session.status_line()


class StatusLine(Static):
    DEFAULT_CSS = """
    StatusLine {
        height: 1;
        width: 100%;
        padding: 0 1;
        background: $background;
        color: $text-muted;
        border-bottom: solid $foreground 10%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last = ""

    def update_status(
        self,
        *,
        cwd: str,
        planner: str,
        busy: bool,
        panel: str,
        always_approve: bool = False,
    ) -> None:
        busy_s = "working" if busy else "idle"
        parts = [cwd, planner, busy_s]
        if always_approve:
            parts.append("approve=always")
        if panel:
            parts.append(panel)
        text = "  ·  ".join(parts)
        if text == self._last:
            return
        self._last = text
        self.update(text)


class ApprovalBar(Vertical):
    """Compact vertical list: bold header + three bordered, centered option rows.

    Height 3 = 1 content row + top/bottom border so labels stay visible and
    rows are separated without looking glued together.
    """

    DEFAULT_CSS = """
    ApprovalBar {
        height: auto;
        width: 100%;
        layout: vertical;
        background: #3a3a3a;
        border-top: solid #555555;
        padding: 0 1 1 1;
        color: #d0d0d0;
    }
    ApprovalBar #approval-header {
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: #eeeeee;
        background: #3a3a3a;
        margin: 0 0 1 0;
        padding: 0;
    }
    ApprovalBar .approval-opt {
        height: 3;
        width: 100%;
        content-align: center middle;
        color: #e0e0e0;
        background: #454545;
        border: solid #6a6a6a;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    ApprovalBar .approval-opt:hover {
        background: #555555;
        color: #ffffff;
        border: solid #888888;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="approval-header")
        yield Static("accept", id="appr-yes", classes="approval-opt")
        yield Static("reject", id="appr-no", classes="approval-opt")
        yield Static("always", id="appr-always", classes="approval-opt")


class PromptArea(TextArea):
    """Multi-line prompt: Enter = send, Shift+Enter = newline."""

    BINDINGS = [
        Binding("enter", "submit_prompt", "send", show=False, priority=True),
        Binding("shift+enter", "insert_newline", "newline", show=False, priority=True),
        # Override TextArea's ctrl+k (delete line) so compact always works / shows
        Binding("ctrl+k", "app_compact", "compact", show=True, priority=True),
    ]

    def action_submit_prompt(self) -> None:
        app = self.app
        if hasattr(app, "submit_prompt"):
            app.submit_prompt(self.text)  # type: ignore[attr-defined]

    def action_insert_newline(self) -> None:
        self.insert("\n")

    def action_app_compact(self) -> None:
        app = self.app
        if hasattr(app, "action_compact"):
            app.action_compact()  # type: ignore[attr-defined]

    async def _on_key(self, event: events.Key) -> None:
        # Parent maps bare "enter" → "\n"; we use bindings for enter/shift+enter.
        if event.key in ("enter", "shift+enter"):
            return
        await super()._on_key(event)

    def action_cursor_up(self, select: bool = False) -> None:
        row, _col = self.cursor_location
        if row == 0 and not select:
            app = self.app
            if hasattr(app, "action_prompt_prev"):
                app.action_prompt_prev()  # type: ignore[attr-defined]
                return
        super().action_cursor_up(select=select)

    def action_cursor_down(self, select: bool = False) -> None:
        row, _col = self.cursor_location
        try:
            last = max(0, self.document.line_count - 1)
        except Exception:
            last = 0
        if row >= last and not select:
            app = self.app
            if hasattr(app, "action_prompt_next"):
                app.action_prompt_next()  # type: ignore[attr-defined]
                return
        super().action_cursor_down(select=select)


class ChatHistory(VerticalScroll):
    """Scrollable chat: Markdown for assistant, fenced code block for user prompts.

    No role labels (no -- you -- / -- assistant --). User text is shown as a
    markdown code fence so it is visually framed; assistant text is full markdown.
    """

    ALLOW_SELECT = True

    DEFAULT_CSS = """
    ChatHistory {
        height: 1fr;
        width: 100%;
        padding: 0 1;
        background: $background;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        color: $text;
    }
    ChatHistory .msg {
        height: auto;
        width: 100%;
        margin: 0 0 1 0;
        padding: 0;
        color: $text;
    }
    ChatHistory .msg-user {
        color: $text;
        background: $surface;
        padding: 0 1;
    }
    ChatHistory .msg-assistant {
        color: $text;
        padding: 0 0;
    }
    ChatHistory .msg-meta {
        color: $text-muted;
    }
    ChatHistory .msg-error {
        color: $error;
    }
    /* Normalize Markdown: body text primary, links accent (not random red/white). */
    ChatHistory Markdown {
        height: auto;
        margin: 0;
        padding: 0;
        background: transparent;
        color: $text;
    }
    ChatHistory .msg-assistant Markdown {
        color: $text;
    }
    ChatHistory .msg-meta Markdown {
        color: $text-muted;
    }
    ChatHistory .msg-error Markdown {
        color: $error;
    }
    ChatHistory MarkdownFence {
        margin: 1 0;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._msg_count = 0

    def _trim_old(self) -> None:
        self._msg_count += 1
        if self._msg_count <= _LOG_MAX_LINES:
            return
        try:
            children = list(self.children)
            for child in children[: max(1, len(children) // 10)]:
                child.remove()
        except Exception:
            pass

    def _mount_md(self, markdown: str, *, kind: str) -> None:
        self._trim_old()
        # Textual Markdown renders headings, lists, fences, bold, etc.
        self.mount(Markdown(markdown, classes=f"msg msg-{kind}"))
        self.scroll_end(animate=False)

    def write_meta(self, text: str) -> None:
        # Soft dim system notes — still as markdown so `code` works
        body = (text or "").strip()
        if not body:
            return
        self._mount_md(body, kind="meta")

    def write_user(self, text: str) -> None:
        """User prompt as a markdown fenced block (``` ... ```)."""
        body = (text or "").rstrip("\n")
        # Escape accidental fence-breaking by padding fences when body has ```
        fence = "```"
        if "```" in body:
            fence = "````"
        md = f"{fence}\n{body}\n{fence}\n"
        self._mount_md(md, kind="user")

    def write_assistant(self, text: str) -> None:
        """Assistant reply as rendered markdown (no role label)."""
        body = (text or "").replace("'''", "```")
        body = body.replace("‘", "'").replace("’", "'")
        body = body.replace("“", '"').replace("”", '"')
        body = body.strip()
        if not body:
            return
        self._mount_md(body, kind="assistant")

    def write_error(self, text: str) -> None:
        body = (text or "").strip()
        if not body:
            return
        # Long pipeline / partial failures must not paint the whole report red.
        if len(body) > 500:
            self._mount_md(body, kind="assistant")
            return
        self._mount_md(f"**error:** {body}", kind="error")


class SidePanel(Vertical):
    """Side panel sibling of chat — pushes main content (does not float over it)."""

    DEFAULT_CSS = """
    SidePanel {
        width: 46;
        height: 100%;
        border-left: tall $accent;
        background: $background;
        padding: 0 1 1 1;
        overflow-y: hidden;
        overflow-x: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    SidePanel #pip-title {
        height: 1;
        color: $text-muted;
        padding: 1 0 0 0;
    }
    SidePanel #pip-footer {
        height: 3;
        layout: horizontal;
        padding-top: 1;
    }
    SidePanel #help-body {
        height: 1fr;
        padding: 1 0;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    SidePanel Button {
        margin: 0 1 0 0;
        border: none;
        min-width: 8;
    }
    SidePanel .muted {
        color: $text-muted;
    }
    SidePanel .no-bar {
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    """

    def __init__(self, width: int = _PIP_DEFAULT_W, **kwargs) -> None:
        super().__init__(**kwargs)
        self._width = width
        self._dragging = False

    def on_mount(self) -> None:
        self.styles.width = self._width

    def set_width(self, width: int) -> None:
        width = max(_PIP_MIN_W, width)
        if width == self._width and self.styles.width and int(self.styles.width.value or 0) == width:
            return
        self._width = width
        self.styles.width = width

    def _max_width(self) -> int:
        try:
            return max(_PIP_MIN_W, self.app.size.width // 2)
        except Exception:
            return 60

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.x <= _DRAG_EDGE and event.button == 1:
            self._dragging = True
            self.capture_mouse()
            event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.release_mouse()
            event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        try:
            screen_w = self.app.size.width
            new_w = screen_w - int(event.screen_x)
            new_w = max(_PIP_MIN_W, min(self._max_width(), new_w))
            if new_w != self._width:
                self.set_width(new_w)
                app = self.app
                if hasattr(app, "_pip_width"):
                    app._pip_width = new_w  # type: ignore[attr-defined]
        except Exception:
            pass
        event.stop()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()

    def on_mouse_scroll_left(self, event: events.MouseScrollLeft) -> None:
        event.stop()

    def on_mouse_scroll_right(self, event: events.MouseScrollRight) -> None:
        event.stop()


class HelpPiP(SidePanel):
    """F1 help side panel (not dumped into chat history)."""

    def compose(self) -> ComposeResult:
        yield Label("help  ·  drag left edge to resize", id="pip-title")
        with VerticalScroll(id="help-body", classes="no-bar"):
            yield Static("", id="help-text")
        with Horizontal(id="pip-footer"):
            yield Button("close", id="help-close")

    def on_mount(self) -> None:
        super().on_mount()
        from cli_app.commands import _help

        # _help ignores session; avoid constructing a full ConversationSession
        result = _help([], None)  # type: ignore[arg-type]
        self.query_one("#help-text", Static).update(result.text)


class ConfigPiP(SidePanel):
    """Full-height side panel; each tab is one scroll (no nested height fight)."""

    DEFAULT_CSS = """
    ConfigPiP {
        width: 46;
        height: 100%;
        border-left: tall $accent;
        background: $background;
        padding: 0 1 1 1;
        overflow-y: hidden;
        overflow-x: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
        layout: vertical;
    }
    ConfigPiP #pip-title {
        height: 1;
        color: $text-muted;
        padding: 1 0 0 0;
    }
    ConfigPiP TabbedContent {
        height: 1fr;
        layout: vertical;
    }
    ConfigPiP ContentSwitcher {
        height: 1fr;
    }
    ConfigPiP TabPane {
        height: 1fr;
        padding: 0;
        layout: vertical;
    }
    /* Single scroll region per tab — form + status share one box */
    ConfigPiP .tab-body {
        height: 1fr;
        width: 100%;
        padding: 1 0;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    ConfigPiP Input {
        margin: 0 0 1 0;
        border: solid $foreground 20%;
        width: 100%;
        height: 3;
    }
    ConfigPiP Select {
        margin: 0 0 1 0;
        width: 100%;
        height: auto;
        max-height: 5;
    }
    ConfigPiP Button {
        margin: 0 1 1 0;
        border: none;
        min-width: 8;
        height: 3;
    }
    ConfigPiP #role-actions, ConfigPiP #key-actions {
        height: auto;
        margin: 0 0 1 0;
        layout: horizontal;
        width: 100%;
    }
    ConfigPiP #pip-footer {
        height: 3;
        layout: horizontal;
        padding-top: 1;
    }
    ConfigPiP .muted {
        color: $text-muted;
        height: auto;
        width: 100%;
    }
    ConfigPiP #roles-list, ConfigPiP #keys-status, ConfigPiP #session-info {
        color: $text;
        height: auto;
        width: 100%;
        margin-top: 1;
        padding-top: 1;
        border-top: solid $foreground 15%;
    }
    ConfigPiP RadioSet {
        height: auto;
        margin: 0 0 1 0;
        layout: horizontal;
        width: 100%;
    }
    """

    def __init__(
        self, session: ConversationSession, width: int = _PIP_DEFAULT_W, **kwargs
    ) -> None:
        super().__init__(width=width, **kwargs)
        self.session = session
        self._data_loaded = False

    def compose(self) -> ComposeResult:
        yield Label("config  ·  drag left edge to resize", id="pip-title")
        with TabbedContent(id="pip-tabs"):
            with TabPane("models", id="tab-models"):
                with VerticalScroll(classes="tab-body no-bar"):
                    yield Label("planner AI", classes="muted")
                    yield Select([], id="sel-planner", prompt="planner model")
                    yield Button("apply planner", id="btn-apply-planner")
                    yield Label("session (ctx / graph / skills)", classes="muted")
                    yield Static("", id="session-info")
            with TabPane("keys", id="tab-keys"):
                # ONE scroll: form + key status (same box as roles)
                with VerticalScroll(classes="tab-body no-bar"):
                    yield Label("provider", classes="muted")
                    yield Select([], id="sel-key-provider", prompt="provider")
                    yield Label("api key (not shown after save)", classes="muted")
                    yield Input(password=True, placeholder="paste key", id="inp-key")
                    with Horizontal(id="key-actions"):
                        yield Button("save key", id="btn-save-key")
                        yield Button("clear key", id="btn-clear-key")
                    yield Static("", id="keys-status")
            with TabPane("roles", id="tab-roles"):
                # ONE scroll for form + active roles (same box, same scroll)
                with VerticalScroll(classes="tab-body no-bar"):
                    yield Label("role", classes="muted")
                    yield Select([], id="sel-role", prompt="role")
                    yield Label("provider", classes="muted")
                    yield Select([], id="sel-role-provider", prompt="provider")
                    yield Label("model id", classes="muted")
                    yield Select([], id="sel-role-model", prompt="model")
                    yield Input(
                        placeholder="custom model name (if not in list)",
                        id="inp-role-model",
                    )
                    yield Label("apply as", classes="muted")
                    with RadioSet(id="role-target"):
                        yield RadioButton("principal", value=True, id="rb-principal")
                        yield RadioButton("fallback", id="rb-fallback")
                    with Horizontal(id="role-actions"):
                        yield Button("apply role", id="btn-apply-role")
                        yield Button("system default", id="btn-role-default")
                    yield Static("", id="roles-list")
        with Horizontal(id="pip-footer"):
            yield Button("refresh", id="pip-refresh")
            yield Button("close", id="pip-close")

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_data(full=True)

    def refresh_session_info_only(self) -> None:
        """Cheap path: update ctx line without rebuilding selects."""
        try:
            self.query_one("#session-info", Static).update(
                _session_info_text(self.session)
            )
        except Exception:
            pass

    def refresh_data(self, *, full: bool = True) -> None:
        if not full and self._data_loaded:
            self.refresh_session_info_only()
            return

        # Planner
        planner_opts = list(_planner_options())
        current = None
        try:
            from cli_app.commands import _resolve_planner

            p, m = _resolve_planner(self.session)
            current = f"{p}::{m}"
            if not any(v == current for _, v in planner_opts):
                planner_opts = [(f"{p}/{m}", current)] + planner_opts
        except Exception:
            pass

        sel_p = self.query_one("#sel-planner", Select)
        sel_p.set_options(planner_opts)
        if current:
            try:
                sel_p.value = current
            except Exception:
                pass

        # Keys
        self.query_one("#sel-key-provider", Select).set_options(_provider_options())
        lines = []
        for row in get_key_status():
            mark = "●" if row["status"] == "set" else "○"
            lines.append(
                f"{mark} {row['provider']:12} {row['status']:8} {row['preview']}"
            )
        self.query_one("#keys-status", Static).update("\n".join(lines) or "(none)")

        # Roles — compact single-column list inside the same scroll
        role_opts: list[tuple[str, str]] = []
        role_lines: list[str] = ["active roles"]
        current_sys = None
        for row in list_roles():
            rid = row.get("id") or ""
            if row.get("scalar"):
                role_lines.append(f"  · {rid} = {row.get('model')}")
                continue
            if row.get("missing"):
                continue
            system = str(row.get("system") or "")
            role = str(row.get("role") or "")
            label = _role_badge(system, role)
            role_opts.append((label, rid))
            if system != current_sys:
                current_sys = system
                title = {
                    "vibe_coding": "System A · Vibe Coding",
                    "deep_research": "System B · Deep Research",
                    "cli": "CLI",
                }.get(system, system)
                role_lines.append(f"▸ {title}")
            fb = f"  fb→{row['fallback']}" if row.get("fallback") else ""
            role_lines.append(
                f"  {label}  {row.get('provider')}/{row.get('model')}{fb}"
            )
        self.query_one("#sel-role", Select).set_options(role_opts)
        self.query_one("#sel-role-provider", Select).set_options(
            _known_provider_options()
        )
        self._refresh_role_model_options()
        self.query_one("#roles-list", Static).update("\n".join(role_lines))

        self.refresh_session_info_only()
        self._data_loaded = True

    def _refresh_role_model_options(self, provider: str | None = None) -> None:
        if provider is None:
            sel = self.query_one("#sel-role-provider", Select)
            if sel.value is Select.BLANK or not sel.value:
                models: list[str] = []
            else:
                models = _models_for_provider(str(sel.value))
        else:
            models = _models_for_provider(provider)
        opts: list[tuple[str, str]] = [("— type custom name —", _CUSTOM_MODEL)]
        for m in models:
            opts.append((m, m))
        self.query_one("#sel-role-model", Select).set_options(opts)

    def resolve_role_model(self) -> str:
        sel = self.query_one("#sel-role-model", Select)
        custom = self.query_one("#inp-role-model", Input).value.strip()
        val = sel.value
        if val is Select.BLANK or val == _CUSTOM_MODEL or not val:
            return custom
        if custom and custom != str(val):
            return custom
        return str(val)

    def role_as_fallback(self) -> bool:
        try:
            rs = self.query_one("#role-target", RadioSet)
            pressed = rs.pressed_button
            if pressed is not None and pressed.id == "rb-fallback":
                return True
        except Exception:
            pass
        return False


class MultiAgentApp(App[None]):
    """Chat shell with optional side panel that pushes the main column."""

    ALLOW_SELECT = True

    TITLE = "multiagent"
    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }
    #workspace {
        layout: horizontal;
        height: 1fr;
        width: 100%;
    }
    #main {
        layout: vertical;
        height: 100%;
        width: 1fr;
        min-width: 20;
    }
    #input-row {
        height: 3;
        max-height: 12;
        width: 100%;
        padding: 0 1 0 1;
        border-top: solid $foreground 10%;
    }
    #prompt {
        width: 1fr;
        height: 100%;
        background: $background;
        border: none;
        padding: 0;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    #prompt .text-area--cursor-line {
        background: $background;
    }
    #hint {
        height: 1;
        width: 100%;
        color: $text-muted;
        padding: 0 1;
        background: $background;
    }
    Footer {
        background: $background;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "quit", show=True),
        Binding("ctrl+d", "quit", "quit", show=False),
        Binding("ctrl+c", "copy_or_quit", "copy/quit", show=False),
        Binding("ctrl+k", "compact", "compact", show=True),
        Binding("ctrl+o", "toggle_config", "config", show=True),
        Binding("ctrl+p", "toggle_config", "config", show=False),
        Binding("escape", "close_overlays", "close", show=False),
        Binding("f1", "help", "help", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        ensure_defaults_snapshot()
        self.session = ConversationSession()
        self._awaiting_key_provider: str | None = None
        self._config_open = False
        self._help_open = False
        self._busy = False
        self._pip_width = _PIP_DEFAULT_W
        self._prompt_history: list[str] = []
        self._prompt_index: int = -1
        self._prompt_draft: str = ""
        self._prompt_height = _PROMPT_MIN_H
        self._resize_pending = False
        self._cwd_cache = _short_cwd()
        self._planner_cache = _planner_label(self.session)
        # Tool approval hand-off (worker thread ↔ UI thread)
        self._approval_event = threading.Event()
        self._approval_decision = "reject"
        self._approval_pending = False

    def compose(self) -> ComposeResult:
        yield StatusLine(id="status-line")
        with Horizontal(id="workspace"):
            with Vertical(id="main"):
                yield ChatHistory(id="chat-log")
                yield Label(
                    "enter send  ·  shift+enter newline  ·  drag-select + ctrl+c copy",
                    id="hint",
                )
                with Vertical(id="input-row"):
                    yield PromptArea(
                        id="prompt",
                        soft_wrap=True,
                        show_line_numbers=False,
                        tab_behavior="indent",
                        compact=True,
                        highlight_cursor_line=False,
                        placeholder="message or /do <task>…",
                    )
            # Side panel mounts here as sibling of #main (pushes chat left)
        # Footer only — compact/config/help as key bindings (no redundant bar)
        yield Footer()

    def on_mount(self) -> None:
        skills_hint = "skills: none"
        try:
            from core.skills import active_skills

            active = active_skills()
            if active:
                skills_hint = f"skills: {', '.join(s.name for s in active)}"
        except Exception:
            pass
        self._log_meta(
            f"multiagent — /do plans pipelines · {skills_hint}\n"
            "enter send · shift+enter newline · drag-select + ctrl+c · "
            "ctrl+k compact · F1 help · ctrl+o config"
        )
        self._refresh_chrome(full_config=False)
        self._apply_prompt_height(_PROMPT_MIN_H)
        self.query_one("#prompt", PromptArea).focus()

    def on_resize(self, event: events.Resize) -> None:
        """Keep PiP within half screen when the terminal is resized."""
        max_w = max(_PIP_MIN_W, event.size.width // 2)
        if self._pip_width > max_w:
            self._pip_width = max_w
        for cls in (ConfigPiP, HelpPiP):
            try:
                pip = self.query_one(cls)
                if pip._width > max_w:
                    pip.set_width(max_w)
            except Exception:
                pass

    # --- log (one selectable Static per message) ---

    def _log(self) -> ChatHistory:
        return self.query_one("#chat-log", ChatHistory)

    def _log_meta(self, text: str) -> None:
        self._log().write_meta(text)

    def _log_user(self, text: str) -> None:
        self._log().write_user(text)

    def _log_assistant(self, text: str) -> None:
        self._log().write_assistant(text)

    def _log_error(self, text: str) -> None:
        self._log().write_error(text)

    # --- chrome ---

    def _panel_label(self) -> str:
        if self._config_open:
            return "config"
        if self._help_open:
            return "help"
        return ""

    def _refresh_chrome(self, *, full_config: bool = False) -> None:
        """Update status line. Config selects only when full_config=True."""
        # Avoid re-reading YAML limits every keystroke/status tick unless needed
        if full_config:
            self.session.reload_limits()
            self._planner_cache = _planner_label(self.session)
            self._cwd_cache = _short_cwd()
        self.query_one(StatusLine).update_status(
            cwd=self._cwd_cache,
            planner=self._planner_cache,
            busy=self._busy,
            panel=self._panel_label(),
            always_approve=bool(self.session.always_approve),
        )
        if self._config_open:
            try:
                pip = self.query_one(ConfigPiP)
                if full_config:
                    pip.refresh_data(full=True)
                else:
                    pip.refresh_session_info_only()
            except Exception:
                pass

    def _set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        # Status only — do not rebuild config widgets while working
        self._refresh_chrome(full_config=False)

    # --- prompt grow / history ---

    def _apply_prompt_height(self, h: int) -> None:
        h = min(_PROMPT_MAX_H, max(_PROMPT_MIN_H, h))
        if h == self._prompt_height:
            return
        self._prompt_height = h
        try:
            self.query_one("#input-row").styles.height = h
        except Exception:
            pass

    def _resize_prompt(self) -> None:
        """Grow input-row with content; skip no-op height changes."""
        try:
            ta = self.query_one("#prompt", PromptArea)
            raw = ta.text or ""
            logical = max(1, raw.count("\n") + 1)
            try:
                width = max(20, ta.size.width or 40)
            except Exception:
                width = 40
            # Fast wrap estimate (avoid per-line overhead when short)
            if len(raw) <= width and "\n" not in raw:
                lines = 1
            else:
                wrapped = 0
                for line in raw.splitlines() or [""]:
                    wrapped += max(1, (len(line) // width) + 1)
                lines = max(logical, wrapped)
            self._apply_prompt_height(lines + 1)
        except Exception:
            pass

    @on(TextArea.Changed, "#prompt")
    def on_prompt_changed(self, _event: TextArea.Changed) -> None:
        # Coalesce rapid keystrokes into one height update per refresh cycle
        if self._resize_pending:
            return
        self._resize_pending = True

        def _do() -> None:
            self._resize_pending = False
            self._resize_prompt()

        self.call_after_refresh(_do)

    def action_prompt_prev(self) -> None:
        if not self._prompt_history:
            return
        ta = self.query_one("#prompt", PromptArea)
        if self._prompt_index < 0:
            self._prompt_draft = ta.text
            self._prompt_index = len(self._prompt_history) - 1
        elif self._prompt_index > 0:
            self._prompt_index -= 1
        ta.load_text(self._prompt_history[self._prompt_index])
        self._resize_prompt()

    def action_prompt_next(self) -> None:
        if self._prompt_index < 0:
            return
        ta = self.query_one("#prompt", PromptArea)
        if self._prompt_index < len(self._prompt_history) - 1:
            self._prompt_index += 1
            ta.load_text(self._prompt_history[self._prompt_index])
        else:
            self._prompt_index = -1
            ta.load_text(self._prompt_draft)
        self._resize_prompt()

    def _remember_prompt(self, line: str) -> None:
        if not line:
            return
        if self._prompt_history and self._prompt_history[-1] == line:
            self._prompt_index = -1
            self._prompt_draft = ""
            return
        self._prompt_history.append(line)
        if len(self._prompt_history) > 80:
            self._prompt_history = self._prompt_history[-80:]
        self._prompt_index = -1
        self._prompt_draft = ""

    def action_copy_or_quit(self) -> None:
        try:
            selected = self.screen.get_selected_text()
        except Exception:
            selected = None
        if selected:
            try:
                self.screen.action_copy_text()
                self.notify("copied", timeout=1.2)
            except Exception:
                self.copy_to_clipboard(selected)
                self.notify("copied", timeout=1.2)
            return
        self.exit()

    # --- overlays ---

    def action_close_overlays(self) -> None:
        self._close_config()
        self._close_help()
        try:
            self.query_one("#prompt", PromptArea).focus()
        except Exception:
            pass

    def _close_config(self) -> None:
        if not self._config_open:
            return
        try:
            pip = self.query_one(ConfigPiP)
            self._pip_width = pip._width
            pip.remove()
        except Exception:
            pass
        self._config_open = False

    def _close_help(self) -> None:
        if not self._help_open:
            return
        try:
            pip = self.query_one(HelpPiP)
            self._pip_width = pip._width
            pip.remove()
        except Exception:
            pass
        self._help_open = False

    def action_toggle_config(self) -> None:
        if self._config_open:
            self._close_config()
            self._refresh_chrome(full_config=False)
            self.query_one("#prompt", PromptArea).focus()
        else:
            self.action_open_config()

    def _side_slot(self) -> Horizontal:
        return self.query_one("#workspace", Horizontal)

    def action_open_config(self) -> None:
        self._close_help()
        if self._config_open:
            try:
                self.query_one(ConfigPiP).refresh_data(full=True)
            except Exception:
                pass
            self._refresh_chrome(full_config=False)
            return
        max_w = max(_PIP_MIN_W, self.size.width // 2)
        w = min(self._pip_width, max_w)
        # Mount as workspace sibling so #main width shrinks (pushes chat)
        self._side_slot().mount(ConfigPiP(self.session, width=w, id="config-pip"))
        self._config_open = True
        self._refresh_chrome(full_config=False)
        self.query_one("#prompt", PromptArea).focus()

    def action_help(self) -> None:
        self._close_config()
        if self._help_open:
            self._close_help()
            self._refresh_chrome(full_config=False)
            self.query_one("#prompt", PromptArea).focus()
            return
        max_w = max(_PIP_MIN_W, self.size.width // 2)
        w = min(self._pip_width, max_w)
        self._side_slot().mount(HelpPiP(width=w, id="help-pip"))
        self._help_open = True
        self._refresh_chrome(full_config=False)

    def action_compact(self) -> None:
        result = dispatch("/compact", self.session)
        self._log_meta(result.text)
        self._refresh_chrome(full_config=False)

    @on(Button.Pressed, "#pip-close")
    def on_pip_close(self) -> None:
        self._close_config()
        self._refresh_chrome(full_config=False)
        self.query_one("#prompt", PromptArea).focus()

    @on(Button.Pressed, "#help-close")
    def on_help_close(self) -> None:
        self._close_help()
        self._refresh_chrome(full_config=False)
        self.query_one("#prompt", PromptArea).focus()

    @on(Button.Pressed, "#pip-refresh")
    def on_pip_refresh(self) -> None:
        _invalidate_option_caches()
        self._refresh_chrome(full_config=True)

    @on(Button.Pressed, "#btn-apply-planner")
    def on_apply_planner(self) -> None:
        sel = self.query_one("#sel-planner", Select)
        val = sel.value
        if val is Select.BLANK or not val:
            self._log_meta("pick a planner model first")
            return
        prov, model = str(val).split("::", 1)
        result = dispatch(f"/planner set {prov} {model}", self.session)
        self._log_meta(result.text)
        self._planner_cache = _planner_label(self.session)
        self._refresh_chrome(full_config=True)

    @on(Button.Pressed, "#btn-save-key")
    def on_save_key(self) -> None:
        prov = self.query_one("#sel-key-provider", Select).value
        key = self.query_one("#inp-key", Input).value.strip()
        if prov is Select.BLANK or not prov:
            self._log_meta("pick a provider")
            return
        if not key:
            self._log_meta("paste an api key first")
            return
        try:
            preview = set_api_key(str(prov), key)
            self.query_one("#inp-key", Input).value = ""
            self._log_meta(f"saved {prov} key ({preview})")
        except Exception as exc:
            self._log_error(str(exc))
        self._refresh_chrome(full_config=True)

    @on(Button.Pressed, "#btn-clear-key")
    def on_clear_key(self) -> None:
        from core.keys import provider_env_map, _upsert_env_var, env_path
        import os as _os

        prov = self.query_one("#sel-key-provider", Select).value
        if prov is Select.BLANK or not prov:
            self._log_meta("pick a provider to clear")
            return
        env_map = provider_env_map()
        env_name = env_map.get(str(prov))
        if not env_name:
            return
        _upsert_env_var(env_path(), env_name, f"your_{prov}_api_key_here")
        _os.environ.pop(env_name, None)
        try:
            from core.clients import clear_client_cache

            clear_client_cache()
        except Exception:
            pass
        self._log_meta(f"cleared {prov} key")
        self._refresh_chrome(full_config=True)

    @on(Button.Pressed, "#btn-apply-role")
    def on_apply_role(self) -> None:
        pip = self.query_one(ConfigPiP)
        role_id = self.query_one("#sel-role", Select).value
        prov = self.query_one("#sel-role-provider", Select).value
        model = pip.resolve_role_model()
        if role_id is Select.BLANK or not role_id:
            self._log_meta("pick a role")
            return
        if prov is Select.BLANK or not prov or not model:
            self._log_meta("pick provider and model id")
            return
        system, role = str(role_id).split(".", 1)
        try:
            if pip.role_as_fallback():
                node = set_role(
                    system,
                    role,
                    fallback_provider=str(prov),
                    fallback_model=model,
                )
                fb = node.get("fallback") or {}
                self._log_meta(
                    f"{role_id} fallback → {fb.get('provider')}/{fb.get('model')}"
                )
            else:
                node = set_role(system, role, provider=str(prov), model=model)
                self._log_meta(f"{role_id} → {node['provider']}/{node['model']}")
        except Exception as exc:
            self._log_error(str(exc))
        self._refresh_chrome(full_config=True)

    @on(Button.Pressed, "#btn-role-default")
    def on_role_default(self) -> None:
        role_id = self.query_one("#sel-role", Select).value
        if role_id is Select.BLANK or not role_id:
            self._log_meta("pick a role to restore default")
            return
        system, role = str(role_id).split(".", 1)
        try:
            node = reset_role_to_default(system, role)
            if "max_fix_cycles" in node:
                self._log_meta(
                    f"{role_id} → default max_fix_cycles={node['max_fix_cycles']}"
                )
            else:
                self._log_meta(
                    f"{role_id} → default {node.get('provider')}/{node.get('model')}"
                )
        except Exception as exc:
            self._log_error(str(exc))
        self._refresh_chrome(full_config=True)

    @on(Select.Changed, "#sel-role")
    def on_role_selected(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        rid = str(event.value)
        for row in list_roles():
            if row.get("id") == rid and not row.get("scalar"):
                prov = row.get("provider")
                try:
                    if prov:
                        self.query_one("#sel-role-provider", Select).value = prov
                except Exception:
                    pass
                try:
                    self.query_one(ConfigPiP)._refresh_role_model_options(
                        str(prov) if prov else None
                    )
                except Exception:
                    pass
                model = str(row.get("model") or "")
                self.query_one("#inp-role-model", Input).value = model
                sel_m = self.query_one("#sel-role-model", Select)
                try:
                    if model:
                        sel_m.value = model
                    else:
                        sel_m.value = _CUSTOM_MODEL
                except Exception:
                    try:
                        sel_m.value = _CUSTOM_MODEL
                    except Exception:
                        pass
                break

    @on(Select.Changed, "#sel-role-provider")
    def on_role_provider_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        try:
            self.query_one(ConfigPiP)._refresh_role_model_options(str(event.value))
        except Exception:
            pass
        try:
            self.query_one("#inp-role-model", Input).value = ""
        except Exception:
            pass

    @on(Select.Changed, "#sel-role-model")
    def on_role_model_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or event.value == _CUSTOM_MODEL:
            return
        try:
            self.query_one("#inp-role-model", Input).value = str(event.value)
        except Exception:
            pass

    # --- tool approval ---

    def _request_tool_approval(self, call: ToolCall) -> str:
        """Block worker thread until the user decides (UI thread)."""
        if self.session.always_approve:
            return "approve"
        self._approval_event.clear()
        self._approval_decision = "reject"
        self._approval_pending = True
        self.call_from_thread(self._show_approval, call)
        # Wait up to 10 minutes for a click / key decision
        ok = self._approval_event.wait(timeout=600)
        self._approval_pending = False
        if not ok:
            self.call_from_thread(self._hide_approval)
            return "reject"
        return self._approval_decision

    def _show_approval(self, call: ToolCall) -> None:
        from cli_app.tools import format_command_header

        header = format_command_header(call)
        if len(header) > 200:
            header = header[:200] + "…"
        try:
            existing = self.query(ApprovalBar)
            if existing:
                existing.first().remove()
        except Exception:
            pass
        bar = ApprovalBar(id="approval-bar")
        self.mount(bar)
        try:
            # Bold via CSS text-style; plain text so the full command is visible
            bar.query_one("#approval-header", Static).update(header)
        except Exception:
            pass
        self._log_meta(f"approval: {header}")

    def _hide_approval(self) -> None:
        try:
            self.query_one(ApprovalBar).remove()
        except Exception:
            pass

    def _resolve_approval(self, decision: str) -> None:
        if not self._approval_pending:
            return
        self._approval_decision = decision
        if decision in ("always", "!"):
            self.session.always_approve = True
        self._hide_approval()
        self._approval_event.set()
        self._refresh_chrome(full_config=False)

    @on(events.Click, "#appr-yes")
    def on_appr_yes(self, event: events.Click) -> None:
        event.stop()
        self._resolve_approval("approve")

    @on(events.Click, "#appr-no")
    def on_appr_no(self, event: events.Click) -> None:
        event.stop()
        self._resolve_approval("reject")

    @on(events.Click, "#appr-always")
    def on_appr_always(self, event: events.Click) -> None:
        event.stop()
        self._resolve_approval("always")

    def _chat_progress(self, msg: str) -> None:
        """Progress line from the agent loop (called via call_from_thread)."""
        self._log_meta(msg)

    # --- submit ---

    def submit_prompt(self, text: str) -> None:
        """Called from PromptArea (Enter)."""
        line = (text or "").strip()
        ta = self.query_one("#prompt", PromptArea)
        ta.load_text("")
        self._apply_prompt_height(_PROMPT_MIN_H)
        if not line:
            return

        # Shortcut keys while a tool approval is pending (one command at a time)
        if self._approval_pending:
            key = line.strip().lower()
            mapping = {
                "a": "approve",
                "y": "approve",
                "yes": "approve",
                "accept": "approve",
                "r": "reject",
                "n": "reject",
                "no": "reject",
                "reject": "reject",
                "!": "always",
                "always": "always",
            }
            if key in mapping:
                self._resolve_approval(mapping[key])
                return

        if self._awaiting_key_provider:
            provider = self._awaiting_key_provider
            self._awaiting_key_provider = None
            result = dispatch(f"/keys set {provider} {line}", self.session)
            self._log_meta(result.text)
            self._refresh_chrome(full_config=False)
            return

        self._remember_prompt(line)
        if line.startswith("/"):
            low = line.strip().split()[0].lower()
            if low in ("/help", "/h"):
                self.action_help()
                return
            if low in ("/config",) and line.strip().lower() in (
                "/config",
                "/config show",
                "/config pip",
                "/config panel",
            ):
                self.action_open_config()
                return
            self._log_user(line)
            self._run_command(line)
        else:
            self._log_user(line)
            self._run_chat(line)

    @work(thread=True, exclusive=True, group="pipeline")
    def _run_command(self, line: str) -> None:
        self.call_from_thread(self._set_busy, True)

        def progress(msg: str) -> None:
            self.call_from_thread(self._chat_progress, msg)

        self.session.progress_cb = progress
        try:
            result = dispatch(line, self.session)
        finally:
            self.session.progress_cb = None
            self.call_from_thread(self._set_busy, False)
        self.call_from_thread(self._handle_result, result)

    @work(thread=True, exclusive=True, group="pipeline")
    def _run_chat(self, text: str) -> None:
        self.call_from_thread(self._set_busy, True)

        def approve(call: ToolCall) -> str:
            return self._request_tool_approval(call)

        def progress(msg: str) -> None:
            self.call_from_thread(self._chat_progress, msg)

        try:
            result = chat_turn(
                text,
                self.session,
                approve=approve,
                progress=progress,
            )
        finally:
            self.call_from_thread(self._set_busy, False)
            self.call_from_thread(self._hide_approval)
        self.call_from_thread(self._handle_result, result)

    def _handle_result(self, result) -> None:
        if result.data and result.data.get("exit"):
            self.exit()
            return
        if result.data and result.data.get("prompt_key"):
            self._awaiting_key_provider = result.data["prompt_key"]
            self._log_meta(
                f"paste api key for {self._awaiting_key_provider} then enter"
            )
            self._refresh_chrome(full_config=False)
            return
        if result.data and result.data.get("help_panel") and not self._help_open:
            self.action_help()
            return
        text = result.text or ""
        data = result.data or {}
        # Structured pipeline/tool replies always use normal assistant colors,
        # even when a step failed (partial success). Only bare short errors go red.
        is_structured = any(
            data.get(k) is not None
            for k in (
                "used_graph",
                "files_written",
                "has_report",
                "passed",
                "plan",
                "steps",
                "tools",
                "graph_updated",
            )
        )
        if result.ok and data.get("open_pip") and not self._config_open:
            self.action_open_config()
        if is_structured:
            self._log_assistant(text)
        elif result.ok:
            self._log_meta(text)
        else:
            self._log_error(text or "error")
        # After a turn: cheap session-info update only
        self.session.reload_limits()
        self._refresh_chrome(full_config=False)


def _quiet_logging_for_tui() -> None:
    """Stop router/HTTP retry noise from painting over the prompt bar.

    ``cli.py`` configures root logging at WARNING with a StreamHandler; during
    the TUI that ends up as sticky lines above the input (e.g. HTTP 429 retries
    from ``core.router``). Keep errors for real failures; silence retry chatter.
    """
    import logging

    # Drop existing stream handlers that write to the terminal
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    # ERROR+ only on root; never spam the TUI with WARNING retries
    logging.basicConfig(level=logging.ERROR, force=True)

    for name in (
        "core.router",
        "core.clients",
        "core.quotas",
        "httpx",
        "httpcore",
        "openai",
        "cohere",
        "urllib3",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)
        logging.getLogger(name).propagate = True


def run_app() -> None:
    _quiet_logging_for_tui()
    ensure_defaults_snapshot()
    get_cli_settings()
    MultiAgentApp().run()


if __name__ == "__main__":
    run_app()
