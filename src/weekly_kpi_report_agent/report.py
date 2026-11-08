import html
import re
from datetime import date

from weekly_kpi_report_agent.kpis import rounded
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

INK = "#EDE6D8"
INK2 = "#dccfba"
MUTED = "#8a857b"
AMBER = "#E8A83C"
AMBER2 = "#B0791C"
CARD = "#0e1b13"
SURFACE = "#1b241e"
BANNER = "#2a2416"
RULE = "#2a352d"
RED = "#F08A7E"
SPARK_PX = 28
SANS = "'Avenir Next', Avenir, 'Helvetica Neue', Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', Menlo, monospace"
SECTION = f"margin:28px 0 10px;font-family:{SANS};font-size:13px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:{AMBER};"
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
    if m := re.fullmatch(r"large cancellations: (.+?) cancelled against .*", reason):
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


def look_at_this(week: WeekReport) -> list[str]:
    """DEC-22 action lines, written by code, at most 3."""
    by_key = {f.key: f for f in week.figures}
    lines: list[str] = []
    if cause := week.cause:
        lines.append(
            f'Check cancellation {cause.cancel_invoice}: was "{cause.product}" a lost sale or a mistake?'
            if cause.cancel_invoice
            else f'Check order {cause.invoice}: "{cause.product}" is {by_key["top_line_share"].display} of revenue'
        )
    for reason in week.reasons:
        if m := re.fullmatch(r"partial week: data ends (\S+)", reason):
            lines.append(f"Re-run this report once the data after {m[1]} is in.")
    partial = any(r.startswith("partial week: ") for r in week.reasons)
    for kpi in [] if partial else ["revenue", "orders"]:
        for kind, words in [("wow", "vs last week"), ("vs4w", "vs the 4-week average")]:
            move = by_key[f"{kpi}_{kind}"]
            if f"{kpi}_{kind}" in week.anomalies and (move.value or 0) < 0:
                lines.append(
                    f"Find out why {kpi} fell {move.display.lstrip('-')} {words}"
                )
    top = by_key["product_1_revenue"]
    if (
        len(lines) < 3
        and top.value is not None
        and top.id not in week.cancelled_products
    ):
        lines.append(f'Keep "{top.label}" in stock: the top seller at {top.display}.')
    return lines[:3]


def render(
    week: WeekReport, narrative: Narrative | None, rejected: list[str]
) -> tuple[str, str]:
    """(markdown, html) for one week, layout as in DEC-19 (round 4)."""
    figures = {f.id: f for f in week.figures}
    by_key = {f.key: f for f in week.figures}
    end = figures["F2"].display
    kicker = f"Weekly sales · {week.week_start} to {end}"
    reasons = [plain(r) for r in week.reasons]
    partial = any(r.startswith("partial week: ") for r in week.reasons)
    cancelled_week = any(r.startswith("large cancellations: ") for r in week.reasons)
    used = sorted(
        {
            m
            for text in (narrative.texts() if narrative else rejected)
            for m in MARKERS.findall(text)
            if m in figures
        },
        key=lambda i: int(i[1:]),
    )
    shown = [f for f in week.figures if f.value is not None]
    withheld = (
        "Narrative withheld: the text failed the number check."
        if rejected
        else "Narrative withheld: no narrative was produced."
    ) + " The figures are computed in code and can be used as they are."
    headline = narrative.headline if narrative else WITHHELD_HEADLINE
    revenue = by_key["revenue"]

    def text(value: str) -> str:
        return html.escape(re.sub(r" ?\[F\d+\]", "", value))

    def share(figure: Figure) -> int:
        return int(rounded(100 * (figure.value or 0) / (revenue.value or 1), "1"))

    def chip(move: Figure, key: str, size: int = 12) -> str:
        words = change_words(move) + (
            " · partial week, not comparable" if partial else ""
        )
        value = move.value
        flat = value is None or abs(value) < 1.0
        colour = (
            INK2
            if partial or flat
            else RED
            if (value or 0) < 0
            and any(
                f"{key}_{kind}" in week.anomalies
                and (by_key[f"{key}_{kind}"].value or 0) < 0
                for kind in ["wow", "vs4w"]
            )
            else AMBER
            if (value or 0) >= 1.0
            else INK2
        )
        mark = "" if flat else "▲ " if (value or 0) > 0 else "▼ "
        return (
            f'<span style="display:inline-block;padding:2px 8px;border:1px solid {colour};'
            f'border-radius:10px;font-size:{size}px;line-height:1.5;color:{colour};">{mark}{html.escape(words)}</span>'
        )

    def bar(fraction: float, colour: str) -> str:
        width = max(1, min(100, round(100 * fraction)))
        return (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td width="{width}%" height="8" bgcolor="{colour}" style="height:8px;font-size:0;line-height:0;background-color:{colour};">&nbsp;</td>'
            + (
                f'<td width="{100 - width}%" style="font-size:0;line-height:0;">&nbsp;</td>'
                if width < 100
                else ""
            )
            + "</tr></table>"
        )

    md = [f"# {kicker}", ""]
    page = [
        f'<p style="margin:0 0 6px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:{MUTED};">{html.escape(kicker)}</p>'
    ]
    if reasons:
        md += ["> **Needs review**", ">", *(f"> - {r}" for r in reasons), ""]
        page.append(
            f'<div style="margin:14px 0 18px;padding:14px 16px;background-color:{BANNER};border-left:4px solid {AMBER2};border-radius:8px;">'
            f'<p style="margin:0 0 6px;font-weight:600;color:{AMBER};">Needs review</p>'
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
            f'<p style="margin:16px 0;font-size:16px;line-height:1.6;color:{INK};">{html.escape(line)}</p>'
        )
    else:
        md += [f"## {headline}", ""]
        page.append(
            f'<h1 style="margin:6px 0 18px;font-family:{SANS};font-size:24px;line-height:1.3;font-weight:600;color:{INK};">{text(headline)}</h1>'
        )
        hero_label = "Revenue after cancellations" if cancelled_week else "Revenue"
        hero = by_key["net_revenue"] if cancelled_week else revenue
        yoy = by_key["revenue_yoy"]
        under = (
            f"Booked {revenue.display}"
            if cancelled_week
            else (f"{yoy.display} vs last year" if yoy.value is not None else "")
        )
        md += [
            f"**{hero_label}: {hero.display}**" + (f" · {under}" if under else ""),
            "",
        ]
        page.append(
            f'<div style="margin:0 0 18px;">'
            f'<div style="font-size:13px;color:{INK2};">{hero_label}</div>'
            f'<div style="margin:2px 0 6px;font-size:44px;line-height:1.1;font-weight:600;color:{INK};">{html.escape(hero.display)}</div>'
            + (
                ""
                if cancelled_week
                else chip(by_key["revenue_wow"], "revenue", 13) + " "
            )
            + (
                f'<span style="font-size:13px;color:{INK2};">{html.escape(under)}</span>'
                if under
                else ""
            )
            + "</div>"
        )
        if cause := week.cause:
            minutes = by_key["top_line_cancel_minutes"]
            if cause.rule == "top_cancel":
                card = f"1 cancellation: {cause.product} · {by_key['top_cancel_value'].display} = {by_key['top_cancel_share'].display} of cancelled value"
            elif minutes.value is None:
                card = f"1 order: {cause.product} ×{by_key['top_line_quantity'].display} · {by_key['top_line_revenue'].display} = {by_key['top_line_share'].display} of revenue"
            else:
                hours = int(rounded(minutes.value / 60, "1"))
                days = int(rounded(minutes.value / 1440, "1"))
                later = (
                    f"{minutes.display} min later"
                    if minutes.value < 120
                    else f"{hours} hours later"
                    if minutes.value < 1440
                    else f"{days} day{'' if days == 1 else 's'} later"
                )
                card = f"1 order: {cause.product} ×{by_key['top_line_quantity'].display} · {by_key['top_line_revenue'].display} → cancelled {later}"
            md += [f"**What changed:** {card}", ""]
            bar_rows = ""
            if cause.rule == "top_line":
                without, move = (
                    by_key["revenue_excl_top_line"],
                    by_key["revenue_excl_top_line_wow"],
                )
                bar_rows = "".join(
                    f'<tr><td width="38%" bgcolor="{SURFACE}" style="padding:6px 8px 0 0;font-size:13px;color:{INK2};">{label}</td>'
                    f'<td width="34%" bgcolor="{SURFACE}" style="padding:6px 8px 0 0;">{bar((value.value or 0) / (revenue.value or 1), colour)}</td>'
                    f'<td align="right" bgcolor="{SURFACE}" style="padding:6px 0 0;font-size:13px;color:{INK};white-space:nowrap;">{html.escape(note)}</td></tr>'
                    for label, value, colour, note in [
                        ("As booked", revenue, MUTED, revenue.display),
                        (
                            "Without this order",
                            without,
                            AMBER,
                            f"{without.display} ({change_words(move)})",
                        ),
                    ]
                )
                md += [
                    f"- As booked: {revenue.display}",
                    f"- Without this order: {without.display} ({change_words(move)})",
                    "",
                ]
            page.append(
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{SURFACE}" style="margin:0 0 18px;background-color:{SURFACE};border-left:4px solid {RED};border-radius:8px;">'
                f'<tr><td bgcolor="{SURFACE}" style="padding:14px 16px;">'
                f'<div style="font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:{RED};">What changed</div>'
                f'<div style="margin-top:6px;font-size:15px;line-height:1.5;color:{INK};">{html.escape(card)}</div>'
                + (
                    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">{bar_rows}</table>'
                    if bar_rows
                    else ""
                )
                + "</td></tr></table>"
            )
        if actions := look_at_this(week):
            md += ["## Look at this", "", *(f"- {a}" for a in actions), ""]
            page.append(f'<h2 style="{SECTION}margin-top:6px;">Look at this</h2>')
            page += [
                f'<p style="margin:0 0 6px;font-size:15px;line-height:1.5;color:{INK};"><span style="color:{AMBER};">→</span> {html.escape(a)}</p>'
                for a in actions
            ]
        tiles = []
        for label, key in KEY_NUMBERS:
            value, wow = by_key[key], by_key[f"{key}_wow"]
            vs4w, yoy4 = by_key[f"{key}_vs4w"].display, by_key[f"{key}_yoy"].display
            md.append(
                f"- {label}: {value.display} ({change_words(wow)}; vs 4-wk avg {vs4w} · vs last year {yoy4})"
            )
            series = week.history.get(key, [])
            peak = max(series, default=0.0)
            sparks = "".join(
                f'<td valign="bottom" width="8%" style="padding:0 1px;height:{SPARK_PX}px;">'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'<td height="{h}" bgcolor="{c}" style="height:{h}px;font-size:0;line-height:0;background-color:{c};">&nbsp;</td>'
                "</tr></table></td>"
                for i, v in enumerate(series)
                for h, c in [
                    (
                        max(1, round(SPARK_PX * v / peak)) if peak > 0 else 1,
                        AMBER if i == len(series) - 1 else MUTED,
                    )
                ]
            )
            tiles.append(
                f'<td width="50%" valign="top" style="padding:0 4px 8px;">'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{SURFACE}" style="background-color:{SURFACE};border:1px solid {RULE};border-radius:12px;">'
                f'<tr><td bgcolor="{SURFACE}" style="padding:12px;">'
                f'<div style="font-size:12px;color:{INK2};">{label}</div>'
                f'<div style="margin:2px 0 6px;font-size:22px;font-weight:600;color:{INK};">{html.escape(value.display)}</div>'
                f"{chip(wow, key)}"
                f'<div style="margin-top:6px;font-size:11px;color:{INK2};">vs 4-wk avg {html.escape(vs4w)} · vs last year {html.escape(yoy4)}</div>'
                + (
                    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;"><tr>{sparks}</tr></table>'
                    if series
                    else ""
                )
                + "</td></tr></table></td>"
            )
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
        md += [*(f"- {x}" for x in others), ""]
        page += [
            (
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0 0;">'
                f"<tr>{tiles[0]}{tiles[1]}</tr><tr>{tiles[2]}{tiles[3]}</tr></table>"
            ),
            *(
                f'<p style="margin:2px 0 6px;font-size:13px;color:{MUTED};">{html.escape(x)}</p>'
                for x in others
            ),
            '<div style="height:12px;"></div>',
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
        for title, prefix in [
            ("Top products", "product"),
            ("Top countries", "country"),
        ]:
            rows = [
                by_key[f"{prefix}_{i}_revenue"]
                for i in range(1, 6)
                if by_key[f"{prefix}_{i}_revenue"].value is not None
            ]
            if not rows:
                continue
            first = rows[0].value or 1
            md += [
                f"## {title}",
                "",
                *(
                    f'{i}. "{f.label}" {f.display} ({share(f)}%)'
                    + (" ✕ cancelled" if f.id in week.cancelled_products else "")
                    for i, f in enumerate(rows, 1)
                ),
                "",
            ]
            page.append(f'<h2 style="{SECTION}">{title}</h2>')
            page.append(
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                + "".join(
                    f'<tr><td bgcolor="{CARD}" width="44%" style="padding:6px 8px 6px 0;border-bottom:1px solid {RULE};font-size:14px;color:{INK};">{html.escape(f.label)}'
                    + (
                        f' <span style="color:{RED};white-space:nowrap;">✕ cancelled</span>'
                        if f.id in week.cancelled_products
                        else ""
                    )
                    + "</td>"
                    f'<td bgcolor="{CARD}" width="30%" style="padding:6px 8px 6px 0;border-bottom:1px solid {RULE};">{bar((f.value or 0) / first, AMBER if i == 0 else MUTED)}</td>'
                    f'<td align="right" bgcolor="{CARD}" style="padding:6px 8px 6px 0;border-bottom:1px solid {RULE};font-size:14px;color:{INK};white-space:nowrap;">{html.escape(f.display)}</td>'
                    f'<td align="right" bgcolor="{CARD}" style="padding:6px 0;border-bottom:1px solid {RULE};font-size:12px;color:{MUTED};white-space:nowrap;">{share(f)}%</td></tr>'
                    for i, f in enumerate(rows)
                )
                + "</table>"
            )
            if prefix == "country":
                split = f"{rows[0].label} {share(rows[0])}% · rest of world {100 - share(rows[0])}%"
                md += [split, ""]
                page.append(
                    f'<p style="margin:8px 0 0;font-size:13px;color:{INK2};">{html.escape(split)}</p>'
                )
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
                f'<p style="{SMALL}margin:0 0 4px;"><span style="font-family:{MONO};">{i}</span> {html.escape(figures[i].label)}: {html.escape(figures[i].display)} — {html.escape(figures[i].source)}</p>'
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
        cell = f"padding:4px 6px 4px 0;border-top:1px solid {RULE};vertical-align:top;font-size:11px;line-height:1.4;color:{INK2};"
        page += [
            f'<details><summary style="{SECTION}cursor:pointer;">All figures ({len(shown)})</summary>',
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">',
            *(
                f'<tr><td bgcolor="{CARD}" style="{cell}font-family:{MONO};color:{MUTED};">{f.id}</td><td bgcolor="{CARD}" style="{cell}">{html.escape(f.label)}</td>'
                f'<td bgcolor="{CARD}" style="{cell}white-space:nowrap;">{html.escape(f.display)}</td><td bgcolor="{CARD}" style="{cell}">{html.escape(f.source)}</td></tr>'
                for f in shown
            ),
            "</table></details>",
        ]
    md += ["---", "", ATTRIBUTION, ""]
    page.append(
        f'<p style="{SMALL}margin:28px 0 0;padding-top:12px;border-top:1px solid {RULE};">'
        + html.escape(ATTRIBUTION)
        + "</p>"
    )
    body = "\n".join(page).replace("[", "&#91;")
    return (
        "\n".join(md),
        (
            "<!DOCTYPE html>\n"
            '<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(subject(week))}</title></head>\n"
            f'<body bgcolor="{CARD}" style="margin:0;padding:0;background-color:{CARD};font-family:{SANS};color:{INK};">\n'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{CARD}" style="background-color:{CARD};"><tr><td align="center" bgcolor="{CARD}" style="padding:20px 10px;background-color:{CARD};background-image:linear-gradient(160deg,#141414 0%,#0B1710 100%);">\n'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{CARD}" style="max-width:680px;background-color:{CARD};border:1px solid {RULE};border-radius:12px;"><tr><td align="left" bgcolor="{CARD}" style="padding:26px 22px;background-color:{CARD};font-family:{SANS};color:{INK};">\n'
            f"{body}\n"
            "</td></tr></table>\n</td></tr></table>\n</body></html>\n"
        ),
    )
