"""QA round 4: DEC-22 figures/cause/history, DEC-19 round-4 layout, DEC-21 --data, DEC-17 F50."""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from edge_support import FakeLLM, cleaned, install, narrative, write_book

from weekly_kpi_report_agent.checker import check_narrative
from weekly_kpi_report_agent.cli import main
from weekly_kpi_report_agent.models import Figure, WeekReport
from weekly_kpi_report_agent.pipeline import assess
from weekly_kpi_report_agent.report import look_at_this, render

NB = " "
START = date(2011, 11, 28)
MON = datetime(2011, 11, 28)
UK = "United Kingdom"
NAN = float("nan")
AMBER = "#E8A83C"
RED = "#F08A7E"
GREYS = {"#dccfba", "#8a857b"}
MUTED = "#8a857b"
STRICT_RAISE = RuntimeError("the model must not be called")
FIGURE_KEYS_R4 = [
    "top_line_revenue",
    "top_line_quantity",
    "top_line_share",
    "top_line_cancel_minutes",
    "revenue_excl_top_line",
    "revenue_excl_top_line_wow",
    "top_cancel_value",
    "top_cancel_share",
]
CHIP = re.compile(
    r'<span style="display:inline-block;padding:2px 8px;border:1px solid (#[0-9A-Fa-f]{6});border-radius:10px;font-size:\d+px;line-height:1\.5;color:#[0-9A-Fa-f]{6};">(.*?)</span>'
)
SPARK = re.compile(
    r'<td height="(\d+)" bgcolor="(#[0-9A-Fa-f]{6})" style="height:(\d+)px;font-size:0;line-height:0;background-color:#[0-9A-Fa-f]{6};">'
)
BARS = re.compile(r'<td width="(\d+)%" height="8" bgcolor="(#[0-9A-Fa-f]{6})"')
Row = tuple[Any, ...]


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def t(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return MON + timedelta(days=days, hours=hours, minutes=minutes)


def row(
    inv: str,
    code: str,
    desc: str,
    qty: int,
    when: datetime,
    price: float,
    cust: float,
    country: str = UK,
) -> Row:
    return (inv, code, desc, qty, when, price, cust, country)


TOP = row("100", "10002", "BBB", 40, t(1, 9), 25.0, 18287.0, "France")
FILL = row("101", "10001", "AAA", 5, t(2, 10), 10.0, 17850.0)
END = row("109", "POST", "POSTAGE", 1, t(6, 12), 18.0, 12583.0)


def cancel_of_top(delta: timedelta, **over: Any) -> Row:
    fields: dict[str, Any] = {
        "inv": "C200",
        "code": "10002",
        "desc": "BBB",
        "qty": -40,
        "price": 25.0,
        "cust": 18287.0,
        "country": "France",
    }
    fields.update(over)
    return row(when=TOP[4] + delta, **fields)


# S1: one big order (45 min to cancel), a second cancellation with no order, previous week 200.
S1: list[Row] = [
    row("P1", "10001", "AAA", 20, t(-6, 10), 10.0, 16321.0),
    TOP,
    FILL,
    row("102", "10003", "CCC", 5, t(3, 10), 10.0, 14911.0),
    cancel_of_top(timedelta(minutes=45), inv="C103"),
    row("C104", "10001", "AAA", -2, t(3, 11), 10.0, 13047.0),
    END,
]
S1_NO_CANCEL: list[Row] = [r for r in S1 if not r[0].startswith("C")]


def build(rows: list[Row], start: date = START) -> WeekReport:
    return assess(cleaned(rows), start, "f.xlsx")


def keyed(week: WeekReport) -> dict[str, Figure]:
    return {f.key: f for f in week.figures}


def page(week: WeekReport) -> str:
    return render(week, None, [])[1]


def chips(html: str) -> list[tuple[str, str]]:
    return CHIP.findall(html)


def hero(html: str) -> str:
    start = html.index('<div style="margin:0 0 18px;">')
    rest = html[start:]
    return rest[: min(rest.index("<table"), rest.index("<h2"))]


def card(html: str) -> str:
    return html.split("What changed", 1)[1].split("Look at this", 1)[0]


def tiles(html: str) -> list[str]:
    parts = html.split('<td width="50%" valign="top"')[1:]
    assert len(parts) == 4
    return parts


def weekly(values: dict[int, float], customer: float = 1.0) -> list[Row]:
    """One single-line order per listed week offset (0 = oldest of the 12 weeks, 11 = the report week)."""
    return [
        row(
            f"W{i}",
            "10001",
            "AAA",
            1,
            t(-7 * (11 - i), 10),
            v,
            customer,
        )
        for i, v in values.items()
    ]


# ---------------------------------------------------------------- matching rule


MATCH_CASES = [
    pytest.param({"delta": timedelta(0)}, 0, id="same-moment"),
    pytest.param({"delta": timedelta(minutes=45)}, 45, id="45-min"),
    pytest.param({"delta": timedelta(days=14)}, 14 * 1440, id="exactly-14-days"),
    pytest.param({"delta": timedelta(days=14, minutes=1)}, None, id="14-days-1-min"),
    pytest.param({"delta": timedelta(days=15)}, None, id="15-days"),
    pytest.param({"delta": timedelta(minutes=-1)}, None, id="before-the-order"),
    pytest.param(
        {"delta": timedelta(minutes=5), "code": "10001"}, None, id="other-code"
    ),
    pytest.param(
        {"delta": timedelta(minutes=5), "cust": 99999.0}, None, id="other-customer"
    ),
    pytest.param({"delta": timedelta(minutes=5), "qty": -39}, None, id="partial-qty"),
    pytest.param({"delta": timedelta(minutes=5), "qty": -41}, None, id="larger-qty"),
    pytest.param({"delta": timedelta(minutes=5), "price": 1.0}, 5, id="price-ignored"),
]


@pytest.mark.parametrize(("over", "minutes"), MATCH_CASES)
def test_matching_rule_on_f48_and_cause(
    over: dict[str, Any], minutes: int | None
) -> None:
    delta = over.pop("delta")
    week = build([TOP, FILL, END, cancel_of_top(delta, **over)])
    f = keyed(week)["top_line_cancel_minutes"]
    assert week.cause is not None and week.cause.rule == "top_line"
    if minutes is None:
        assert (f.value, f.display, f.source) == (None, "n/a", "")
        assert week.cause.cancel_invoice is None
    else:
        assert f.value == minutes
        assert f.display == f"{minutes:,}".replace(",", NB)
        assert week.cause.cancel_invoice == "C200"


def test_nan_customer_never_matches() -> None:
    order = row("100", "10002", "BBB", 40, t(1, 9), 25.0, NAN)
    cancel = row("C200", "10002", "BBB", -40, t(1, 10), 25.0, NAN)
    week = build([order, FILL, END, cancel])
    assert keyed(week)["top_line_cancel_minutes"].value is None
    assert week.cause is not None and week.cause.cancel_invoice is None
    assert week.cancelled_products == []


def test_earliest_of_several_matching_cancellations_wins() -> None:
    week = build(
        [
            TOP,
            FILL,
            END,
            cancel_of_top(timedelta(minutes=90), inv="C300"),
            cancel_of_top(timedelta(minutes=30), inv="C301"),
        ]
    )
    assert keyed(week)["top_line_cancel_minutes"].value == 30
    assert week.cause is not None and week.cause.cancel_invoice == "C301"


def test_cancellation_may_fall_in_a_later_week() -> None:
    week = build([TOP, FILL, END, cancel_of_top(timedelta(days=9))])
    assert keyed(week)["top_line_cancel_minutes"].value == 9 * 1440
    assert week.cancelled_products == []


# ------------------------------------------------------------------ F45-F52


def test_s1_round4_figures() -> None:
    week = build(S1)
    by_key = keyed(week)
    assert [f.id for f in week.figures] == [f"F{i}" for i in range(1, 53)]
    assert [f.key for f in week.figures[44:]] == FIGURE_KEYS_R4
    shown = {k: by_key[k].display for k in FIGURE_KEYS_R4}
    assert shown == {
        "top_line_revenue": f"£1{NB}000",
        "top_line_quantity": "40",
        "top_line_share": "90.9%",
        "top_line_cancel_minutes": "45",
        "revenue_excl_top_line": "£100",
        "revenue_excl_top_line_wow": "-50.0%",
        "top_cancel_value": f"£1{NB}000",
        "top_cancel_share": "98.0%",
    }
    assert by_key["top_line_revenue"].label == "BBB"
    assert by_key["top_cancel_value"].label == "BBB"
    assert by_key["revenue"].display == f"£1{NB}100"
    assert by_key["cancelled_value"].display == f"£1{NB}020"
    assert by_key["top_line_revenue"].value == 1000.0
    assert by_key["top_line_quantity"].value == 40.0
    assert by_key["revenue_excl_top_line_wow"].value == pytest.approx(-50.0)
    assert by_key["top_cancel_share"].value == pytest.approx(100 * 1000 / 1020)
    assert "invoice 100" in by_key["top_line_revenue"].source
    assert "invoice C103" in by_key["top_cancel_value"].source
    assert "C103" in by_key["top_line_cancel_minutes"].source


def test_s1_context_fields() -> None:
    week = build(S1)
    assert week.cause is not None
    assert week.cause.model_dump() == {
        "product": "BBB",
        "invoice": "100",
        "cancel_invoice": "C103",
        "rule": "top_line",
    }
    assert week.cancelled_products == ["F26"]
    assert week.reasons == [
        f"large cancellations: £1{NB}020 cancelled against £1{NB}100 revenue"
    ]
    assert week.history["revenue"] == [0.0] * 10 + [200.0, 1100.0]
    assert week.history["orders"] == [0.0] * 10 + [1.0, 3.0]
    assert week.history["customers"] == [0.0] * 10 + [1.0, 3.0]
    assert week.history["aov"] == [0.0] * 10 + [200.0, pytest.approx(1100 / 3)]


def test_largest_line_tie_goes_to_the_earliest() -> None:
    later = row("OA", "10001", "AAA", 5, t(3, 10), 100.0, 1.0)
    earlier = row("OB", "10002", "BBB", 5, t(1, 10), 100.0, 2.0)
    by_key = keyed(build([later, earlier]))
    assert by_key["top_line_revenue"].label == "BBB"
    assert "invoice OB at 2011-11-29 10:00" in by_key["top_line_revenue"].source


def test_no_cancellations_makes_f51_f52_na_and_f43_zero() -> None:
    by_key = keyed(build([TOP, FILL, END]))
    assert by_key["cancelled_value"].display == "£0"
    for k in ["top_cancel_value", "top_cancel_share", "top_line_cancel_minutes"]:
        f = by_key[k]
        assert (f.value, f.display, f.source) == (None, "n/a", "")


def test_no_product_lines_makes_f45_to_f50_na() -> None:
    rows = [
        row("P1", "10001", "AAA", 20, t(-6, 10), 10.0, 1.0),
        row("C9", "10001", "AAA", -20, t(2, 10), 10.0, 1.0),
    ]
    week = build(rows)
    by_key = keyed(week)
    assert week.status == "no_data"
    assert by_key["revenue"].display == "£0"
    assert len(week.figures) == 52
    for k in FIGURE_KEYS_R4[:6]:
        f = by_key[k]
        assert (f.value, f.display, f.source) == (None, "n/a", ""), k
    assert by_key["top_cancel_value"].display == "£200"
    assert by_key["top_cancel_share"].display == "100.0%"
    assert week.cause is None
    assert week.cancelled_products == []
    assert week.history["revenue"] == [0.0] * 10 + [200.0, 0.0]
    assert "Look at this" not in page(week)


def test_empty_week_with_no_lines_at_all() -> None:
    week = build(
        [row("P1", "10001", "AAA", 20, t(-6, 10), 10.0, 1.0)], date(2011, 12, 5)
    )
    by_key = keyed(week)
    assert week.status == "no_data"
    assert by_key["top_cancel_share"].display == "n/a"
    assert by_key["top_line_share"].display == "n/a"
    assert all(len(v) == 12 for v in week.history.values())


def test_single_product_line_has_no_cause() -> None:
    week = build([TOP, END])
    assert keyed(week)["top_line_share"].display == "100.0%"
    assert keyed(week)["revenue_excl_top_line"].display == "£0"
    assert week.cause is None


# ----------------------------------------------------------------- cause rules


def lines_of(count: int, value: float = 10.0, start: int = 0) -> list[Row]:
    return [
        row(f"F{start + i}", "10001", "AAA", 1, t(2, 10), value, 100.0 + i)
        for i in range(count)
    ]


def top_of(value: float) -> Row:
    return row("T", "10002", "BBB", 1, t(1, 10), value, 7.0)


@pytest.mark.parametrize(
    ("fillers", "share_text", "cause"),
    [
        (30, "25.0%", False),
        (29, "25.6%", True),
    ],
)
def test_top_line_share_must_exceed_25(
    fillers: int, share_text: str, cause: bool
) -> None:
    week = build([top_of(100.0), *lines_of(fillers)])
    assert keyed(week)["top_line_share"].display == share_text
    assert (week.cause is not None) is cause


def test_top_line_needs_ten_times_the_second_line() -> None:
    assert build([top_of(100.0), *lines_of(1, 11.0)]).cause is None
    exactly = build([top_of(100.0), *lines_of(1, 10.0)])
    assert exactly.cause is not None and exactly.cause.rule == "top_line"


def test_top_line_beats_top_cancel() -> None:
    week = build(S1)
    assert keyed(week)["top_cancel_share"].value is not None
    assert week.cause is not None and week.cause.rule == "top_line"


def test_cause_product_is_cut_to_100_chars() -> None:
    rows = [
        row("T", "10002", "X" * 150, 1, t(1, 10), 100.0, 7.0),
        *lines_of(1, 1.0),
    ]
    week = build(rows)
    assert week.cause is not None and week.cause.product == "X" * 100
    assert keyed(week)["top_line_revenue"].label == "X" * 100


def small_week(extra: int = 0) -> list[Row]:
    """4 product lines of 100 (revenue 400): no top_line cause (share 25%, not 10x)."""
    return [
        row(f"S{i}", f"2000{i}", f"D{i}", 1, t(1 + i % 5, 10), 100.0, 100.0 + i)
        for i in range(4 + extra)
    ]


PRIOR = t(-3)


def order_and_cancel(
    qty: int,
    order_when: datetime | None = PRIOR,
    cust_order: float = 90001.0,
    cust_cancel: float = 90001.0,
    order_inv: str = "400",
) -> list[Row]:
    rows = [row("C500", "30001", "CCC", -qty, t(1, 10), 1.0, cust_cancel)]
    if order_when is not None:
        rows.append(row(order_inv, "30001", "CCC", qty, order_when, 1.0, cust_order))
    return rows


@pytest.mark.parametrize(
    ("qty", "large", "cause_rule"),
    [(96, False, None), (100, True, "top_cancel")],
)
def test_top_cancel_only_in_a_large_cancellation_week(
    qty: int, large: bool, cause_rule: str | None
) -> None:
    week = build([*small_week(), *order_and_cancel(qty)])
    assert keyed(week)["top_cancel_share"].display == "100.0%"
    assert any(r.startswith("large cancellations") for r in week.reasons) is large
    assert (week.cause.rule if week.cause else None) == cause_rule


def test_top_cancel_matched_order_invoice() -> None:
    week = build([*small_week(), *order_and_cancel(100)])
    assert week.cause is not None
    assert week.cause.model_dump() == {
        "product": "CCC",
        "invoice": "400",
        "cancel_invoice": "C500",
        "rule": "top_cancel",
    }


@pytest.mark.parametrize(
    ("order_when", "expected_invoice", "fillers"),
    [
        (t(1, 10) - timedelta(days=14), "400", 0),
        (t(1, 10) - timedelta(days=14, minutes=1), "C500", 0),
        (t(1, 10) - timedelta(days=15), "C500", 0),
        (t(1, 11), "C500", -2),
        (None, "C500", 0),
    ],
)
def test_top_cancel_invoice_falls_back_to_the_cancellation(
    order_when: datetime | None, expected_invoice: str, fillers: int
) -> None:
    week = build([*small_week(fillers), *order_and_cancel(100, order_when)])
    assert week.cause is not None and week.cause.rule == "top_cancel"
    assert week.cause.invoice == expected_invoice
    assert week.cause.cancel_invoice == "C500"


def test_top_cancel_picks_the_nearest_earlier_order() -> None:
    rows = [
        *small_week(),
        *order_and_cancel(100, t(-9), order_inv="401"),
        row("402", "30001", "CCC", 100, t(-1, 8), 1.0, 90001.0),
    ]
    week = build(rows)
    assert week.cause is not None and week.cause.invoice == "402"


def test_top_cancel_nan_customer_is_unmatched() -> None:
    rows = [*small_week(), *order_and_cancel(100, cust_order=NAN, cust_cancel=NAN)]
    week = build(rows)
    assert week.cause is not None and week.cause.invoice == "C500"


def test_top_cancel_needs_share_above_50() -> None:
    even = [
        row("C501", "30001", "CCC", -100, t(1, 10), 1.0, 1.0),
        row("C502", "30002", "DDD", -100, t(1, 11), 1.0, 2.0),
    ]
    week = build([*small_week(), *even])
    assert keyed(week)["top_cancel_share"].display == "50.0%"
    assert week.reasons and week.cause is None
    over = [even[0], row("C502", "30002", "DDD", -96, t(1, 11), 1.0, 2.0)]
    week = build([*small_week(), *over])
    assert keyed(week)["top_cancel_share"].display == "51.0%"
    assert week.cause is not None and week.cause.rule == "top_cancel"


# ------------------------------------------------------------ cancelled_products


def pair(qty_a: int, qty_b: int, cancel_qty: int, price_b: float = 10.0) -> list[Row]:
    return [
        row("O1", "10001", "AAA", qty_a, t(1, 9), 10.0, 1.0),
        row("O2", "10001", "AAA", qty_b, t(1, 10), price_b, 2.0),
        row("C1", "10001", "AAA", -cancel_qty, t(2, 9), 10.0, 1.0),
        END,
    ]


def test_cancelled_products_at_exactly_half() -> None:
    assert build(pair(5, 5, 5)).cancelled_products == ["F26"]


def test_cancelled_products_below_half() -> None:
    week = build(pair(5, 3, 5, 17.0))
    assert keyed(week)["revenue"].display == "£101"
    assert week.cancelled_products == []


def test_cancelled_products_ignore_unmatched_cancellations() -> None:
    rows = [
        row("O1", "10001", "AAA", 5, t(1, 9), 10.0, 1.0),
        row("C1", "10001", "AAA", -5, t(2, 9), 10.0, 2.0),
        row("C2", "10001", "AAA", -3, t(2, 9), 10.0, 1.0),
        row("C3", "10001", "AAA", -5, t(2, 9), 10.0, NAN),
    ]
    assert build(rows).cancelled_products == []


def test_cancelled_products_use_the_rank_id() -> None:
    rows = [
        row("O1", "10001", "AAA", 1, t(1, 9), 500.0, 3.0),
        row("O2", "10002", "BBB", 5, t(1, 9), 10.0, 1.0),
        row("C1", "10002", "BBB", -5, t(2, 9), 10.0, 1.0),
    ]
    assert build(rows).cancelled_products == ["F27"]


def test_cancelled_products_matched_order_from_the_previous_week() -> None:
    rows = [
        row("O0", "10002", "BBB", 5, t(-2, 9), 10.0, 1.0),
        row("O1", "10002", "BBB", 5, t(1, 9), 10.0, 2.0),
        row("C1", "10002", "BBB", -5, t(2, 9), 10.0, 1.0),
    ]
    assert build(rows).cancelled_products == ["F26"]


# ---------------------------------------------------------------------- history


def test_history_twelve_values_oldest_first_with_zero_weeks() -> None:
    values = {1: 100.0, 3: 280.0, 5: 50.0, 11: 140.0}
    out = {12: 999.0}
    week = build(weekly(values) + weekly(out))
    assert set(week.history) == {"revenue", "orders", "aov", "customers"}
    assert all(len(v) == 12 for v in week.history.values())
    expected = [values.get(i, 0.0) for i in range(12)]
    assert week.history["revenue"] == expected
    assert week.history["orders"] == [1.0 if i in values else 0.0 for i in range(12)]
    assert week.history["customers"] == week.history["orders"]
    assert week.history["aov"] == expected
    assert week.history["revenue"][-1] == keyed(week)["revenue"].value


def test_history_week_older_than_twelve_is_left_out() -> None:
    week = build(
        weekly({0: 10.0, 11: 20.0})
        + [row("Z", "10001", "AAA", 1, t(-7 * 12, 10), 999.0, 1.0)]
    )
    assert week.history["revenue"][0] == 10.0
    assert 999.0 not in week.history["revenue"]


def test_history_orders_aov_and_customers_per_week() -> None:
    rows = [
        row("1", "10001", "AAA", 1, t(1), 10.0, 1.0),
        row("1", "10002", "BBB", 1, t(1), 30.0, 1.0),
        row("2", "10001", "AAA", 1, t(2), 20.0, 2.0),
        row("3", "10001", "AAA", 1, t(3), 20.0, NAN),
    ]
    week = build(rows)
    assert week.history["orders"][-1] == 3.0
    assert week.history["customers"][-1] == 2.0
    assert week.history["aov"][-1] == pytest.approx(80 / 3)


def test_history_on_a_no_data_week_is_all_zero_for_the_week() -> None:
    week = build([row("P", "10001", "AAA", 1, t(-14, 10), 5.0, 1.0)])
    assert week.status == "no_data"
    assert week.history["revenue"] == [0.0] * 9 + [5.0, 0.0, 0.0]


# ------------------------------------------------------------------ Look at this


def test_look_at_this_cause_with_cancellation_first() -> None:
    lines = look_at_this(build(S1))
    assert lines == ['Check cancellation C103: was "BBB" a lost sale or a mistake?']


def test_look_at_this_cause_without_cancellation_then_stock() -> None:
    week = build(S1_NO_CANCEL)
    assert look_at_this(week) == [
        'Check order 100: "BBB" is 90.9% of revenue',
        f'Keep "BBB" in stock: the top seller at £1{NB}000.',
    ]


def test_look_at_this_negative_anomalies_and_stock_line() -> None:
    prev = [
        row("a1", "10001", "AAA", 10, t(-5, 10), 500.0, 1.0),
        row("a2", "10001", "AAA", 10, t(-4, 10), 500.0, 2.0),
    ]
    now = [row(f"n{i}", "10001", "AAA", 1, t(i, 10), 100.0, 10.0 + i) for i in range(3)]
    week = build([*prev, *now, END])
    assert week.cause is None
    assert {"revenue_wow", "revenue_vs4w"} <= set(week.anomalies)
    by_key = keyed(week)
    assert look_at_this(week) == [
        f"Find out why revenue fell ({by_key['revenue_wow'].display} vs last week)",
        f"Find out why revenue fell ({by_key['revenue_vs4w'].display} vs the 4-week average)",
        f'Keep "AAA" in stock: the top seller at {by_key["product_1_revenue"].display}.',
    ]


def test_look_at_this_ignores_positive_anomalies() -> None:
    week = build(S1_NO_CANCEL)
    assert "revenue_wow" in week.anomalies
    assert not any("Find out why" in x for x in look_at_this(week))


def test_look_at_this_orders_fall_and_units_never() -> None:
    prev = [
        row(f"p{i}", "10001", "AAA", 1, t(-6 + i, 10), 100.0, 1.0 + i) for i in range(4)
    ]
    now = [row("n1", "10001", "AAA", 1, t(1, 10), 400.0, 20.0)]
    week = build([*prev, *now, END])
    assert "orders_wow" in week.anomalies and "revenue_wow" not in week.anomalies
    assert "units_wow" not in week.anomalies
    text = " ".join(look_at_this(week))
    assert "Find out why orders fell (-75.0% vs last week)" in text
    assert "units" not in text


def test_look_at_this_is_capped_at_three_in_order_without_stock() -> None:
    rows = [
        row("P1", "10001", "AAA", 20, t(-6, 10), 500.0, 16321.0),
        row("P2", "10001", "AAA", 20, t(-5, 10), 500.0, 11112.0),
        TOP,
        row("101", "10001", "AAA", 1, t(2, 10), 10.0, 17850.0),
        cancel_of_top(timedelta(minutes=45), inv="C103"),
    ]
    week = build(rows)
    assert any(r.startswith("partial week") for r in week.reasons)
    assert week.cause is not None and week.cause.cancel_invoice == "C103"
    assert {"revenue_wow", "revenue_vs4w"} <= set(week.anomalies)
    lines = look_at_this(week)
    by_key = keyed(week)
    assert len(lines) == 3
    assert lines[0].startswith("Check cancellation C103")
    assert lines[1] == "Re-run this report once the data after 2011-11-30 is in."
    assert (
        lines[2]
        == f"Find out why revenue fell ({by_key['revenue_wow'].display} vs last week)"
    )
    assert not any("in stock" in x for x in lines)


def test_no_stock_line_when_top_seller_was_cancelled() -> None:
    week = build(S1)
    assert week.cancelled_products == ["F26"]
    assert "in stock" not in page(week)
    assert "in stock" not in render(week, None, [])[0]


def test_look_at_this_renders_in_html_and_markdown() -> None:
    week = build(S1)
    md, html = render(week, None, [])
    expected = 'Check cancellation C103: was "BBB" a lost sale or a mistake?'
    assert f"- {expected}" in md
    assert expected.replace('"', "&quot;") in html


# ---------------------------------------------------------------- chip colours


def tile_chips(html: str) -> list[tuple[str, str]]:
    return chips(html)[-4:]


def test_chip_amber_at_plus_one_grey_below() -> None:
    week = build(
        [
            row("p", "10001", "AAA", 1, t(-3, 10), 100.0, 1.0),
            row("n", "10001", "AAA", 1, t(1, 10), 101.0, 1.0),
            END,
        ]
    )
    got = chips(page(week))
    assert len(got) == 5
    assert got[0] == got[1] == (AMBER, "▲ +1.0% vs last week")
    assert got[2] == got[4] and got[2][0] in GREYS and got[2][1] == "+0.0% vs last week"
    assert got[3] == (AMBER, "▲ +1.0% vs last week")


def test_chip_below_one_percent_is_grey_even_when_it_displays_plus_one() -> None:
    week = build(
        [
            row("p", "10001", "AAA", 1, t(-3, 10), 10000.0, 1.0),
            row("n", "10001", "AAA", 1, t(1, 10), 10099.0, 1.0),
            END,
        ]
    )
    assert keyed(week)["revenue_wow"].display == "+1.0%"
    colour, text = chips(page(week))[1]
    assert colour in GREYS and text == "+1.0% vs last week"


@pytest.mark.parametrize(("price", "text"), [(99.0, "▼ -1.0%"), (90.0, "▼ -10.0%")])
def test_chip_small_negative_without_anomaly_is_grey(price: float, text: str) -> None:
    prev = [
        row(f"p{i}", "10001", "AAA", 1, t(-7 * i, 10) - timedelta(days=0), 100.0, 1.0)
        for i in range(1, 5)
    ]
    week = build([*prev, row("n", "10001", "AAA", 1, t(1, 10), price, 1.0), END])
    assert week.anomalies == []
    colour, got = chips(page(week))[1]
    assert colour in GREYS
    assert got == f"{text} vs last week"


def test_chip_red_only_for_a_negative_anomaly() -> None:
    prev = [
        row("a", "10001", "AAA", 1, t(-5, 10), 100.0, 1.0),
        row("b", "10001", "AAA", 1, t(-4, 10), 100.0, 2.0),
    ]
    week = build([*prev, row("n", "10001", "AAA", 1, t(1, 10), 100.0, 3.0), END])
    assert "revenue_wow" in week.anomalies and "orders_wow" in week.anomalies
    rev, orders, aov, customers = tile_chips(page(week))
    assert rev == (RED, "▼ -50.0% vs last week")
    assert orders == (RED, "▼ -50.0% vs last week")
    assert aov[0] in GREYS and aov[1] == "+0.0% vs last week"
    assert customers[0] in GREYS and customers[1] == "▼ -50.0% vs last week"
    assert chips(page(week))[0] == rev


def test_chip_red_when_only_the_four_week_move_is_the_anomaly() -> None:
    values = {10: 100.0, 9: 200.0, 8: 200.0, 7: 200.0, 11: 90.0}
    week = build([*weekly(values), END])
    assert "revenue_vs4w" in week.anomalies and "revenue_wow" not in week.anomalies
    assert tile_chips(page(week))[0] == (RED, "▼ -10.0% vs last week")


def test_chip_positive_anomaly_is_amber_not_red() -> None:
    week = build(S1_NO_CANCEL)
    assert "revenue_wow" in week.anomalies
    assert tile_chips(page(week))[0][0] == AMBER


def test_chip_na_is_grey_no_comparison() -> None:
    week = build([TOP, FILL, END])
    got = chips(page(week))
    assert len(got) == 5
    assert set(got) == {(c, "no comparison") for c in {got[0][0]}}
    assert got[0][0] in GREYS


def test_partial_week_chips_are_all_grey_with_a_label() -> None:
    prev = [
        row("a", "10001", "AAA", 1, t(-5, 10), 100.0, 1.0),
        row("b", "10001", "AAA", 1, t(-4, 10), 100.0, 2.0),
    ]
    week = build([*prev, row("n", "10001", "AAA", 1, t(2, 10), 100.0, 3.0)])
    assert any(r.startswith("partial week") for r in week.reasons)
    assert "revenue_wow" in week.anomalies
    got = chips(page(week))
    assert len(got) == 5
    for colour, text in got:
        assert colour in GREYS
        assert text.endswith(" · partial week, not comparable")
    assert got[1][1] == "▼ -50.0% vs last week · partial week, not comparable"


def test_large_cancellation_hero_has_no_chip_and_shows_net() -> None:
    week = build(S1)
    html = page(week)
    assert len(chips(html)) == 4
    shown = hero(html)
    assert "Revenue after cancellations" in shown
    assert "£80" in shown
    assert f"Booked £1{NB}100" in shown
    order = [
        html.index(x)
        for x in [
            "Revenue after cancellations",
            "£80",
            "Booked",
            "1 order:",
            "Look at this",
            "valign",
        ]
    ]
    assert order == sorted(order)


def test_plain_hero_label_chip_and_last_year() -> None:
    last_year = row("y", "10001", "AAA", 1, datetime(2010, 11, 30, 10), 50.0, 1.0)
    rows = [
        last_year,
        row("p", "10001", "AAA", 1, t(-3, 10), 100.0, 1.0),
        row("n", "10001", "AAA", 1, t(1, 10), 150.0, 1.0),
    ]
    week = build(rows)
    shown = hero(page(week))
    assert ">Revenue</div>" in shown and "Revenue after" not in shown
    assert "£150" in shown and "+50.0% vs last week" in shown
    assert "+200.0% vs last year" in shown
    no_year = hero(page(build([TOP, FILL, END])))
    assert "vs last year" not in no_year


# -------------------------------------------------------------- spark-columns


def test_spark_heights_colours_and_count() -> None:
    values = {1: 100.0, 3: 280.0, 5: 50.0, 11: 140.0}
    html = page(build(weekly(values)))
    assert html.count('valign="bottom"') == 48
    revenue, orders, aov, customers = tiles(html)
    for tile in (revenue, orders, aov, customers):
        assert tile.count('valign="bottom"') == 12
        blocks = SPARK.findall(tile)
        assert len(blocks) == 12
        assert [b[1] for b in blocks] == [MUTED] * 11 + [AMBER]
        assert all(b[0] == b[2] for b in blocks)
    heights = [int(h) for h, _, _ in SPARK.findall(revenue)]
    for i, v in values.items():
        assert heights[i] == int(v / 10), i
    assert max(heights) == 28
    assert all(h >= 1 for h in heights)
    orders_h = [int(h) for h, _, _ in SPARK.findall(orders)]
    assert [h for i, h in enumerate(orders_h) if i in values] == [28] * 4
    assert all(h >= 1 for h in orders_h)


def test_spark_blocks_are_one_pixel_when_the_maximum_is_zero() -> None:
    rows = [
        row(f"W{i}", "10001", "AAA", 1, t(-7 * i, 10), 10.0 + i, NAN) for i in range(6)
    ]
    week = build(rows)
    assert week.history["customers"] == [0.0] * 12
    revenue, _orders, _aov, customers = tiles(page(week))
    blocks = SPARK.findall(customers)
    assert len(blocks) == 12
    assert [b[0] for b in blocks] == ["1"] * 12
    assert [b[1] for b in blocks] == [MUTED] * 11 + [AMBER]
    assert max(int(h) for h, _, _ in SPARK.findall(revenue)) == 28


def test_page_has_valign_bottom_nowhere_else() -> None:
    html = page(build(S1))
    assert html.count('valign="bottom"') == 48
    assert "<sup" not in html and "[F" not in html


def test_render_without_history_does_not_break() -> None:
    week = build(S1)
    week.history = {}
    assert page(week).count('valign="bottom"') == 0


# ----------------------------------------------------------------- cause card


@pytest.mark.parametrize(
    ("minutes", "tail"),
    [
        (1, "1 min later"),
        (119, "119 min later"),
        (121, "1 day later"),
        (130, "1 day later"),
        (2160, "2 days later"),
        (3600, "3 days later"),
        (4320, "3 days later"),
        (10 * 1440, "10 days later"),
    ],
)
def test_cause_card_minutes_then_days(minutes: int, tail: str) -> None:
    week = build([TOP, FILL, END, cancel_of_top(timedelta(minutes=minutes))])
    assert f"1 order: BBB ×40 · £1{NB}000 → cancelled {tail}" in card(page(week))


def test_cause_card_at_exactly_120_minutes_is_still_minutes() -> None:
    week = build([TOP, FILL, END, cancel_of_top(timedelta(minutes=120))])
    assert "→ cancelled 120 min later" in card(page(week))


def test_cause_card_not_cancelled_form() -> None:
    week = build(S1_NO_CANCEL)
    html = page(week)
    assert f"1 order: BBB ×40 · £1{NB}000 = 90.9% of revenue" in card(html)
    assert "cancelled" not in card(html).replace("What changed", "")


def test_cause_card_cancellation_form_has_no_bars() -> None:
    week = build([*small_week(), *order_and_cancel(100)])
    html = page(week)
    shown = card(html)
    assert "1 cancellation: CCC · £100 = 100.0% of cancelled value" in shown
    assert "As booked" not in shown and not BARS.findall(shown)


def test_cause_card_bars_are_proportional_to_the_larger_value() -> None:
    html = page(build(S1))
    shown = card(html)
    assert "As booked" in shown and f"£1{NB}100" in shown
    assert "Without this order" in shown and "£100 (-50.0% vs last week)" in shown
    assert [(int(w), c) for w, c in BARS.findall(shown)] == [(100, MUTED), (9, AMBER)]


def test_no_cause_card_without_cause() -> None:
    week = build([*lines_of(10)])
    assert week.cause is None
    assert "What changed" not in page(week)


def test_cause_card_in_markdown() -> None:
    md = render(build(S1), None, [])[0]
    assert (
        f"**What changed:** 1 order: BBB ×40 · £1{NB}000 → cancelled 45 min later" in md
    )
    assert "✕ cancelled" in md and "✕ cancelled" in page(build(S1))


# ----------------------------------------------------- DEC-17 direction (F50)


def figs(rows: list[Row]) -> list[Figure]:
    return build(rows).figures


def test_f50_direction_words_are_checked() -> None:
    f = figs(S1)
    bad = check_narrative(
        "Revenue without that order rose -50.0% [F50] on last week.", f
    )
    assert [(v.kind, v.token) for v in bad] == [("wrong_direction", "-50.0%")]
    assert (
        check_narrative("Revenue without that order fell -50.0% [F50] on last week.", f)
        == []
    )
    assert check_narrative("Revenue without that order moved -50.0% [F50].", f) == []


def test_f50_positive_with_a_down_word() -> None:
    f = figs(
        [
            row("P", "10001", "AAA", 5, t(-6, 10), 10.0, 1.0),
            top_of(1000.0),
            *lines_of(1, 100.0),
        ]
    )
    by_id = {x.id: x for x in f}
    assert by_id["F50"].display == "+100.0%"
    bad = check_narrative("Without it revenue fell +100.0% [F50].", f)
    assert [(v.kind, v.token) for v in bad] == [("wrong_direction", "+100.0%")]
    assert check_narrative("Without it revenue rose +100.0% [F50].", f) == []


def test_f47_and_f52_are_not_change_figures() -> None:
    f = figs(S1)
    text = "The order was 90.9% [F47] of revenue and it fell 98.0% [F52] of cancelled value."
    assert check_narrative(text, f) == []
    assert check_narrative("It rose 90.9% [F47].", f) == []


def test_new_figures_must_be_cited_with_their_own_marker() -> None:
    f = figs(S1)
    assert (
        check_narrative(
            f"One order of £1{NB}000 [F45] came back 45 [F48] minutes later.", f
        )
        == []
    )
    wrong = check_narrative(f"One order of £1{NB}000 [F51].", f)
    assert wrong == []  # F45 and F51 share the display: either marker is the right text
    off = check_narrative("One order of £100 [F45].", f)
    assert [(v.kind, v.token) for v in off] == [("wrong_reference", "£100")]


# ---------------------------------------------- privacy and run/render --data


def run_args(book: Path, out: Path) -> list[str]:
    return [
        "run",
        "--data",
        str(book),
        "--as-of",
        "2011-12-05",
        "--out",
        str(out),
        "--no-gmail",
    ]


def written(out: Path) -> dict[str, str]:
    return {
        str(p.relative_to(out)): p.read_text() for p in out.rglob("*") if p.is_file()
    }


IDS = ["18287", "17850", "14911", "13047", "12583", "16321"]


def test_no_customer_ids_in_any_output_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = write_book(tmp_path / "f.xlsx", S1)
    llm, _ = install(
        monkeypatch, FakeLLM([narrative("Weekly sales summary", "Figures below.")])
    )
    out = tmp_path / "out"
    assert main(run_args(book, out)) == 2
    folder = out / "2011-11-28"
    assert main(["render", "--from", str(folder), "--data", str(book)]) == 2
    assert (
        main(
            [
                "backfill",
                "--data",
                str(book),
                "--from",
                "2011-11-21",
                "--to",
                "2011-11-28",
                "--out",
                str(tmp_path / "bf"),
            ]
        )
        == 0
    )
    files = {**written(out), **written(tmp_path / "bf")}
    assert {
        "2011-11-28/report.md",
        "2011-11-28/report.html",
        "2011-11-28/figures.json",
        "2011-11-28/narrative.json",
    } <= set(files)
    for name, text in files.items():
        for cid in IDS:
            assert cid not in text, (name, cid)
    assert len(llm.calls) == 1 + 2


def test_render_with_data_recomputes_and_never_calls_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = write_book(tmp_path / "f.xlsx", S1)
    install(monkeypatch, FakeLLM([narrative("Weekly sales summary", "Figures below.")]))
    out = tmp_path / "out"
    assert main(run_args(book, out)) == 2
    folder = out / "2011-11-28"
    original = json.loads((folder / "figures.json").read_text())
    assert original["cause"]["cancel_invoice"] == "C103"

    tampered = json.loads(json.dumps(original))
    tampered["reasons"] = ["bogus"]
    tampered["anomalies"] = ["units_wow"]
    tampered["history"] = {}
    tampered["cause"] = None
    tampered["cancelled_products"] = []
    tampered["figures"][2]["display"] = "£1"
    tampered["figures"][44]["display"] = "£1"
    tampered["figures"] = tampered["figures"][:50]
    (folder / "figures.json").write_text(json.dumps(tampered))
    (folder / "report.html").unlink()

    llm, gmail = install(monkeypatch, FakeLLM([STRICT_RAISE]))
    assert main(["render", "--from", str(folder), "--data", str(book)]) == 2
    assert llm.calls == [] and gmail.calls == []
    assert json.loads((folder / "figures.json").read_text()) == original
    assert (folder / "report.html").exists()


def test_render_with_data_without_narrative_is_figures_only_and_model_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = write_book(tmp_path / "f.xlsx", S1_NO_CANCEL)
    install(monkeypatch, FakeLLM([narrative("Weekly sales summary", "Figures below.")]))
    out = tmp_path / "out"
    assert main(run_args(book, out)) == 0
    folder = out / "2011-11-28"
    (folder / "narrative.json").unlink()
    llm, gmail = install(monkeypatch, FakeLLM([STRICT_RAISE]))
    assert main(["render", "--from", str(folder), "--data", str(book), "--draft"]) == 2
    assert llm.calls == []
    saved = json.loads((folder / "figures.json").read_text())
    assert saved["status"] == "needs_review"
    assert saved["attempts"] == 1
    assert (
        saved["cause"]["rule"] == "top_line"
        and saved["cause"]["cancel_invoice"] is None
    )
    assert len(gmail.calls) == 1
    assert "Narrative withheld" in (folder / "report.md").read_text()


def test_render_with_data_and_a_missing_column_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    book = write_book(tmp_path / "f.xlsx", S1)
    install(monkeypatch, FakeLLM([narrative("Weekly sales summary", "Figures below.")]))
    out = tmp_path / "out"
    assert main(run_args(book, out)) == 2
    import pandas as pd

    bad = tmp_path / "bad.xlsx"
    pd.read_excel(book).drop(columns=["Price"]).to_excel(bad, index=False)
    before = (out / "2011-11-28" / "figures.json").read_text()
    llm, _ = install(monkeypatch, FakeLLM([STRICT_RAISE]))
    assert main(["render", "--from", str(out / "2011-11-28"), "--data", str(bad)]) == 1
    assert "missing columns: Price" in capsys.readouterr().err
    assert (out / "2011-11-28" / "figures.json").read_text() == before
    assert llm.calls == []


def test_older_figures_json_without_data_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    book = write_book(tmp_path / "f.xlsx", S1)
    install(monkeypatch, FakeLLM([narrative("Weekly sales summary", "Figures below.")]))
    out = tmp_path / "out"
    assert main(run_args(book, out)) == 2
    folder = out / "2011-11-28"
    data = json.loads((folder / "figures.json").read_text())
    data["figures"] = data["figures"][:44]
    for key in ["history", "cause", "cancelled_products"]:
        del data[key]
    (folder / "figures.json").write_text(json.dumps(data))
    assert main(["render", "--from", str(folder)]) == 1
    assert "written by an older version" in capsys.readouterr().err


def test_render_with_data_keeps_saved_rejected_sentences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = write_book(tmp_path / "f.xlsx", S1)
    bad = narrative("Weekly sales summary", "Revenue reached £1 [F3] this week.")
    install(monkeypatch, FakeLLM([bad, bad, bad]))
    out = tmp_path / "out"
    main(run_args(book, out))
    folder = out / "2011-11-28"
    saved = json.loads((folder / "figures.json").read_text())
    assert saved["violations"]
    llm, _ = install(monkeypatch, FakeLLM([STRICT_RAISE]))
    assert main(["render", "--from", str(folder), "--data", str(book)]) == 2
    assert llm.calls == []
    after = json.loads((folder / "figures.json").read_text())
    assert after["violations"] == saved["violations"]
    page = (folder / "report.html").read_text()
    assert "Rejected sentences" in page
    assert "Narrative withheld: the text failed the number check." in page
