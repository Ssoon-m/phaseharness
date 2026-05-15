#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


STAGES = ["clarify", "context_gather", "plan", "generate", "evaluate"]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def elapsed_seconds(start: Any, end: Any) -> float | None:
    started_at = parse_iso(start)
    ended_at = parse_iso(end)
    if started_at is None or ended_at is None:
        return None
    return max(0.0, round((ended_at - started_at).total_seconds(), 3))


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness").is_dir() or (current / ".git").exists():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    events.append(item)
    except OSError:
        pass
    return events


def runs_dir(root: Path) -> Path:
    return root / ".phaseharness" / "runs"


def run_dir(root: Path, run_id: str) -> Path:
    return runs_dir(root) / run_id


def run_json_path(root: Path, run_id: str) -> Path:
    return run_dir(root, run_id) / "run.json"


def events_path(root: Path, run_id: str) -> Path:
    return run_dir(root, run_id) / "events.jsonl"


def safe_run_id(value: str) -> str:
    run_id = unquote(value).strip()
    path = Path(run_id)
    if not run_id or path.is_absolute() or "/" in run_id or "\\" in run_id or ".." in path.parts:
        raise ValueError("invalid run id")
    return run_id


def discovered_phase_ids(root: Path, run_id: str) -> list[str]:
    phase_dir = run_dir(root, run_id) / "phases"
    if not phase_dir.exists():
        return []
    return [path.stem for path in sorted(phase_dir.glob("phase-*.md")) if path.is_file()]


def status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def sorted_runs(index: dict[str, Any]) -> list[dict[str, Any]]:
    runs = index.get("runs")
    if not isinstance(runs, list):
        return []
    records = [item for item in runs if isinstance(item, dict) and item.get("run_id")]
    return sorted(records, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)


def stage_rows(run: dict[str, Any], *, now: str) -> list[dict[str, Any]]:
    stages = run.get("stages")
    if not isinstance(stages, dict):
        stages = {}
    workflow = run.get("workflow")
    stage_names = [str(item) for item in workflow] if isinstance(workflow, list) else STAGES
    rows: list[dict[str, Any]] = []
    for stage in stage_names:
        raw = stages.get(stage)
        item = raw if isinstance(raw, dict) else {}
        status = str(item.get("status") or "pending")
        end_time = item.get("completed_at") or item.get("failed_at") or (now if status == "running" else None)
        duration = item.get("duration_seconds")
        if duration is None:
            duration = elapsed_seconds(item.get("started_at"), end_time)
        rows.append(
            {
                "stage": stage,
                "status": status,
                "attempts": item.get("attempts", 0),
                "started_at": item.get("started_at"),
                "completed_at": item.get("completed_at"),
                "failed_at": item.get("failed_at"),
                "duration_seconds": duration,
                "artifact": item.get("artifact"),
                "message": item.get("message"),
            }
        )
    return rows


def phase_rows(root: Path, run: dict[str, Any], *, now: str) -> list[dict[str, Any]]:
    run_id = str(run.get("run_id") or "")
    generate = run.get("generate")
    if not isinstance(generate, dict):
        generate = {}
    statuses = generate.get("phase_status") if isinstance(generate.get("phase_status"), dict) else {}
    attempts = generate.get("phase_attempts") if isinstance(generate.get("phase_attempts"), dict) else {}
    timing = generate.get("phase_timing") if isinstance(generate.get("phase_timing"), dict) else {}
    queue = generate.get("queue") if isinstance(generate.get("queue"), list) else []
    phase_ids = sorted({str(item) for item in queue} | set(statuses.keys()) | set(discovered_phase_ids(root, run_id)))
    rows: list[dict[str, Any]] = []
    for phase_id in phase_ids:
        phase_timing = timing.get(phase_id) if isinstance(timing.get(phase_id), dict) else {}
        status = str(statuses.get(phase_id) or phase_timing.get("status") or "pending")
        end_time = phase_timing.get("completed_at") or phase_timing.get("failed_at") or (now if status == "running" else None)
        duration = phase_timing.get("duration_seconds")
        if duration is None:
            duration = elapsed_seconds(phase_timing.get("started_at"), end_time)
        rows.append(
            {
                "phase_id": phase_id,
                "status": status,
                "attempts": attempts.get(phase_id, 0),
                "started_at": phase_timing.get("started_at"),
                "completed_at": phase_timing.get("completed_at"),
                "failed_at": phase_timing.get("failed_at"),
                "duration_seconds": duration,
                "file": f".phaseharness/runs/{run_id}/phases/{phase_id}.md",
            }
        )
    return rows


def commit_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    commits = run.get("commits")
    if not isinstance(commits, dict):
        return []
    rows = []
    for key, raw in sorted(commits.items()):
        item = raw if isinstance(raw, dict) else {}
        rows.append(
            {
                "key": key,
                "status": item.get("status"),
                "mode": item.get("mode"),
                "implementation_phase": item.get("implementation_phase"),
                "updated_at": item.get("updated_at"),
                "completed_at": item.get("completed_at"),
                "message": item.get("message"),
                "eligible_paths": item.get("paths", {}).get("eligible_paths", []) if isinstance(item.get("paths"), dict) else [],
            }
        )
    return rows


def summarize_run(root: Path, run_id: str) -> dict[str, Any] | None:
    run = load_json(run_json_path(root, run_id), None)
    if not isinstance(run, dict):
        return None
    now = now_iso()
    events = read_events(events_path(root, run_id))
    metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
    loop = run.get("loop") if isinstance(run.get("loop"), dict) else {}
    generate = run.get("generate") if isinstance(run.get("generate"), dict) else {}
    evaluation = run.get("evaluation") if isinstance(run.get("evaluation"), dict) else {}
    current_status = run.get("status")
    run_end = run.get("completed_at") or run.get("failed_at") or (now if current_status in ("active", "waiting_user") else None)
    run_duration = metrics.get("run_duration_seconds")
    if run_duration is None:
        run_duration = elapsed_seconds(run.get("created_at"), run_end)
    stages = stage_rows(run, now=now)
    phases = phase_rows(root, run, now=now)
    loop_started_events = [event for event in events if event.get("type") == "loop_started"]
    post_evaluate_fixes = bool(metrics.get("post_evaluate_fixes") or loop_started_events or int(loop.get("current", 1) or 1) > 1)
    return {
        "run_id": run_id,
        "request": run.get("request"),
        "mode": run.get("mode"),
        "status": current_status,
        "current_stage": run.get("current_stage"),
        "current_phase": generate.get("current_phase"),
        "loop": {"current": loop.get("current", 1), "max": loop.get("max", 1)},
        "commit_mode": run.get("commit_mode"),
        "evaluation_status": evaluation.get("status"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "completed_at": run.get("completed_at"),
        "failed_at": run.get("failed_at"),
        "duration_seconds": run_duration,
        "worktree": run.get("worktree"),
        "blocked_by": run.get("blocked_by"),
        "inflight": run.get("inflight"),
        "stages": stages,
        "phases": phases,
        "commits": commit_rows(run),
        "metrics": {
            **metrics,
            "post_evaluate_fixes": post_evaluate_fixes,
            "loop_retry_count": max(0, int(loop.get("current", 1) or 1) - 1),
            "stage_status_counts": status_counts(stages),
            "phase_status_counts": status_counts(phases),
            "followup_phase_count": metrics.get("followup_phase_count", len(loop_started_events)),
        },
        "events": events[-200:],
    }


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [run for run in runs if run.get("status") == "completed"]
    errored = [run for run in runs if run.get("status") == "error"]
    active = [run for run in runs if run.get("status") in ("active", "waiting_user")]
    durations = [float(run["duration_seconds"]) for run in runs if isinstance(run.get("duration_seconds"), (int, float))]
    completed_durations = [float(run["duration_seconds"]) for run in completed if isinstance(run.get("duration_seconds"), (int, float))]
    retries = [int(run.get("metrics", {}).get("loop_retry_count", 0) or 0) for run in runs]
    post_fix_runs = [run for run in runs if run.get("metrics", {}).get("post_evaluate_fixes")]
    return {
        "total_runs": len(runs),
        "active_runs": len(active),
        "completed_runs": len(completed),
        "error_runs": len(errored),
        "completion_rate": round(len(completed) / len(runs), 3) if runs else None,
        "post_evaluate_fix_runs": len(post_fix_runs),
        "post_evaluate_fix_rate": round(len(post_fix_runs) / len(runs), 3) if runs else None,
        "average_run_duration_seconds": average(durations),
        "average_completed_duration_seconds": average(completed_durations),
        "average_loop_retries": average([float(item) for item in retries]),
    }


def dashboard_data(root: Path, *, run_limit: int = 50) -> dict[str, Any]:
    active = load_json(root / ".phaseharness" / "state" / "active.json", {})
    index = load_json(root / ".phaseharness" / "state" / "index.json", {"runs": []})
    summaries: list[dict[str, Any]] = []
    for record in sorted_runs(index)[:run_limit]:
        summary = summarize_run(root, str(record.get("run_id")))
        if summary is not None:
            summaries.append(summary)
    active_run_id = active.get("active_run") if isinstance(active, dict) else None
    active_run = summarize_run(root, str(active_run_id)) if active_run_id else None
    if active_run is not None and all(item.get("run_id") != active_run.get("run_id") for item in summaries):
        summaries.insert(0, active_run)
    return {
        "generated_at": now_iso(),
        "root": str(root),
        "active": active,
        "active_run": active_run,
        "runs": summaries,
        "aggregate": aggregate_runs(summaries),
    }


def html_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phaseharness Metrics</title>
<style>
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --panel: #ffffff;
  --text: #171a1f;
  --muted: #667085;
  --line: #d8dee8;
  --blue: #2563eb;
  --green: #16803c;
  --amber: #9a6700;
  --red: #c92a2a;
  --gray: #475467;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  position: sticky;
  top: 0;
  z-index: 2;
  border-bottom: 1px solid var(--line);
  background: rgba(247, 248, 250, 0.94);
  backdrop-filter: blur(8px);
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 18px; }
.headrow { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h1 { margin: 0; font-size: 20px; line-height: 1.2; font-weight: 700; }
h2 { margin: 0 0 12px; font-size: 15px; line-height: 1.2; }
.subtle { color: var(--muted); font-size: 12px; }
main { max-width: 1180px; margin: 0 auto; padding: 18px; }
.grid { display: grid; gap: 14px; }
.metrics { grid-template-columns: repeat(6, minmax(0, 1fr)); }
.two { grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr); }
.section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.metric {
  min-height: 84px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}
.metric .label { color: var(--muted); font-size: 12px; }
.metric .value { margin-top: 8px; font-size: 24px; line-height: 1; font-weight: 700; }
.metric .detail { margin-top: 8px; color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.status {
  display: inline-flex;
  align-items: center;
  height: 24px;
  border-radius: 999px;
  padding: 0 9px;
  border: 1px solid var(--line);
  color: var(--gray);
  background: #f8fafc;
  font-size: 12px;
  font-weight: 650;
}
.status.completed, .status.pass, .status.committed { color: var(--green); background: #ecfdf3; border-color: #b7e3c5; }
.status.running, .status.active { color: var(--blue); background: #eef4ff; border-color: #bfd2ff; }
.status.pending, .status.waiting_user { color: var(--amber); background: #fff7e6; border-color: #f1d18a; }
.status.error, .status.failed, .status.fail { color: var(--red); background: #fff1f1; border-color: #f3b8b8; }
.flow { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.step {
  min-height: 72px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  background: #fbfcfe;
}
.step strong { display: block; margin-bottom: 8px; overflow-wrap: anywhere; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: 12px; font-weight: 650; }
td { font-size: 13px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.truncate { max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-button {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--blue);
  cursor: pointer;
  font: inherit;
  padding: 0;
  text-align: left;
}
.run-button:hover { text-decoration: underline; }
tr.selected-row td { background: #eef4ff; }
.events { max-height: 420px; overflow: auto; }
.event { display: grid; grid-template-columns: 160px 150px minmax(0, 1fr); gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--line); }
.event:last-child { border-bottom: 0; }
.empty { color: var(--muted); padding: 24px 0; text-align: center; }
@media (max-width: 920px) {
  .metrics, .two, .flow { grid-template-columns: 1fr; }
  .headrow { align-items: flex-start; flex-direction: column; }
  .event { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<header>
  <div class="wrap headrow">
    <div>
      <h1>Phaseharness Metrics</h1>
      <div class="subtle" id="root"></div>
    </div>
    <div class="subtle" id="updated"></div>
  </div>
</header>
<main class="grid">
  <section class="grid metrics" id="metrics"></section>
  <section class="section" id="active"></section>
  <section class="section">
    <h2>Workflow</h2>
    <div class="flow" id="flow"></div>
  </section>
  <section class="grid two">
    <div class="section">
      <h2>Generate Phases</h2>
      <div id="phases"></div>
    </div>
    <div class="section">
      <h2>Recent Events</h2>
      <div class="events" id="events"></div>
    </div>
  </section>
  <section class="section">
    <h2>Recent Runs</h2>
    <div id="runs"></div>
  </section>
</main>
<script>
const h = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[ch]));
const status = (value) => `<span class="status ${h(value)}">${h(value || "unknown")}</span>`;
const duration = (seconds) => {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "-";
  const total = Math.max(0, Math.round(Number(seconds)));
  const hPart = Math.floor(total / 3600);
  const mPart = Math.floor((total % 3600) / 60);
  const sPart = total % 60;
  if (hPart) return `${hPart}h ${mPart}m`;
  if (mPart) return `${mPart}m ${sPart}s`;
  return `${sPart}s`;
};
const pct = (value) => value === null || value === undefined ? "-" : `${Math.round(Number(value) * 100)}%`;
const fmtTime = (value) => value ? new Date(value).toLocaleString() : "-";
let dashboardData = null;
let selectedRunId = null;

function runById(data, runId) {
  if (!runId) return null;
  return (data.runs || []).find((run) => run.run_id === runId) || null;
}

function pickSelectedRun(data) {
  const selected = runById(data, selectedRunId);
  if (selected) return selected;
  const activeId = data.active_run?.run_id;
  const active = runById(data, activeId) || data.active_run;
  if (active) {
    selectedRunId = active.run_id;
    return active;
  }
  const first = (data.runs || [])[0] || null;
  selectedRunId = first?.run_id || null;
  return first;
}

function isActiveSelection(data, run) {
  return Boolean(run && data.active_run && data.active_run.run_id === run.run_id);
}

function renderMetrics(data, run) {
  const aggregate = data.aggregate || {};
  const loop = run?.loop || {};
  const metrics = [
    ["Viewed", run ? run.status : "none", run ? run.run_id : "no run selected"],
    ["Stage", run ? run.current_stage : "-", run?.current_phase ? `phase ${run.current_phase}` : ""],
    ["Loop", run ? `${loop.current || 1} / ${loop.max || 1}` : "-", run ? `${run.metrics?.loop_retry_count || 0} retries` : ""],
    ["Elapsed", run ? duration(run.duration_seconds) : "-", run ? `started ${fmtTime(run.created_at)}` : ""],
    ["Post-eval fixes", run ? (run.metrics?.post_evaluate_fixes ? "yes" : "no") : "-", run ? `${run.metrics?.followup_phase_count || 0} follow-up phases` : ""],
    ["Completion", pct(aggregate.completion_rate), `${aggregate.completed_runs || 0}/${aggregate.total_runs || 0} runs`],
  ];
  document.getElementById("metrics").innerHTML = metrics.map(([label, value, detail]) => `
    <div class="metric">
      <div class="label">${h(label)}</div>
      <div class="value">${h(value)}</div>
      <div class="detail">${h(detail)}</div>
    </div>
  `).join("");
}

function renderSelectedRun(data, run) {
  const target = document.getElementById("active");
  if (!run) {
    target.innerHTML = `<h2>Selected Run</h2><div class="empty">No phaseharness run history.</div>`;
    return;
  }
  const scope = isActiveSelection(data, run) ? "active" : "history";
  target.innerHTML = `
    <h2>Selected Run</h2>
    <table>
      <tbody>
        <tr><th>Run</th><td class="mono">${h(run.run_id)}</td><th>Scope</th><td>${status(scope)}</td></tr>
        <tr><th>Status</th><td>${status(run.status)}</td><th>Stage</th><td>${h(run.current_stage || "-")}</td></tr>
        <tr><th>Request</th><td colspan="3">${h(run.request)}</td></tr>
        <tr><th>Evaluation</th><td>${status(run.evaluation_status)}</td><th>Commit mode</th><td>${h(run.commit_mode)}</td></tr>
        <tr><th>Updated</th><td>${h(fmtTime(run.updated_at))}</td><th>Elapsed</th><td>${h(duration(run.duration_seconds))}</td></tr>
      </tbody>
    </table>
  `;
}

function renderFlow(run) {
  const steps = run?.stages || [];
  document.getElementById("flow").innerHTML = steps.length ? steps.map((step) => `
    <div class="step">
      <strong>${h(step.stage)}</strong>
      ${status(step.status)}
      <div class="subtle">attempts ${h(step.attempts || 0)}</div>
      <div class="subtle">${h(duration(step.duration_seconds))}</div>
    </div>
  `).join("") : `<div class="empty">No workflow data.</div>`;
}

function table(rows, columns) {
  if (!rows.length) return `<div class="empty">No data.</div>`;
  return `<table><thead><tr>${columns.map((col) => `<th>${h(col.label)}</th>`).join("")}</tr></thead><tbody>${
    rows.map((row) => `<tr>${columns.map((col) => `<td>${col.render(row)}</td>`).join("")}</tr>`).join("")
  }</tbody></table>`;
}

function renderPhases(run) {
  const rows = run?.phases || [];
  document.getElementById("phases").innerHTML = table(rows, [
    { label: "Phase", render: (row) => `<span class="mono">${h(row.phase_id)}</span>` },
    { label: "Status", render: (row) => status(row.status) },
    { label: "Attempts", render: (row) => h(row.attempts || 0) },
    { label: "Duration", render: (row) => h(duration(row.duration_seconds)) },
    { label: "File", render: (row) => `<span class="mono truncate">${h(row.file)}</span>` },
  ]);
}

function renderEvents(run) {
  const events = (run?.events || []).slice().reverse();
  document.getElementById("events").innerHTML = events.length ? events.map((event) => `
    <div class="event">
      <div class="subtle">${h(fmtTime(event.time))}</div>
      <div class="mono">${h(event.type)}</div>
      <div class="subtle">${h(JSON.stringify(Object.fromEntries(Object.entries(event).filter(([key]) => !["time", "type", "run_id"].includes(key)))))}</div>
    </div>
  `).join("") : `<div class="empty">No events.</div>`;
}

function renderRuns(data, run) {
  const rows = data.runs || [];
  if (!rows.length) {
    document.getElementById("runs").innerHTML = `<div class="empty">No run history.</div>`;
    return;
  }
  document.getElementById("runs").innerHTML = `<table>
    <thead><tr><th>Run</th><th>Status</th><th>Loop</th><th>Post-eval fixes</th><th>Duration</th><th>Request</th></tr></thead>
    <tbody>${rows.map((row) => {
      const selected = run && row.run_id === run.run_id;
      return `<tr class="${selected ? "selected-row" : ""}">
        <td><button class="run-button mono" type="button" data-run-id="${h(row.run_id)}">${h(row.run_id)}</button></td>
        <td>${status(row.status)}</td>
        <td>${h(row.loop?.current || 1)} / ${h(row.loop?.max || 1)}</td>
        <td>${row.metrics?.post_evaluate_fixes ? "yes" : "no"}</td>
        <td>${h(duration(row.duration_seconds))}</td>
        <td><div class="truncate">${h(row.request)}</div></td>
      </tr>`;
    }).join("")}</tbody>
  </table>`;
}

function renderDashboard(data) {
  const run = pickSelectedRun(data);
  document.getElementById("root").textContent = data.root || "";
  document.getElementById("updated").textContent = `Updated ${fmtTime(data.generated_at)}`;
  renderMetrics(data, run);
  renderSelectedRun(data, run);
  renderFlow(run);
  renderPhases(run);
  renderEvents(run);
  renderRuns(data, run);
}

async function refresh() {
  const response = await fetch("/api/status", { cache: "no-store" });
  const data = await response.json();
  dashboardData = data;
  renderDashboard(data);
}

document.getElementById("runs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-run-id]");
  if (!button) return;
  selectedRunId = button.getAttribute("data-run-id");
  if (dashboardData) renderDashboard(dashboardData);
});

refresh().catch((error) => {
  document.getElementById("active").innerHTML = `<h2>Selected Run</h2><div class="empty">${h(error.message)}</div>`;
});
setInterval(() => refresh().catch(() => {}), 2000);
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    root: Path

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_text(self, status: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, payload: Any) -> None:
        self.send_text(status, json.dumps(payload, ensure_ascii=False, indent=2), "application/json")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/":
                self.send_text(200, html_page(), "text/html")
                return
            if path == "/api/status":
                self.send_json(200, dashboard_data(self.root))
                return
            if path == "/api/runs":
                self.send_json(200, {"runs": dashboard_data(self.root)["runs"]})
                return
            if path.startswith("/api/runs/"):
                run_id = safe_run_id(path.removeprefix("/api/runs/"))
                summary = summarize_run(self.root, run_id)
                if summary is None:
                    self.send_json(404, {"error": "run not found"})
                else:
                    self.send_json(200, summary)
                return
            self.send_json(404, {"error": "not found"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})


def command_summary(args: argparse.Namespace) -> int:
    root = find_project_root(Path(args.root) if args.root else None)
    data = dashboard_data(root, run_limit=args.limit)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    active = data.get("active_run")
    aggregate = data.get("aggregate", {})
    print(f"root: {data['root']}")
    print(f"runs: {aggregate.get('total_runs', 0)} total, {aggregate.get('active_runs', 0)} active")
    if active:
        print(
            "active: "
            f"{active.get('run_id')} "
            f"stage={active.get('current_stage')} "
            f"phase={active.get('current_phase') or '-'} "
            f"loop={active.get('loop', {}).get('current')}/{active.get('loop', {}).get('max')} "
            f"elapsed={active.get('duration_seconds')}"
        )
    else:
        print("active: none")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    root = find_project_root(Path(args.root) if args.root else None)
    handler = type("BoundDashboardHandler", (DashboardHandler,), {"root": root})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host = args.host if args.host != "0.0.0.0" else "127.0.0.1"
    print(f"Phaseharness dashboard: http://{host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve or print Phaseharness run metrics.")
    parser.add_argument("--root", help="project root; defaults to the current repository")
    sub = parser.add_subparsers(dest="command", required=True)

    summary = sub.add_parser("summary", help="print dashboard data")
    summary.add_argument("--json", action="store_true")
    summary.add_argument("--limit", type=int, default=50)
    summary.set_defaults(func=command_summary)

    serve = sub.add_parser("serve", help="serve the local dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.set_defaults(func=command_serve)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
