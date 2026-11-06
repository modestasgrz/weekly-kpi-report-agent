from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pandas as pd
from pydantic import BaseModel

from weekly_kpi_report_agent.data import PRODUCT_CODE
from weekly_kpi_report_agent.models import Figure

MAX_LABEL = 100
ANOMALY_PCT = Decimal("25.0")
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


def money(value: float) -> str:
    return f"£{rounded(value, '1'):,}"


def count(value: float) -> str:
    return f"{int(value):,}"


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


def ranked(products: pd.DataFrame, by: str) -> list[tuple[str, float, int]]:
    """(label, revenue, lines) top 5, revenue desc then label asc."""
    rows: list[tuple[str, float, int]] = []
    for key, group in products.groupby(by):
        label = (
            str(key)
            if by == "Country"
            else str(group["Description"].value_counts().sort_index().idxmax())
        )
        rows.append((label[:MAX_LABEL], float(group["revenue"].sum()), len(group)))
    rows.sort(key=lambda r: (-round(r[1], 6), r[0]))
    return rows[:5]


def compute_week(
    df: pd.DataFrame, start: date, file_name: str
) -> tuple[list[Figure], list[str]]:
    """The 44 figures of DEC-05 for the ISO week starting `start`, plus the anomaly keys of DEC-04."""
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

    lines = f"{cur.lines:,} product lines, {rng}, {file_name}"
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
        f"£{rounded(week_aov or 0, '0.01'):,}",
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
                f"({kpi} this week − {kpi} of the {described}) / base × 100; base {'n/a' if base is None else f'{round(base, 2):,}'}, {file_name}",
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
                label, revenue, n = top[i]
                add(
                    f"{prefix}_{i + 1}_revenue",
                    label,
                    revenue,
                    money(revenue),
                    f"sum(Quantity×Price) of {label} over {n:,} product lines, {rng}, {file_name}",
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
        f"−sum(Quantity×Price) over {len(cancelled):,} product cancellation lines, {rng}, {file_name}",
    )
    add(
        "net_revenue",
        "Revenue after product cancellations (GBP)",
        cur.revenue - cancelled_value,
        money(cur.revenue - cancelled_value),
        f"product revenue (F3) − cancelled product value (F43), {rng}, {file_name}",
    )
    return figures, anomalies
