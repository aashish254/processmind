"""HTML analyst report generator.

Self-contained, print-ready report embedding the As-Is and To-Be SVG
diagrams, findings, recommendations, before/after metrics and event-log
analytics. No JavaScript, no CDN - renders offline.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

from process_miner.export.svg import to_svg
from process_miner.models import PipelineResult, ProcessModel


def build_report(result: PipelineResult, eval_note: str = "") -> str:
    model = result.model
    tobe = result.tobe_model
    report = result.bottleneck_report
    if model is None:
        raise ValueError("PipelineResult has no model")

    asis_svg = to_svg(model)
    tobe_svg = to_svg(tobe) if tobe else ""
    m_asis = model.summary_metrics()
    m_tobe = tobe.summary_metrics() if tobe else None

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Process Report - {html.escape(model.name)}</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; margin: 0; background: #f4f6f9; color: #1a1a2e; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  header {{ background: #16325c; color: #fff; padding: 28px 32px; border-radius: 12px; }}
  header h1 {{ margin: 0 0 6px; font-size: 26px; }}
  header .meta {{ color: #b8c7e0; font-size: 13px; }}
  .chips {{ margin-top: 10px; }}
  .chip {{ display: inline-block; background: #2d4e86; color: #dce6f7; padding: 3px 10px; border-radius: 20px; font-size: 12px; margin-right: 6px; }}
  section {{ background: #fff; border-radius: 12px; padding: 24px 28px; margin-top: 20px; box-shadow: 0 1px 3px rgba(20,30,60,.08); }}
  h2 {{ margin-top: 0; font-size: 19px; color: #16325c; border-bottom: 2px solid #e8edf5; padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th {{ text-align: left; background: #f0f3f9; color: #333; padding: 8px 10px; border-bottom: 2px solid #dfe6f0; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eef1f6; vertical-align: top; }}
  .sev-high {{ background: #fdecea; color: #b03a2e; padding: 2px 9px; border-radius: 12px; font-size: 11.5px; font-weight: 600; }}
  .sev-medium {{ background: #fff4e0; color: #9a6b00; padding: 2px 9px; border-radius: 12px; font-size: 11.5px; font-weight: 600; }}
  .sev-low {{ background: #e8f0fe; color: #1a4fa0; padding: 2px 9px; border-radius: 12px; font-size: 11.5px; font-weight: 600; }}
  .cards {{ display: flex; gap: 14px; flex-wrap: wrap; }}
  .card {{ flex: 1 1 150px; background: #f8fafd; border: 1px solid #e3e9f3; border-radius: 10px; padding: 14px 16px; }}
  .card .k {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #7a8699; }}
  .card .v {{ font-size: 22px; font-weight: 700; color: #16325c; margin-top: 2px; }}
  .card .d {{ font-size: 12px; color: #5a6b85; margin-top: 2px; }}
  .diagram {{ overflow: auto; border: 1px solid #e6ebf2; border-radius: 8px; padding: 10px; background: #fff; }}
  .diagram svg {{ width: 100%; height: auto; display: block; }}
  .improved {{ color: #1c7c3c; font-weight: 700; }}
  .worsened {{ color: #b03a2e; font-weight: 700; }}
  pre {{ background: #0f1c33; color: #d7e3f7; padding: 16px; border-radius: 8px; overflow: auto; font-size: 12px; }}
  .applied {{ color: #1c7c3c; font-weight: 700; }}
  .notapplied {{ color: #8a94a6; }}
  footer {{ color: #8a94a6; font-size: 12px; text-align: center; padding: 22px 0 30px; }}
  @media print {{ body {{ background: #fff; }} section {{ box-shadow: none; border: 1px solid #eee; page-break-inside: avoid; }} }}
</style>
</head>
<body><div class="wrap">
<header>
  <h1>{html.escape(model.name)}</h1>
  <div class="meta">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} &middot; engine: {html.escape(result.engine)} &middot; extractor: {html.escape(result.modeler_method)}</div>
  <div class="chips"><span class="chip">BPMN 2.0</span><span class="chip">{m_asis.task_count} tasks</span><span class="chip">{m_asis.lane_count} lanes</span><span class="chip">{len(report.findings) if report else 0} findings</span></div>
</header>"""]

    # metrics
    parts.append('<section><h2>Key metrics</h2><div class="cards">')
    cards = [
        ("Tasks", str(m_asis.task_count), "" if not m_tobe else _delta(m_asis.task_count, m_tobe.task_count, lower_better=True)),
        ("Automation rate", f"{m_asis.automation_rate:.0%}", "" if not m_tobe else _delta(m_asis.automation_rate, m_tobe.automation_rate, lower_better=False, pct=True)),
        ("Est. cycle time", _fmt_minutes(m_asis.estimated_cycle_time_minutes), "" if not m_tobe else _delta(m_asis.estimated_cycle_time_minutes, m_tobe.estimated_cycle_time_minutes, lower_better=True, minutes=True)),
        ("Gateways", str(m_asis.gateway_count), "" if not m_tobe else _delta(m_asis.gateway_count, m_tobe.gateway_count, lower_better=None)),
        ("Manual steps", str(m_asis.manual_count), "" if not m_tobe else _delta(m_asis.manual_count, m_tobe.manual_count, lower_better=True)),
    ]
    for k, v, d in cards:
        parts.append(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div><div class="d">{d}</div></div>')
    parts.append('</div></section>')

    # as-is diagram
    parts.append(f'<section><h2>As-Is process model</h2><div class="diagram">{asis_svg}</div></section>')

    # findings
    if report and report.findings:
        parts.append('<section><h2>Bottleneck findings</h2><table><tr><th>Severity</th><th>Finding</th><th>Detail</th><th>Evidence</th></tr>')
        for f in report.findings:
            parts.append(
                f'<tr><td><span class="sev-{f.severity}">{f.severity.upper()}</span></td>'
                f'<td><b>{html.escape(f.title)}</b><br><span style="color:#7a8699;font-size:12px">{f.category}</span></td>'
                f'<td>{html.escape(f.description)}</td><td>{html.escape("; ".join(f.evidence))}</td></tr>'
            )
        parts.append('</table></section>')

    # recommendations
    if report and report.recommendations:
        parts.append('<section><h2>Recommendations (As-Is &rarr; To-Be)</h2><table><tr><th>#</th><th>Recommendation</th><th>Category</th><th>Expected impact</th><th>Applied</th></tr>')
        for r in report.recommendations:
            state = '<span class="applied">Yes</span>' if r.applied else '<span class="notapplied">Advisory</span>'
            parts.append(
                f'<tr><td>{r.id}</td><td><b>{html.escape(r.title)}</b><br><span style="color:#5a6b85;font-size:12.5px">{html.escape(r.description)}</span></td>'
                f'<td>{r.category}</td><td>{html.escape(r.expected_impact)}<br><span style="color:#7a8699;font-size:12px">confidence {r.confidence:.0%}</span></td>'
                f'<td>{state}</td></tr>'
            )
        parts.append('</table></section>')

    # to-be diagram
    if tobe is not None and tobe_svg:
        parts.append(f'<section><h2>To-Be process model (after applied recommendations)</h2><div class="diagram">{tobe_svg}</div></section>')

    # conformance (documented vs enacted)
    if result.conformance is not None:
        c = result.conformance
        parts.append(
            f'<section><h2>Conformance — documented vs enacted</h2>'
            f'<p>{html.escape(c.summary)}</p>'
            f'<div class="cards">'
            f'<div class="card"><div class="k">Matched activities</div><div class="v">{len(c.matched_activities)}</div>'
            f'<div class="d">of {len(c.matched_activities) + len(c.documented_only)} documented</div></div>'
            f'<div class="card"><div class="k">DF precision</div><div class="v">{c.df_precision:.0%}</div><div class="d">documented flow observed in log</div></div>'
            f'<div class="card"><div class="k">DF recall</div><div class="v">{c.df_recall:.0%}</div><div class="d">observed flow explained by SOP</div></div>'
            f'<div class="card"><div class="k">Trace fitness</div><div class="v">{c.fitness:.0%}</div><div class="d">observed handovers replayable on the SOP</div></div>'
            f'<div class="card"><div class="k">Drift issues</div><div class="v">{len(c.issues)}</div><div class="d">see below</div></div>'
            f'</div>'
        )
        if c.issues:
            parts.append('<table style="margin-top:14px"><tr><th>Kind</th><th>Finding</th><th>Evidence</th></tr>')
            for i in c.issues:
                ev = "<br>".join(html.escape(e) for e in i.evidence[:8])
                parts.append(
                    f'<tr><td><span class="sev-{i.severity}">{html.escape(i.kind)}</span></td>'
                    f'<td><b>{html.escape(i.title)}</b><br><span style="color:#5a6b85;font-size:12.5px">{html.escape(i.description)}</span></td>'
                    f'<td>{ev}</td></tr>'
                )
            parts.append('</table>')
        parts.append('</section>')

    # log analytics
    if report and report.log_summary:
        ls = report.log_summary
        parts.append(f'<section><h2>Event-log analytics</h2><p>{ls.cases} cases &middot; {ls.events} events &middot; {ls.activities_count} distinct activities &middot; top bottlenecks: <b>{html.escape(", ".join(ls.top_bottlenecks))}</b></p>')
        parts.append('<table><tr><th>Activity</th><th>Frequency</th><th>Cases</th><th>Median wait</th><th>Total wait</th><th>Rework rate</th><th>Bottleneck score</th></tr>')
        for a in ls.activities[:12]:
            parts.append(
                f'<tr><td>{html.escape(a.name)}</td><td>{a.frequency}</td><td>{a.cases}</td>'
                f'<td>{_fmt_minutes(a.median_wait_minutes)}</td><td>{_fmt_minutes(a.total_wait_minutes)}</td>'
                f'<td>{a.rework_rate:.0%}</td><td>{a.bottleneck_score:.2f}</td></tr>'
            )
        parts.append('</table>')
        if ls.variants:
            parts.append('<h3 style="margin-top:18px">Top variants</h3><table><tr><th>Share</th><th>Count</th><th>Sequence</th></tr>')
            for v in ls.variants:
                parts.append(f'<tr><td>{v.share:.0%}</td><td>{v.count}</td><td>{html.escape(" &rarr; ".join(v.sequence))}</td></tr>')
            parts.append('</table>')
        parts.append('</section>')

    if eval_note:
        parts.append(f'<section><h2>Extraction evaluation</h2><div>{eval_note}</div></section>')

    # mermaid + artifacts
    from process_miner.export.mermaid import to_mermaid

    parts.append(f'<section><h2>Mermaid source</h2><pre>{html.escape(to_mermaid(model))}</pre></section>')
    if result.artifacts:
        rows = "".join(
            f'<tr><td>{html.escape(k)}</td><td><code>{html.escape(v)}</code></td></tr>'
            for k, v in sorted(result.artifacts.items())
        )
        parts.append(f'<section><h2>Artifacts</h2><table>{rows}</table></section>')

    parts.append(f'<footer>ProcessMind &middot; Enterprise AI Process Mining &amp; BPMN Automation &middot; {datetime.now().year}</footer>')
    parts.append('</div></body></html>')
    return "\n".join(parts)


def _delta(a: float, b: float, lower_better: Optional[bool], pct: bool = False, minutes: bool = False) -> str:
    if a == b:
        return "unchanged"
    diff = b - a
    sign = "+" if diff >= 0 else ""
    val = f"{sign}{diff:.0%}" if pct else (_fmt_minutes(abs(diff)) if minutes else f"{sign}{diff:g}")
    if lower_better is None:
        return f"({val})"
    good = (diff < 0) if lower_better else (diff > 0)
    cls = "improved" if good else "worsened"
    arrow = "&darr;" if diff < 0 else "&uarr;"
    return f'<span class="{cls}">{arrow} {val}</span>'


def _fmt_minutes(m: float) -> str:
    if m >= 1440:
        return f"{m / 1440:.1f} d"
    if m >= 60:
        return f"{m / 60:.1f} h"
    return f"{m:.0f} min"
