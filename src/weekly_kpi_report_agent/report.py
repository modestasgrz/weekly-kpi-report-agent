import html
import re

from weekly_kpi_report_agent.models import Narrative, WeekReport

ATTRIBUTION = "Data: Online Retail II (Chen, D., 2012), UCI Machine Learning Repository, https://doi.org/10.24432/C5CG6D — licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
MARKERS = re.compile(r"\[(F\d+)\]")


def subject(week: WeekReport) -> str:
    prefix = "[NEEDS REVIEW] " if week.status == "needs_review" else ""
    return f"{prefix}Weekly sales KPIs — week of {week.week_start}"


def render(
    week: WeekReport, narrative: Narrative | None, rejected: list[str]
) -> tuple[str, str]:
    """(markdown, html) for one week, sections as in DEC-11."""
    figures = {f.id: f for f in week.figures}
    end = figures["F2"].display
    title = f"Weekly sales KPIs — week of {week.week_start} to {end}"
    used = sorted(
        {
            m
            for text in (narrative.texts() if narrative else [])
            for m in MARKERS.findall(text)
        },
        key=lambda i: int(i[1:]),
    )
    by_key = {f.key: f for f in week.figures}
    flags = [
        *week.reasons,
        *(
            f"anomaly: {key} [{by_key[key].id}] {by_key[key].display}"
            for key in week.anomalies
        ),
    ]
    shown = [f for f in week.figures if f.value is not None]
    withheld = (
        "Narrative withheld: the text failed the number check."
        if rejected
        else "Narrative withheld: no narrative was produced (see Flags)."
    ) + " The figures below are computed in code and can be used as they are."

    md = [f"# {title}", "", f"Status: {week.status}", ""]
    page = [
        f"<h1>{html.escape(title)}</h1>",
        f"<p>Status: <b>{html.escape(week.status)}</b></p>",
    ]
    if week.status == "no_data":
        line = f"No sales data for week {week.week_start} ({week.week_start}..{end}): no product lines in the dataset for these dates."
        md += [line, ""]
        page.append(f"<p>{html.escape(line)}</p>")
    elif narrative:
        md += [
            "## Summary",
            "",
            f"**{narrative.headline}**",
            "",
            *(p + "\n" for p in narrative.paragraphs),
        ]
        page += [
            "<h2>Summary</h2>",
            f"<p><b>{html.escape(narrative.headline)}</b></p>",
            *(f"<p>{html.escape(p)}</p>" for p in narrative.paragraphs),
        ]
    else:
        md += [
            "## Summary",
            "",
            withheld,
            "",
        ]
        page += [
            "<h2>Summary</h2>",
            f"<p>{html.escape(withheld)}</p>",
        ]
        if rejected:
            md += ["### Rejected sentences", "", *(f"> {s}\n" for s in rejected)]
            page += [
                "<h3>Rejected sentences</h3>",
                *(f"<blockquote>{html.escape(s)}</blockquote>" for s in rejected),
            ]
    if flags:
        md += ["## Flags", "", *(f"- {f}" for f in flags), ""]
        page += [
            "<h2>Flags</h2>",
            "<ul>",
            *(f"<li>{html.escape(f)}</li>" for f in flags),
            "</ul>",
        ]
    if week.status != "no_data":
        md += [
            "## Figures",
            "",
            "| ID | Figure | Value | Source |",
            "| --- | --- | --- | --- |",
        ]
        md += [
            f"| {f.id} | {f.label.replace('|', '/')} | {f.display} | {f.source.replace('|', '/')} |"
            for f in shown
        ]
        md.append("")
        page += [
            "<h2>Figures</h2>",
            "<table><tr><th>ID</th><th>Figure</th><th>Value</th><th>Source</th></tr>",
        ]
        page += [
            f"<tr><td>{f.id}</td><td>{html.escape(f.label)}</td><td>{html.escape(f.display)}</td><td>{html.escape(f.source)}</td></tr>"
            for f in shown
        ]
        page.append("</table>")
    if used:
        md += [
            "## Footnotes",
            "",
            *(
                f"- [{i}] {figures[i].label}: {figures[i].display} — {figures[i].source}"
                for i in used
            ),
            "",
        ]
        page += [
            "<h2>Footnotes</h2>",
            "<ol>",
            *(
                f"<li>[{i}] {html.escape(figures[i].label)}: {html.escape(figures[i].display)} — {html.escape(figures[i].source)}</li>"
                for i in used
            ),
            "</ol>",
        ]
    md += ["---", "", ATTRIBUTION, ""]
    page += ["<hr>", f"<p><small>{html.escape(ATTRIBUTION)}</small></p>"]
    body = "\n".join(page)
    return (
        "\n".join(md),
        f'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title></head><body>\n{body}\n</body></html>\n',
    )
