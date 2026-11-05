from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from weekly_kpi_report_agent.kpis import change, compute_week, money, rounded


def test_half_up_rounding() -> None:
    assert money(76.5) == "£77"
    assert money(1234567.49) == "£1,234,567"
    assert rounded(0.125, "0.01") == Decimal("0.13")
    assert rounded(12.25, "0.1") == Decimal("12.3")
    assert rounded(130274.65 / 242, "0.01") == Decimal("538.33")
    assert change(-0.04) == "+0.0%"
    assert change(-0.05) == "-0.1%"


def frame(
    rows: list[tuple[str, str, int, datetime, float, float | None]],
) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=[
            "Invoice",
            "StockCode",
            "Quantity",
            "InvoiceDate",
            "Price",
            "Customer ID",
        ],
    )
    df["Description"] = "ITEM"
    df["Country"] = "United Kingdom"
    df["bucket"] = "product"
    df["revenue"] = df["Quantity"] * df["Price"]
    return df


def test_week_without_lines_is_all_zero_and_changes_na() -> None:
    df = frame([("1", "10000", 1, datetime(2011, 1, 3, 9), 2.0, 1.0)])
    figures, anomalies = compute_week(df, date(2011, 1, 10), "f.xlsx")
    by_id = {f.id: f for f in figures}
    assert by_id["F42"].value == 0
    assert by_id["F5"].display == "n/a"
    assert by_id["F11"].display == "-100.0%"
    assert anomalies == ["revenue_wow", "revenue_vs4w", "orders_wow", "orders_vs4w"]


def test_iso_week_53_has_no_yoy_base() -> None:
    df = frame([("1", "10000", 1, datetime(2015, 12, 28, 9), 2.0, 1.0)])
    by_id = {f.id: f for f in compute_week(df, date(2015, 12, 28), "f.xlsx")[0]}
    assert by_id["F13"].display == "n/a"
    assert by_id["F3"].display == "£2"
