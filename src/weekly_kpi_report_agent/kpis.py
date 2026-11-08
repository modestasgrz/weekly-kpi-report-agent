from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pandas as pd
from pydantic import BaseModel

from weekly_kpi_report_agent.data import PRODUCT_CODE
from weekly_kpi_report_agent.models import Cause, Figure

MAX_LABEL = 100
ANOMALY_PCT = Decimal("25.0")
LARGE_CANCEL_SHARE = 0.25
MATCH_DAYS = 14
HISTORY_KEYS = ["revenue", "orders", "aov", "customers"]
COMPARED = ["revenue", "orders", "aov", "units", "customers"]
DQ_BUCKETS = ["duplicate", "cancellation", "adjustment", "non_product", "non_positive"]
DQ_KEYS = [
    "duplicate_lines_removed",
    "cancellation_lines",
    "adjustment_lines",
    "non_product_lines",
    "non_positive_lines",
]


class WeekStats(BaseModel):
    lines: int
    revenue: float
    orders: int
    units: int
    customers: int


def rounded(value: float, places: str) -> Decimal:
    """ROUND_HALF_UP on the intended value: the float is first snapped to 9 decimals, so 538.3249999… (538.325) rounds up."""
    return (
        Decimal(value)
        .quantize(Decimal("1e-9"), ROUND_HALF_EVEN)
        .quantize(Decimal(places), ROUND_HALF_UP)
    )


def grouped(value: float | Decimal) -> str:
    """Thousands separated by a narrow no-break space (DEC-06), never a comma."""
    return f"{value:,}".replace(",", "\u202f")


def money(value: float) -> str:
    return f"£{grouped(rounded(value, '1') + 0)}"


def count(value: float) -> str:
    return grouped(int(value))


def change(value: float) -> str:
    r = rounded(value, "0.1")
    return f"{'-' if r < 0 else '+'}{abs(r)}%"


def window(df: pd.DataFrame, start: date) -> pd.DataFrame:
    begin = datetime.combine(start, datetime.min.time())
    return df[
        (df["InvoiceDate"] >= begin) & (df["InvoiceDate"] < begin + timedelta(days=7))
    ]


def stats(week: pd.DataFrame) -> WeekStats:
    products = week[week["bucket"] == "product"]
    return WeekStats(
        lines=len(products),
        revenue=float(products["revenue"].sum()),
        orders=products["Invoice"].nunique(),
        units=int(products["Quantity"].sum()),
        customers=products["Customer ID"].nunique(),
    )


def aov(s: WeekStats) -> float | None:
    return s.revenue / s.orders if s.orders else None


def ranked(products: pd.DataFrame, by: str) -> list[tuple[str, float, int, str]]:
    """(label, revenue, lines, key) top 5, revenue desc then label asc."""
    rows: list[tuple[str, float, int, str]] = []
    for key, group in products.groupby(by):
        label = (
            str(key)
            if by == "Country"
            else str(group["Description"].value_counts().sort_index().idxmax())
        )
        rows.append(
            (label[:MAX_LABEL], float(group["revenue"].sum()), len(group), str(key))
        )
    rows.sort(key=lambda r: (-round(r[1], 6), r[0]))
    return rows[:5]


def week_lines(df: pd.DataFrame, start: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(product lines by revenue desc then time, product-code cancellation lines by value desc then time) of the week."""
    week = window(df, start)
    products = week[week["bucket"] == "product"].sort_values(
        ["revenue", "InvoiceDate"], ascending=[False, True], kind="stable"
    )
    cancels = week[
        (week["bucket"] == "cancellation") & week["StockCode"].str.match(PRODUCT_CODE)
    ].sort_values(["revenue", "InvoiceDate"], kind="stable")
    return products, cancels


def matching(df: pd.DataFrame, line: pd.Series, cancellations: bool) -> pd.DataFrame:
    """DEC-22 matches of `line`: its cancellations (cancellations=True) or the orders it cancels, nearest first."""
    if pd.isna(line["Customer ID"]):
        return df.iloc[0:0]
    at = line["InvoiceDate"]
    span = timedelta(days=MATCH_DAYS)
    same = df[
        (df["StockCode"] == line["StockCode"])
        & (df["Customer ID"] == line["Customer ID"])
        & (df["Quantity"] == -line["Quantity"])
    ]
    if cancellations:
        found = same[
            (same["bucket"] == "cancellation")
            & (same["InvoiceDate"] >= at)
            & (same["InvoiceDate"] <= at + span)
        ]
        nearest: pd.DataFrame = found.sort_values("InvoiceDate", kind="stable")
        return nearest
    found = same[
        (same["bucket"] == "product")
        & (same["InvoiceDate"] <= at)
        & (same["InvoiceDate"] >= at - span)
    ]
    latest: pd.DataFrame = found.sort_values(
        "InvoiceDate", ascending=False, kind="stable"
    )
    return latest


def context(
    df: pd.DataFrame, start: date, figures: list[Figure], large_cancellations: bool
) -> tuple[dict[str, list[float]], Cause | None, list[str]]:
    """DEC-22 history (12 weeks, oldest first), cause and cancelled top products of the week."""
    weeks = [
        stats(window(df, start - timedelta(days=7 * i))) for i in range(11, -1, -1)
    ]
    history = {
        "revenue": [s.revenue for s in weeks],
        "orders": [float(s.orders) for s in weeks],
        "aov": [aov(s) or 0.0 for s in weeks],
        "customers": [float(s.customers) for s in weeks],
    }
    by_key = {f.key: f for f in figures}
    products, cancels = week_lines(df, start)
    cause: Cause | None = None
    share = by_key["top_line_share"].value
    if (
        share is not None
        and share > 25.0
        and len(products) >= 2
        and products["revenue"].iloc[0] >= 10 * products["revenue"].iloc[1]
    ):
        top = products.iloc[0]
        cancelled = matching(df, top, cancellations=True)
        cause = Cause(
            product=str(top["Description"])[:MAX_LABEL],
            invoice=str(top["Invoice"]),
            cancel_invoice=str(cancelled["Invoice"].iloc[0])
            if len(cancelled)
            else None,
            rule="top_line",
        )
    elif large_cancellations and (by_key["top_cancel_share"].value or 0) > 50.0:
        top = cancels.iloc[0]
        order = matching(df, top, cancellations=False)
        cause = Cause(
            product=str(top["Description"])[:MAX_LABEL],
            invoice=str(order["Invoice"].iloc[0] if len(order) else top["Invoice"]),
            cancel_invoice=str(top["Invoice"]),
            rule="top_cancel",
        )
    hit: list[str] = []
    for i, (_, revenue, _, code) in enumerate(ranked(products, "StockCode"), 26):
        mine = cancels[cancels["StockCode"] == code]
        matched = -sum(
            float(row["revenue"])
            for _, row in mine.iterrows()
            if len(matching(df, row, cancellations=False))
        )
        if revenue > 0 and matched >= 0.5 * revenue:
            hit.append(f"F{i}")
    return history, cause, hit


def compute_week(
    df: pd.DataFrame, start: date, file_name: str
) -> tuple[list[Figure], list[str]]:
    """The 52 figures of DEC-05/DEC-22 for the ISO week starting `start`, plus the anomaly keys of DEC-04."""
    end = start + timedelta(days=6)
    rng = f"{start}..{end}"
    week = window(df, start)
    products = week[week["bucket"] == "product"]
    cur = stats(week)
    prev = stats(window(df, start - timedelta(days=7)))
    last4 = [stats(window(df, start - timedelta(days=7 * i))) for i in range(1, 5)]
    iso_year, iso_week, _ = start.isocalendar()
    try:
        yoy_start: date | None = date.fromisocalendar(iso_year - 1, iso_week, 1)
    except ValueError:
        yoy_start = None
    yoy = stats(window(df, yoy_start)) if yoy_start else None

    first_seen = (
        df[(df["bucket"] == "product") & df["Customer ID"].notna()]
        .groupby("Customer ID")["InvoiceDate"]
        .min()
    )
    week_customers = set(products["Customer ID"].dropna())
    begin = datetime.combine(start, datetime.min.time())
    new = sum(
        1 for c in week_customers if begin <= first_seen[c] < begin + timedelta(days=7)
    )
    cancels = week[week["bucket"] == "cancellation"]["Invoice"].nunique()
    denominator = cur.orders + cancels

    figures: list[Figure] = []

    def add(
        key: str, label: str, value: float | None, display: str, source: str
    ) -> None:
        figures.append(
            Figure(
                id=f"F{len(figures) + 1}",
                key=key,
                label=label,
                value=value,
                display=display if value is not None else "n/a",
                source=source if value is not None else "",
            )
        )

    lines = f"{grouped(cur.lines)} product lines, {rng}, {file_name}"
    add(
        "week_start",
        "Week start (Monday)",
        float(start.strftime("%Y%m%d")),
        str(start),
        f"ISO week {iso_week} of {iso_year}, Monday..Sunday, {file_name}",
    )
    add(
        "week_end",
        "Week end (Sunday)",
        float(end.strftime("%Y%m%d")),
        str(end),
        f"ISO week {iso_week} of {iso_year}, Monday..Sunday, {file_name}",
    )
    week_aov = aov(cur)
    add(
        "revenue",
        "Product revenue (GBP)",
        cur.revenue,
        money(cur.revenue),
        f"sum(Quantity×Price) over {lines}",
    )
    add(
        "orders",
        "Orders",
        cur.orders,
        count(cur.orders),
        f"count of distinct Invoice over {lines}",
    )
    add(
        "aov",
        "Average order value (GBP)",
        week_aov,
        f"£{grouped(rounded(week_aov or 0, '0.01'))}",
        f"revenue / orders over {lines}",
    )
    add(
        "units",
        "Units sold",
        cur.units,
        count(cur.units),
        f"sum(Quantity) over {lines}",
    )
    add(
        "customers",
        "Customers",
        cur.customers,
        count(cur.customers),
        f"count of distinct non-empty Customer ID over {lines}",
    )
    add(
        "new_customers",
        "New customers",
        new,
        count(new),
        f"customers whose first product line in the dataset is in {rng}, {file_name}",
    )
    add(
        "returning_customers",
        "Returning customers",
        cur.customers - new,
        count(cur.customers - new),
        f"customers − new customers, {rng}, {file_name}",
    )
    rate = 100 * cancels / denominator if denominator else None
    add(
        "cancellation_rate",
        "Cancellation rate",
        rate,
        f"{rounded(rate or 0, '0.1')}%",
        f"{cancels} cancellation invoices / ({cur.orders} orders + {cancels} cancellation invoices), {rng}, {file_name}",
    )

    four_values = {
        "revenue": sum(s.revenue for s in last4) / 4,
        "orders": sum(s.orders for s in last4) / 4,
        "aov": sum(s.revenue for s in last4) / orders4
        if (orders4 := sum(s.orders for s in last4))
        else None,
        "units": sum(s.units for s in last4) / 4,
        "customers": sum(s.customers for s in last4) / 4,
    }
    current = {
        "revenue": cur.revenue,
        "orders": cur.orders,
        "aov": week_aov,
        "units": cur.units,
        "customers": cur.customers,
    }
    bases = {
        "wow": (
            {k: (aov(prev) if k == "aov" else getattr(prev, k)) for k in COMPARED},
            f"previous week {start - timedelta(days=7)}..{start - timedelta(days=1)}",
        ),
        "vs4w": (
            four_values,
            f"mean of the 4 previous weeks {start - timedelta(days=28)}..{start - timedelta(days=1)}",
        ),
        "yoy": (
            {k: (aov(yoy) if k == "aov" else getattr(yoy, k)) for k in COMPARED}
            if yoy
            else dict.fromkeys(COMPARED),
            f"same ISO week one year earlier {yoy_start}..{yoy_start + timedelta(days=6)}"
            if yoy_start
            else "same ISO week one year earlier",
        ),
    }
    anomalies: list[str] = []
    for kpi in COMPARED:
        for kind in ["wow", "vs4w", "yoy"]:
            values, described = bases[kind]
            base, now = values[kpi], current[kpi]
            delta = (now - base) / base * 100 if base and now is not None else None
            add(
                f"{kpi}_{kind}",
                f"{kpi} change, {kind}",
                delta,
                change(delta or 0),
                f"({kpi} this week − {kpi} of the {described}) / base × 100; base {'n/a' if base is None else grouped(round(base, 2))}, {file_name}",
            )
            if (
                delta is not None
                and kpi in ("revenue", "orders")
                and kind != "yoy"
                and abs(rounded(delta, "0.1")) >= ANOMALY_PCT
            ):
                anomalies.append(f"{kpi}_{kind}")

    for prefix, by in [("product", "StockCode"), ("country", "Country")]:
        top = ranked(products, by)
        for i in range(5):
            if i < len(top):
                label, revenue, n, _ = top[i]
                add(
                    f"{prefix}_{i + 1}_revenue",
                    label,
                    revenue,
                    money(revenue),
                    f"sum(Quantity×Price) of {label} over {grouped(n)} product lines, {rng}, {file_name}",
                )
            else:
                add(f"{prefix}_{i + 1}_revenue", "", None, "", "")

    for key, bucket in zip(DQ_KEYS, DQ_BUCKETS, strict=True):
        n = int((week["bucket"] == bucket).sum())
        add(
            key,
            key.replace("_", " "),
            n,
            count(n),
            f"lines in {rng} classified as {bucket} by the cleaning rules (DEC-03), {file_name}",
        )
    missing_customer = int(products["Customer ID"].isna().sum())
    add(
        "lines_without_customer_id",
        "product lines without customer id",
        missing_customer,
        count(missing_customer),
        f"product lines with empty Customer ID, {rng}, {file_name}",
    )
    add(
        "product_lines",
        "product lines",
        cur.lines,
        count(cur.lines),
        f"lines in {rng} kept after the cleaning rules (DEC-03), {file_name}",
    )
    cancelled = week[
        (week["bucket"] == "cancellation") & week["StockCode"].str.match(PRODUCT_CODE)
    ]
    cancelled_value = abs(float(cancelled["revenue"].sum()))
    add(
        "cancelled_value",
        "Cancelled product value (GBP)",
        cancelled_value,
        money(cancelled_value),
        f"−sum(Quantity×Price) over {grouped(len(cancelled))} product cancellation lines, {rng}, {file_name}",
    )
    net = cur.revenue - cancelled_value
    add(
        "net_revenue",
        "Revenue after product cancellations (GBP)",
        net,
        money(net),
        f"product revenue (F3) − cancelled product value (F43), {rng}, {file_name}",
    )
    ordered, cancel_lines = week_lines(df, start)
    big = ordered.iloc[0] if len(ordered) else None
    top_revenue = float(big["revenue"]) if big is not None else None
    where = (
        f"invoice {big['Invoice']} at {big['InvoiceDate']:%Y-%m-%d %H:%M}, {file_name}"
        if big is not None
        else ""
    )
    add(
        "top_line_revenue",
        str(big["Description"])[:MAX_LABEL] if big is not None else "",
        top_revenue,
        money(top_revenue or 0),
        f"largest single product line: Quantity×Price, {where}",
    )
    add(
        "top_line_quantity",
        "Units on the largest product line",
        float(big["Quantity"]) if big is not None else None,
        count(big["Quantity"] if big is not None else 0),
        f"Quantity of the largest product line, {where}",
    )
    share = (
        100 * top_revenue / cur.revenue
        if top_revenue is not None and cur.revenue
        else None
    )
    add(
        "top_line_share",
        "Largest product line, share of revenue",
        share,
        f"{rounded(share or 0, '0.1')}%",
        f"largest product line / product revenue (F45 / F3), {rng}, {file_name}",
    )
    cancelled_by = matching(df, big, cancellations=True) if big is not None else None
    minutes = (
        (cancelled_by["InvoiceDate"].iloc[0] - big["InvoiceDate"]).total_seconds() // 60
        if big is not None and cancelled_by is not None and len(cancelled_by)
        else None
    )
    add(
        "top_line_cancel_minutes",
        "Minutes until the largest product line was cancelled",
        minutes,
        count(minutes or 0),
        f"from invoice {big['Invoice'] if big is not None else ''} to cancellation "
        f"{cancelled_by['Invoice'].iloc[0] if minutes is not None and cancelled_by is not None else ''} "
        f"(same StockCode, customer and quantity, within {MATCH_DAYS} days), {file_name}",
    )
    without = cur.revenue - top_revenue if top_revenue is not None else None
    add(
        "revenue_excl_top_line",
        "Revenue without the largest product line (GBP)",
        without,
        money(without or 0),
        f"product revenue (F3) − largest product line (F45), {rng}, {file_name}",
    )
    without_wow = (
        (without - prev.revenue) / prev.revenue * 100
        if without is not None and prev.revenue
        else None
    )
    add(
        "revenue_excl_top_line_wow",
        "revenue without the largest line, change, wow",
        without_wow,
        change(without_wow or 0),
        f"(F49 − revenue of the previous week {start - timedelta(days=7)}..{start - timedelta(days=1)}) / base × 100; base {grouped(round(prev.revenue, 2))}, {file_name}",
    )
    top_cancel = cancel_lines.iloc[0] if len(cancel_lines) else None
    cancel_value = -float(top_cancel["revenue"]) if top_cancel is not None else None
    add(
        "top_cancel_value",
        str(top_cancel["Description"])[:MAX_LABEL] if top_cancel is not None else "",
        cancel_value,
        money(cancel_value or 0),
        f"largest product cancellation line: −Quantity×Price, invoice {top_cancel['Invoice'] if top_cancel is not None else ''}, {rng}, {file_name}",
    )
    cancel_share = (
        100 * cancel_value / cancelled_value
        if cancel_value is not None and cancelled_value
        else None
    )
    add(
        "top_cancel_share",
        "Largest product cancellation, share of cancelled value",
        cancel_share,
        f"{rounded(cancel_share or 0, '0.1')}%",
        f"largest product cancellation line / cancelled product value (F51 / F43), {rng}, {file_name}",
    )
    return figures, anomalies
