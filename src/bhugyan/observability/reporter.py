"""Step-by-step pipeline visibility.

Every pipeline run is reported as a sequence of named STEPS. For each step we
show, live in the console: input count -> output count, how many items were
skipped and *why* (a reason histogram), free-form notes, and the wall time.
The whole run is also persisted as a JSON file in run_logs/ for auditing.

This is the "make it visible how the pipeline works at each step" layer that
every pipeline (P1-P5) and the common loader funnel their progress through.

Rich is used for pretty output when installed; otherwise it degrades to plain
print() so the reporter never becomes a hard dependency.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

try:  # pretty output if available
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _console = Console()
    _HAS_RICH = True
except Exception:  # pragma: no cover - fallback path
    _console = None
    _HAS_RICH = False


def _emit(msg: str = "") -> None:
    if _HAS_RICH:
        _console.print(msg)
    else:
        # strip the most common rich markup for the plain fallback
        for tag in ("[bold]", "[/bold]", "[dim]", "[/dim]", "[green]", "[/green]",
                    "[yellow]", "[/yellow]", "[red]", "[/red]", "[cyan]", "[/cyan]"):
            msg = msg.replace(tag, "")
        print(msg)


@dataclass
class StepReport:
    """Live tally for a single pipeline step."""

    name: str
    total_in: int = 0
    passed: int = 0
    skipped: int = 0
    skip_reasons: Counter = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    # ---- methods the step body calls as it processes items ----
    def ok(self, n: int = 1) -> None:
        self.passed += n

    def skip(self, reason: str, n: int = 1) -> None:
        self.skipped += n
        self.skip_reasons[reason] += n

    def note(self, message: str) -> None:
        self.notes.append(message)

    def set_in(self, n: int) -> None:
        self.total_in = n

    @property
    def total_out(self) -> int:
        # If the body tracked passes explicitly, trust that; else infer.
        if self.passed or self.skipped:
            return self.passed
        return self.total_in

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "in": self.total_in,
            "out": self.total_out,
            "skipped": self.skipped,
            "skip_reasons": dict(self.skip_reasons),
            "notes": self.notes,
            "duration_s": round(self.duration_s, 4),
        }


class PipelineRun:
    """Coordinates and renders the steps of one pipeline execution."""

    def __init__(self, pipeline: str, meta: dict | None = None,
                 log_dir: Path | None = None):
        self.pipeline = pipeline
        self.meta = meta or {}
        self.steps: list[StepReport] = []
        self.log_dir = log_dir
        self._t0 = time.perf_counter()
        self._print_header()

    def _print_header(self) -> None:
        lines = [f"[dim]{k}:[/dim] {v}" for k, v in self.meta.items()]
        body = "\n".join(lines) if lines else "[dim]starting…[/dim]"
        if _HAS_RICH:
            _console.print(Panel(body, title=f"[bold cyan]Pipeline {self.pipeline}[/bold cyan]",
                                 expand=False))
        else:
            _emit(f"\n=== Pipeline {self.pipeline} ===")
            for line in lines:
                _emit("  " + line)

    @contextmanager
    def step(self, name: str, total_in: int | None = None) -> Iterator[StepReport]:
        rep = StepReport(name=name)
        if total_in is not None:
            rep.total_in = total_in
        _emit(f"[bold]▶ {name}[/bold]" +
              (f"  [dim]({total_in} in)[/dim]" if total_in is not None else ""))
        t0 = time.perf_counter()
        try:
            yield rep
        finally:
            rep.duration_s = time.perf_counter() - t0
            self.steps.append(rep)
            self._print_step_summary(rep)

    def _print_step_summary(self, rep: StepReport) -> None:
        tail = f"[dim]{rep.duration_s:.2f}s[/dim]"
        line = (f"   [green]{rep.total_out} ok[/green]"
                + (f", [yellow]{rep.skipped} skipped[/yellow]" if rep.skipped else "")
                + f"   {tail}")
        _emit(line)
        for reason, count in rep.skip_reasons.most_common():
            _emit(f"     [yellow]·[/yellow] [dim]skipped:[/dim] {reason} ×{count}")
        for note in rep.notes:
            _emit(f"     [cyan]·[/cyan] {note}")

    # ---- finalize ----
    def finish(self, extra: dict | None = None) -> dict:
        total = time.perf_counter() - self._t0
        summary = {
            "pipeline": self.pipeline,
            "meta": self.meta,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_s": round(total, 4),
            **(extra or {}),
        }
        self._print_final_table(total, extra or {})
        if self.log_dir is not None:
            self._write_log(summary)
        return summary

    def _print_final_table(self, total: float, extra: dict) -> None:
        if _HAS_RICH:
            table = Table(title=f"Run summary — {self.pipeline}", expand=False)
            table.add_column("Step")
            table.add_column("In", justify="right")
            table.add_column("Out", justify="right")
            table.add_column("Skipped", justify="right")
            table.add_column("Time", justify="right")
            for s in self.steps:
                table.add_row(s.name, str(s.total_in), str(s.total_out),
                              str(s.skipped) if s.skipped else "-",
                              f"{s.duration_s:.2f}s")
            _console.print(table)
        else:
            _emit("--- Run summary ---")
            for s in self.steps:
                _emit(f"  {s.name}: {s.total_in} -> {s.total_out} "
                      f"(skipped {s.skipped}) {s.duration_s:.2f}s")
        for k, v in extra.items():
            _emit(f"[dim]{k}:[/dim] {v}")
        _emit(f"[bold green]✓ {self.pipeline} done in {total:.2f}s[/bold green]\n")

    def _write_log(self, summary: dict) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # deterministic-ish name (no Date.now here; based on step count + pipeline)
        safe = self.pipeline.replace(":", "").replace(" ", "_").lower()
        path = self.log_dir / f"{safe}_run.json"
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        _emit(f"[dim]run log → {path}[/dim]")
