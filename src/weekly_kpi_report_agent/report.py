import html
import re
from datetime import date

from weekly_kpi_report_agent.models import Figure, Narrative, WeekReport

ATTRIBUTION = "Data: Online Retail II (Chen, D., 2012), UCI Machine Learning Repository, https://doi.org/10.24432/C5CG6D — licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
MARKERS = re.compile(r"\[(F\d+)\]")
WITHHELD_HEADLINE = "Figures only this week: the written summary was held back"
KEY_NUMBERS = [
    ("Revenue", "revenue"),
    ("Orders", "orders"),
    ("Average order", "aov"),
    ("Customers", "customers"),
]
ANOMALY_WORDS = {"wow": "vs last week", "vs4w": "vs 4-wk avg"}

INK = "#22201c"
MUTED = "#77716a"
FAINT = "#9a948c"
RULE = "#e6e0d6"
ACCENT = "#2e5e4e"
SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
SECTION = f"margin:28px 0 10px;font-family:{SERIF};font-size:18px;font-weight:normal;color:{ACCENT};"
SMALL = f"font-size:12px;line-height:1.5;color:{MUTED};"


def subject(week: WeekReport) -> str:
    prefix = "[NEEDS REVIEW] " if week.status == "needs_review" else ""
    return f"{prefix}Weekly sales KPIs — week of {week.week_start}"


def plain(reason: str) -> str:
    """DEC-19 plain-words version of a status reason."""
    computed = "Every figure below is computed from the data."
    if m := re.fullmatch(r"partial week: data ends (\d{4}-\d{2}-\d{2})", reason):
        day = date.fromisoformat(m[1]).strftime("%A")
        return f"Data stops on {day} {m[1]}, so this week is missing days. Don't compare it with full weeks."
    if m := re.fullmatch(r"large cancellations: (\S+) cancelled against .*", reason):
        return f"{m[1]} of products were cancelled this week. Revenue counts orders before cancellations, so the week's takings may be lower."
    if reason.startswith("narrative failed number check"):
        return f"The written summary failed the number check, so it is held back. {computed}"
    if reason in ("model output invalid", "cost cap reached") or reason.startswith(
        "model call failed: "
    ):
        return f"No written summary this week ({reason}). {computed}"
    if m := re.fullmatch(r"gmail draft failed: (.*)", reason):
        return f"The Gmail draft could not be created ({m[1]}); this local copy is complete."
    return reason


def change_words(figure: Figure) -> str:
    return "no comparison" if figure.value is None else f"{figure.display} vs last week"


def arrow(figure: Figure) -> str:
    if not figure.value or figure.display in ("+0.0%", "-0.0%"):
        return ""
    return "▲ " if figure.value > 0 else "▼ "


def render(
    week: WeekReport, narrative: Narrative | None, rejected: list[str]
) -> tuple[str, str]:
    """(markdown, html) for one week, layout as in DEC-19."""
    figures = {f.id: f for f in week.figures}
    by_key = {f.key: f for f in week.figures}
    end = figures["F2"].display
    kicker = f"Weekly sales · {week.week_start} to {end}"
    reasons = [plain(r) for r in week.reasons]
    used = sorted(
        {
            m
            for text in (narrative.texts() if narrative else rejected)
            for m in MARKERS.findall(text)
        },
        key=lambda i: int(i[1:]),
    )
    looks = [
        f"{key.split('_')[0].capitalize()} {by_key[key].display} {ANOMALY_WORDS[key.split('_')[1]]}"
        for key in week.anomalies
    ]
    shown = [f for f in week.figures if f.value is not None]
    tops = [
        (
            title,
            [
                by_key[f"{prefix}_{i}_revenue"]
                for i in range(1, 6)
                if by_key[f"{prefix}_{i}_revenue"].value is not None
            ],
        )
        for title, prefix in [("Top products", "product"), ("Top countries", "country")]
    ]
    withheld = (
        "Narrative withheld: the text failed the number check."
        if rejected
        else "Narrative withheld: no narrative was produced."
    ) + " The figures are computed in code and can be used as they are."
    headline = narrative.headline if narrative else WITHHELD_HEADLINE
    others = [
        (
            f"Cancellation rate {by_key['cancellation_rate'].display} · "
            f"Cancelled products {by_key['cancelled_value'].display} · "
            f"Revenue after cancellations {by_key['net_revenue'].display}"
        )
    ]
    if by_key["lines_without_customer_id"].value:
        others.append(
            f"No customer ID on {by_key['lines_without_customer_id'].display} of "
            f"{by_key['product_lines'].display} product lines; Customers counts only lines with one."
        )
    partial = any(r.startswith("partial week: ") for r in week.reasons)

    def text(value: str) -> str:
        return MARKERS.sub(
            lambda m: f'<sup style="font-size:10px;color:{FAINT};">{m[1]}</sup>',
            html.escape(value).replace(" [F", "[F"),
        )

    md = [f"# {kicker}", ""]
    page = [
        f'<p style="margin:0 0 6px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:{MUTED};">{html.escape(kicker)}</p>'
    ]
    if reasons:
        md += ["> **Needs review**", ">", *(f"> - {r}" for r in reasons), ""]
        page.append(
            '<div style="margin:14px 0 18px;padding:14px 16px;background:#fbf1dc;border-left:4px solid #b7791f;border-radius:4px;">'
            '<p style="margin:0 0 6px;font-weight:600;color:#7a4e0e;">Needs review</p>'
            + "".join(
                f'<p style="margin:4px 0 0;font-size:14px;line-height:1.5;color:{INK};">{html.escape(r)}</p>'
                for r in reasons
            )
            + "</div>"
        )
    if week.status == "no_data":
        line = f"No sales data for week {week.week_start} ({week.week_start}..{end}): no product lines in the dataset for these dates."
        md += [line, ""]
        page.append(
            f'<p style="margin:16px 0;font-size:16px;line-height:1.6;">{html.escape(line)}</p>'
        )
    else:
        md += [f"## {headline}", ""]
        page.append(
            f'<h1 style="margin:6px 0 20px;font-family:{SERIF};font-size:26px;line-height:1.25;font-weight:normal;color:{INK};">{text(headline)}</h1>'
        )
        tiles = []
        for label, key in KEY_NUMBERS:
            value, wow = by_key[key], by_key[f"{key}_wow"]
            vs4w, yoy = by_key[f"{key}_vs4w"].display, by_key[f"{key}_yoy"].display
            md.append(
                f"- {label}: {value.display} ({change_words(wow)}; vs 4-wk avg {vs4w} · vs last year {yoy})"
            )
            tiles.append(
                f'<div style="display:inline-block;vertical-align:top;width:120px;margin:0 8px 10px 0;padding:12px;border:1px solid {RULE};border-radius:6px;">'
                f'<div style="font-size:12px;color:{MUTED};">{label}</div>'
                f'<div style="margin:2px 0 4px;font-family:{SERIF};font-size:22px;color:{INK};">{html.escape(value.display)}</div>'
                f'<div style="font-size:12px;color:{FAINT if partial else INK};">{arrow(wow)}{html.escape(change_words(wow))}</div>'
                f'<div style="margin-top:2px;font-size:11px;color:{FAINT};">vs 4-wk avg {html.escape(vs4w)} · vs last year {html.escape(yoy)}</div>'
                "</div>"
            )
        md += [*(f"- {x}" for x in others), ""]
        page += [
            f"<div>{''.join(tiles)}</div>",
            *(
                f'<p style="margin:2px 0 6px;font-size:13px;color:{MUTED};">{html.escape(x)}</p>'
                for x in others
            ),
            '<div style="height:16px;"></div>',
        ]
        para = f"margin:0 0 14px;font-size:16px;line-height:1.6;color:{INK};"
        if narrative:
            md += [p + "\n" for p in narrative.paragraphs]
            page += [f'<p style="{para}">{text(p)}</p>' for p in narrative.paragraphs]
        else:
            md += [withheld, ""]
            page.append(f'<p style="{para}">{html.escape(withheld)}</p>')
            if rejected:
                md += ["### Rejected sentences", "", *(f"> {s}\n" for s in rejected)]
                page.append(f'<p style="{SMALL}margin:0 0 6px;">Rejected sentences</p>')
                page += [
                    f'<blockquote style="margin:0 0 8px;padding:6px 12px;border-left:3px solid {RULE};font-size:14px;color:{MUTED};">{text(s)}</blockquote>'
                    for s in rejected
                ]
        if looks:
            md += ["## Worth a look", "", *(f"- {x}" for x in looks), ""]
            page.append(f'<h2 style="{SECTION}">Worth a look</h2>')
            page += [
                f'<p style="margin:0 0 6px;font-size:15px;color:{INK};">{html.escape(x)}</p>'
                for x in looks
            ]
        blocks = []
        for title, rows in tops:
            if not rows:
                continue
            md += [
                f"## {title}",
                "",
                *(f'{i}. "{f.label}" {f.display}' for i, f in enumerate(rows, 1)),
                "",
            ]
            blocks.append(
                f'<div style="display:inline-block;vertical-align:top;width:296px;margin:0 12px 8px 0;">'
                f'<h2 style="{SECTION}">{title}</h2>'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                + "".join(
                    f'<tr><td style="padding:5px 8px 5px 0;border-bottom:1px solid {RULE};font-size:14px;color:{INK};">{html.escape(f.label)}</td>'
                    f'<td align="right" style="padding:5px 0;border-bottom:1px solid {RULE};font-size:14px;color:{INK};white-space:nowrap;">{html.escape(f.display)}</td></tr>'
                    for f in rows
                )
                + "</table></div>"
            )
        page.append(f"<div>{''.join(blocks)}</div>")
        if used:
            md += [
                "## Sources",
                "",
                *(
                    f"- [{i}] {figures[i].label}: {figures[i].display} — {figures[i].source}"
                    for i in used
                ),
                "",
            ]
            page.append(
                f'<details><summary style="{SECTION}cursor:pointer;">Sources</summary>'
            )
            page += [
                f'<p style="{SMALL}margin:0 0 4px;"><span style="color:{FAINT};">{i}</span> {html.escape(figures[i].label)}: {html.escape(figures[i].display)} — {html.escape(figures[i].source)}</p>'
                for i in used
            ]
            page.append("</details>")
        md += [
            "## All figures",
            "",
            "| ID | Figure | Value | Source |",
            "| --- | --- | --- | --- |",
            *(
                f"| {f.id} | {f.label.replace('|', '/')} | {f.display} | {f.source.replace('|', '/')} |"
                for f in shown
            ),
            "",
        ]
        cell = f"padding:4px 6px 4px 0;border-top:1px solid {RULE};vertical-align:top;font-size:11px;line-height:1.4;color:{MUTED};"
        page += [
            f'<details><summary style="{SECTION}cursor:pointer;">All figures ({len(shown)})</summary>',
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">',
            *(
                f'<tr><td style="{cell}color:{FAINT};">{f.id}</td><td style="{cell}">{html.escape(f.label)}</td>'
                f'<td style="{cell}white-space:nowrap;">{html.escape(f.display)}</td><td style="{cell}">{html.escape(f.source)}</td></tr>'
                for f in shown
            ),
            "</table></details>",
        ]
    md += ["---", "", ATTRIBUTION, ""]
    page.append(
        f'<p style="{SMALL}margin:28px 0 0;padding-top:12px;border-top:1px solid {RULE};">{html.escape(ATTRIBUTION)}</p>'
    )
    body = "\n".join(page)
    return (
        "\n".join(md),
        (
            "<!DOCTYPE html>\n"
            '<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(subject(week))}</title></head>\n"
            f'<body style="margin:0;padding:0;background:#f6f3ee;font-family:{SANS};color:{INK};">\n'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f3ee;"><tr><td align="center" style="padding:20px 10px;">\n'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;background:#fffdf9;border:1px solid {RULE};border-radius:8px;"><tr><td align="left" style="padding:26px 22px;font-family:{SANS};color:{INK};">\n'
            f"{body}\n"
            "</td></tr></table>\n</td></tr></table>\n</body></html>\n"
        ),
    )
