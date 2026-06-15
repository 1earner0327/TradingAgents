from __future__ import annotations

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import questionary


PALETTE = {
    "ink": "#e5e7eb",
    "muted": "#94a3b8",
    "faint": "#64748b",
    "panel": "#334155",
    "primary": "#38bdf8",
    "secondary": "#2dd4bf",
    "accent": "#fbbf24",
    "success": "#34d399",
    "warning": "#f59e0b",
    "danger": "#fb7185",
    "violet": "#a78bfa",
}


QUESTIONARY_STYLE = questionary.Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:yellow bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
        ("checkbox-selected", "fg:green"),
        ("separator", "fg:gray"),
        ("instruction", "fg:gray"),
        ("text", "fg:white"),
        ("disabled", "fg:gray"),
    ]
)


def make_panel(
    renderable,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    border_style: str | None = None,
    padding: tuple[int, int] = (1, 2),
    expand: bool = True,
):
    return Panel(
        renderable,
        title=title,
        subtitle=subtitle,
        border_style=border_style or PALETTE["panel"],
        box=box.ROUNDED,
        padding=padding,
        expand=expand,
    )


def brand_header(session: dict | None = None):
    session = session or {}
    ticker = session.get("ticker", "--")
    analysis_date = session.get("analysis_date", "--")
    provider = session.get("llm_provider", "--")

    grid = Table.grid(expand=True)
    grid.add_column(ratio=3)
    grid.add_column(ratio=2, justify="right")
    grid.add_row(
        Text.assemble(
            ("TradingAgents", f"bold {PALETTE['ink']}"),
            ("  Research Command Center", PALETTE["muted"]),
        ),
        Text.assemble(
            ("LIVE DESK", f"bold {PALETTE['secondary']}"),
            ("  "),
            (provider.upper(), PALETTE["accent"]),
        ),
    )
    grid.add_row(
        Text("Multi-agent market intelligence and risk review", style=PALETTE["faint"]),
        Text(f"{ticker}  |  {analysis_date}", style=PALETTE["muted"]),
    )
    return make_panel(grid, border_style=PALETTE["primary"], padding=(0, 2))


def welcome_panel(welcome_ascii: str):
    workflow = Text.assemble(
        ("Analysts", PALETTE["primary"]),
        ("  ->  ", PALETTE["faint"]),
        ("Research", PALETTE["violet"]),
        ("  ->  ", PALETTE["faint"]),
        ("Trader", PALETTE["accent"]),
        ("  ->  ", PALETTE["faint"]),
        ("Risk", PALETTE["danger"]),
        ("  ->  ", PALETTE["faint"]),
        ("Portfolio", PALETTE["success"]),
    )

    body = Group(
        Align.center(Text(welcome_ascii.rstrip(), style=f"bold {PALETTE['primary']}")),
        Align.center(Text("Institutional multi-agent market research terminal", style=PALETTE["ink"])),
        Align.center(Text("-" * 72, style=PALETTE["panel"])),
        Align.center(workflow),
        Align.center(Text("Tauric Research open-source framework", style=PALETTE["faint"])),
    )
    return Align.center(
        make_panel(
            body,
            title="TradingAgents",
            subtitle="Market intelligence console",
            border_style=PALETTE["primary"],
            padding=(1, 4),
            expand=False,
        )
    )


def step_panel(step: int, title: str, prompt: str, default: str | None = None):
    content = Text()
    content.append(f"STEP {step:02d}  ", style=f"bold {PALETTE['accent']}")
    content.append(f"{title}\n", style=f"bold {PALETTE['ink']}")
    content.append(prompt, style=PALETTE["muted"])
    if default:
        content.append(f"\nDefault: {default}", style=PALETTE["faint"])
    return make_panel(content, border_style=PALETTE["panel"], padding=(1, 2))


def env_notice(label: str, value: str | None):
    safe_value = value or "not set"
    text = Text.assemble(
        ("CONFIG ", f"bold {PALETTE['secondary']}"),
        (label, PALETTE["muted"]),
        (" = ", PALETTE["faint"]),
        (safe_value, PALETTE["ink"]),
    )
    return text


def status_renderable(status: str):
    normalized = (status or "pending").lower()
    labels = {
        "pending": ("QUEUED", PALETTE["faint"]),
        "in_progress": ("ANALYZING", PALETTE["primary"]),
        "completed": ("COMPLETE", PALETTE["success"]),
        "error": ("ERROR", PALETTE["danger"]),
    }
    label, color = labels.get(normalized, (normalized.upper(), PALETTE["ink"]))
    return Text(label, style=f"bold {color}")


def report_section_header(label: str, border_style: str):
    return make_panel(
        Align.center(Text(label, style=f"bold {PALETTE['ink']}")),
        border_style=border_style,
        padding=(0, 2),
    )
