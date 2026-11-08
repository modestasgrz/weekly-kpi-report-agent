from datetime import date, datetime

import pandas as pd

from weekly_kpi_report_agent.data import COLUMNS, clean
from weekly_kpi_report_agent.kpis import compute_week
from weekly_kpi_report_agent.models import Figure

Row = tuple[str, str, str, int, datetime, float, float | None, str]
UK = "United Kingdom"
MON = date(2011, 11, 28)


def at(day: str, hour: int = 10) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00")


def line(
    invoice: str,
    code: str,
    desc: str,
    qty: int,
    when: datetime,
    price: float,
    customer: float | None = 1.0,
    country: str = UK,
) -> Row:
    return (invoice, code, desc, qty, when, price, customer, country)


def figures(rows: list[Row], start: date = MON) -> tuple[dict[str, Figure], list[str]]:
    df = clean([pd.DataFrame(rows, columns=COLUMNS)])
    found, anomalies = compute_week(df, start, "f.xlsx")
    return {f.id: f for f in found}, anomalies


def displays(by_id: dict[str, Figure], *ids: str) -> list[str]:
    return [by_id[i].display for i in ids]


def test_always_52_figures_in_fixed_order() -> None:
    by_id, _ = figures([line("1", "10001", "A", 1, at("2011-11-29"), 1.0)])
    assert list(by_id) == [f"F{i}" for i in range(1, 53)]


def test_week_with_only_cancellations_has_no_product_figures() -> None:
    by_id, anomalies = figures(
        [
            line("C1", "10001", "A", -1, at("2011-11-29"), 2.0),
            line("C1", "10002", "B", -3, at("2011-11-29"), 2.0),
            line("C2", "10001", "A", -1, at("2011-11-30"), 2.0),
        ]
    )
    assert displays(by_id, "F42", "F3", "F4", "F6", "F7") == ["0", "£0", "0", "0", "0"]
    assert by_id["F42"].value == 0
    assert displays(by_id, "F5", "F26", "F31") == ["n/a", "n/a", "n/a"]
    assert displays(by_id, "F37", "F10") == ["3", "100.0%"]
    assert anomalies == []


def test_week_with_nothing_at_all_has_na_rates() -> None:
    by_id, _ = figures([line("1", "10001", "A", 1, at("2011-10-03"), 1.0)])
    assert displays(by_id, "F42", "F10", "F5") == ["0", "n/a", "n/a"]
    assert by_id["F10"].value is None
    assert by_id["F10"].source == ""


def test_dataset_without_any_product_line_does_not_crash() -> None:
    by_id, _ = figures([line("C1", "10001", "A", -1, at("2011-11-29"), 2.0)])
    assert displays(by_id, "F42", "F8", "F9") == ["0", "0", "0"]


def test_cancellation_rate_counts_distinct_invoices_not_lines() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "A", 1, at("2011-11-29"), 1.0),
            line("1", "10002", "B", 1, at("2011-11-29"), 1.0),
            line("C2", "10001", "A", -1, at("2011-11-29"), 1.0),
            line("C2", "10002", "B", -1, at("2011-11-29"), 1.0),
        ]
    )
    assert displays(by_id, "F4", "F37", "F10") == ["1", "2", "50.0%"]


def test_all_customer_ids_missing() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "A", 1, at("2011-11-29"), 1.0, None),
            line("2", "10002", "B", 2, at("2011-11-30"), 1.0, None),
        ]
    )
    assert displays(by_id, "F7", "F8", "F9", "F41", "F42") == ["0", "0", "0", "2", "2"]
    assert displays(by_id, "F4", "F6") == ["2", "3"]


def test_all_customer_ids_missing_in_whole_dataset_gives_na_customer_changes() -> None:
    by_id, _ = figures(
        [
            line("0", "10001", "A", 1, at("2011-11-22"), 1.0, None),
            line("1", "10001", "A", 1, at("2011-11-29"), 1.0, None),
        ]
    )
    assert displays(by_id, "F23", "F24", "F25") == ["n/a", "n/a", "n/a"]
    assert displays(by_id, "F11") == ["+0.0%"]


def test_missing_customer_ids_do_not_count_as_customers() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "A", 1, at("2011-11-29"), 1.0, 7.0),
            line("2", "10001", "A", 1, at("2011-11-29"), 1.0, None),
            line("3", "10001", "A", 1, at("2011-11-29"), 1.0, 7.0),
        ]
    )
    assert displays(by_id, "F7", "F8", "F9", "F41") == ["1", "1", "0", "1"]


def test_customer_seen_before_the_week_is_returning_even_with_old_cancel_first() -> (
    None
):
    by_id, _ = figures(
        [
            line("C0", "10001", "A", -1, at("2011-11-01"), 1.0, 5.0),
            line("1", "10001", "A", 1, at("2011-11-29"), 1.0, 5.0),
            line("2", "10001", "A", 1, at("2011-11-29"), 1.0, 6.0),
        ]
    )
    assert displays(by_id, "F7", "F8", "F9") == ["2", "2", "0"]


def test_ties_in_top_five_are_alphabetical_by_label() -> None:
    codes = ["10007", "10006", "10005", "10004", "10003", "10002", "10001"]
    names = ["G", "F", "E", "D", "C", "B", "A"]
    rows = [
        line(str(i), code, name, 1, at("2011-11-29"), 10.0)
        for i, (code, name) in enumerate(zip(codes, names, strict=True))
    ]
    by_id, _ = figures(rows)
    assert [by_id[f"F{i}"].label for i in range(26, 31)] == ["A", "B", "C", "D", "E"]
    assert displays(by_id, "F26", "F30") == ["£10", "£10"]


def test_float_noise_does_not_break_a_revenue_tie() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "BBB", 3, at("2011-11-29"), 0.1),
            line("2", "10002", "AAA", 1, at("2011-11-29"), 0.3),
        ]
    )
    assert [by_id["F26"].label, by_id["F27"].label] == ["AAA", "BBB"]


def test_higher_revenue_beats_alphabetical_order() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "AAA", 1, at("2011-11-29"), 1.0),
            line("2", "10002", "ZZZ", 1, at("2011-11-29"), 2.0),
        ]
    )
    assert [by_id["F26"].label, by_id["F27"].label] == ["ZZZ", "AAA"]


def test_only_top_five_and_rest_are_na() -> None:
    rows = [
        line(str(i), f"1000{i}", f"P{i}", 1, at("2011-11-29"), float(i))
        for i in range(1, 7)
    ]
    by_id, _ = figures(rows)
    assert [by_id[f"F{i}"].label for i in range(26, 31)] == [
        "P6",
        "P5",
        "P4",
        "P3",
        "P2",
    ]
    one, _ = figures(rows[:1])
    assert displays(one, "F26", "F27", "F30") == ["£1", "n/a", "n/a"]
    assert one["F27"].value is None
    assert one["F27"].label == ""
    assert displays(one, "F31", "F32") == ["£1", "n/a"]


def test_country_ties_are_alphabetical() -> None:
    rows = [
        line(str(i), "10001", "A", 1, at("2011-11-29"), 5.0, 1.0, country)
        for i, country in enumerate(["Spain", "France", "Italy", "Austria"])
    ]
    by_id, _ = figures(rows)
    assert [by_id[f"F{i}"].label for i in range(31, 35)] == [
        "Austria",
        "France",
        "Italy",
        "Spain",
    ]


def test_label_is_the_most_frequent_description_with_alphabetical_tie() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "ZEBRA MUG", 1, at("2011-11-29"), 1.0),
            line("2", "10001", "APPLE MUG", 1, at("2011-11-29"), 1.0),
            line("3", "10002", "COMMON", 1, at("2011-11-29"), 0.5),
            line("4", "10002", "COMMON", 1, at("2011-11-29"), 0.5),
            line("5", "10002", "RARE", 1, at("2011-11-29"), 0.5),
        ]
    )
    assert by_id["F26"].label == "APPLE MUG"
    assert by_id["F27"].label == "COMMON"
    assert displays(by_id, "F26", "F27") == ["£2", "£2"]


def test_label_is_cut_to_100_characters() -> None:
    by_id, _ = figures([line("1", "10001", "X" * 150, 1, at("2011-11-29"), 1.0)])
    assert by_id["F26"].label == "X" * 100
    assert "X" * 101 not in by_id["F26"].source


def test_top_list_ignores_cancelled_zero_price_and_non_product_lines() -> None:
    by_id, _ = figures(
        [
            line("1", "10001", "REAL", 1, at("2011-11-29"), 1.0),
            line("C2", "10002", "CANCELLED", -5, at("2011-11-29"), 100.0),
            line("3", "10003", "FREE", 5, at("2011-11-29"), 0.0),
            line("4", "POST", "POSTAGE", 1, at("2011-11-29"), 50.0),
        ]
    )
    assert by_id["F26"].label == "REAL"
    assert by_id["F27"].display == "n/a"


def week_53_frame() -> list[Row]:
    return [line("1", "10001", "A", 1, at("2015-12-29"), 2.0)]


def test_iso_week_53_has_no_year_ago_week_even_with_data_a_year_before() -> None:
    rows = [
        *week_53_frame(),
        line("0", "10001", "A", 1, at("2014-12-29"), 2.0),
        line("00", "10001", "A", 1, at("2014-12-22"), 2.0),
    ]
    by_id, anomalies = figures(rows, date(2015, 12, 28))
    assert displays(by_id, "F13", "F16", "F19", "F22", "F25") == ["n/a"] * 5
    assert by_id["F13"].value is None
    assert by_id["F13"].source == ""
    assert "revenue_yoy" not in anomalies


def test_iso_week_one_uses_the_iso_year_not_the_calendar_year() -> None:
    rows = [
        line("0", "10001", "A", 1, at("2018-01-02"), 100.0),
        line("1", "10001", "A", 1, at("2019-01-01"), 200.0),
    ]
    by_id, _ = figures(rows, date(2018, 12, 31))
    assert by_id["F13"].display == "+100.0%"
    assert "2018-01-01..2018-01-07" in by_id["F13"].source


def test_year_ago_week_may_start_in_the_previous_calendar_year() -> None:
    rows = [
        line("0", "10001", "A", 1, at("2019-12-31"), 100.0),
        line("1", "10001", "A", 1, at("2021-01-05"), 50.0),
    ]
    by_id, _ = figures(rows, date(2021, 1, 4))
    assert by_id["F13"].display == "-50.0%"
    assert "2019-12-30..2020-01-05" in by_id["F13"].source


def test_year_ago_week_without_data_gives_na_not_minus_100() -> None:
    by_id, _ = figures([line("1", "10001", "A", 1, at("2011-11-29"), 2.0)])
    assert displays(by_id, "F13", "F16", "F19", "F22", "F25") == ["n/a"] * 5


def test_previous_week_empty_gives_na_wow_but_defined_4_week_change() -> None:
    rows = [
        line("1", "10001", "A", 1, at("2011-11-29"), 100.0, 1.0),
        line("0", "10001", "A", 1, at("2011-11-15"), 40.0, 1.0),
    ]
    by_id, anomalies = figures(rows)
    assert displays(by_id, "F11", "F14", "F17", "F20", "F23") == ["n/a"] * 5
    assert displays(by_id, "F12", "F15", "F18", "F21", "F24") == [
        "+900.0%",
        "+300.0%",
        "+150.0%",
        "+300.0%",
        "+300.0%",
    ]
    assert anomalies == ["revenue_vs4w", "orders_vs4w"]


def test_previous_week_empty_and_no_older_data_gives_all_na_changes() -> None:
    by_id, anomalies = figures([line("1", "10001", "A", 1, at("2011-11-29"), 100.0)])
    assert displays(by_id, *[f"F{i}" for i in range(11, 26)]) == ["n/a"] * 15
    assert anomalies == []


def test_4_week_aov_is_sum_of_revenue_over_sum_of_orders() -> None:
    rows = [
        line("1", "10001", "A", 1, at("2011-11-29"), 125.0),
        line("2", "10001", "A", 1, at("2011-11-23"), 100.0),
        line("3", "10001", "A", 1, at("2011-11-15"), 50.0),
        line("4", "10001", "A", 1, at("2011-11-15"), 50.0),
        line("5", "10001", "A", 1, at("2011-11-15"), 50.0),
        line("6", "10001", "A", 1, at("2011-10-05"), 5000.0),
    ]
    by_id, _ = figures(rows)
    assert displays(by_id, "F5") == ["£125.00"]
    assert displays(by_id, "F18") == ["+100.0%"]
    assert "base 62.5" in by_id["F18"].source
    assert displays(by_id, "F12", "F15") == ["+100.0%", "+0.0%"]


def test_4_week_mean_counts_empty_weeks_as_zero() -> None:
    rows = [
        line("1", "10001", "A", 1, at("2011-11-29"), 100.0),
        line("2", "10001", "A", 1, at("2011-11-02"), 100.0),
    ]
    by_id, _ = figures(rows)
    assert displays(by_id, "F12", "F15") == ["+300.0%", "+300.0%"]
    assert displays(by_id, "F18") == ["+0.0%"]


def test_4_week_window_excludes_the_fifth_previous_week() -> None:
    rows = [
        line("1", "10001", "A", 1, at("2011-11-29"), 100.0),
        line("2", "10001", "A", 1, at("2011-10-31"), 100.0),
        line("3", "10001", "A", 1, at("2011-10-24"), 100000.0),
    ]
    by_id, _ = figures(rows)
    assert displays(by_id, "F12") == ["+300.0%"]


def steady_weeks(current_revenue: float) -> list[Row]:
    previous = [
        line(str(i), "10001", "A", 1, at(day), 100.0, 1.0)
        for i, day in enumerate(
            ["2011-11-22", "2011-11-15", "2011-11-08", "2011-11-01"]
        )
    ]
    return [
        *previous,
        line("9", "10001", "A", 1, at("2011-11-29"), current_revenue, 1.0),
    ]


def test_anomaly_threshold_is_inclusive() -> None:
    by_id, anomalies = figures(steady_weeks(125.0))
    assert displays(by_id, "F11", "F12") == ["+25.0%", "+25.0%"]
    assert anomalies == ["revenue_wow", "revenue_vs4w"]


def test_change_just_below_the_threshold_is_not_an_anomaly() -> None:
    by_id, anomalies = figures(steady_weeks(124.9))
    assert displays(by_id, "F11") == ["+24.9%"]
    assert anomalies == []


def test_big_drops_are_anomalies_but_yoy_and_other_kpis_never_are() -> None:
    rows = [
        line("0", "10001", "A", 1, at("2010-11-30"), 0.2, 1.0),
        *[
            line(str(i), "10001", "A", 10, at(day), 100.0, 1.0)
            for i, day in enumerate(
                ["2011-11-22", "2011-11-15", "2011-11-08", "2011-11-01"], start=1
            )
        ],
        line("9", "10001", "A", 1, at("2011-11-29"), 1.0, 2.0),
        line("9", "10002", "B", 1, at("2011-11-29"), 1.0, 3.0),
    ]
    by_id, anomalies = figures(rows)
    assert displays(by_id, "F11", "F13", "F14", "F17", "F20", "F23") == [
        "-99.8%",
        "+900.0%",
        "+0.0%",
        "-99.8%",
        "-80.0%",
        "+100.0%",
    ]
    assert anomalies == ["revenue_wow", "revenue_vs4w"]


def test_new_customer_is_by_first_product_line_in_whole_dataset() -> None:
    rows = [
        line("1", "10001", "A", 1, at("2011-11-29"), 1.0, 5.0),
        line("2", "10001", "A", 1, at("2011-11-30"), 1.0, 5.0),
        line("3", "10001", "A", 1, at("2011-12-05"), 1.0, 6.0),
        line("0", "10001", "A", 1, at("2011-05-01"), 1.0, 7.0),
        line("4", "10001", "A", 1, at("2011-11-29"), 1.0, 7.0),
    ]
    by_id, _ = figures(rows)
    assert displays(by_id, "F7", "F8", "F9") == ["2", "1", "1"]


def test_week_boundaries_are_monday_midnight_to_sunday_end() -> None:
    rows = [
        line("1", "10001", "A", 1, datetime(2011, 11, 27, 23, 59, 59), 1.0),
        line("2", "10001", "A", 1, datetime(2011, 11, 28, 0, 0, 0), 2.0),
        line("3", "10001", "A", 1, datetime(2011, 12, 4, 23, 59, 59), 4.0),
        line("4", "10001", "A", 1, datetime(2011, 12, 5, 0, 0, 0), 8.0),
    ]
    by_id, _ = figures(rows)
    assert displays(by_id, "F3", "F4", "F42") == ["£6", "2", "2"]


def test_dq_counts_only_cover_lines_dated_in_the_week() -> None:
    rows = [
        line("C1", "10001", "A", -1, at("2011-11-20"), 1.0),
        line("C2", "10001", "A", -1, at("2011-11-29"), 1.0),
        line("A3", "B", "adj", 1, at("2011-11-29"), -5.0),
        line("4", "POST", "P", 1, at("2011-11-29"), 5.0),
        line("5", "10001", "A", 0, at("2011-11-29"), 5.0),
        line("6", "10001", "A", 1, at("2011-11-29"), 0.0),
        line("7", "10001", "A", 1, at("2011-11-29"), 3.0),
        line("7", "10001", "A", 1, at("2011-11-29"), 3.0),
    ]
    by_id, _ = figures(rows)
    assert displays(by_id, "F36", "F37", "F38", "F39", "F40", "F41", "F42") == [
        "1",
        "1",
        "1",
        "1",
        "2",
        "0",
        "1",
    ]


def test_large_revenue_uses_narrow_space_thousands() -> None:
    by_id, _ = figures([line("1", "10001", "A", 1000, at("2011-11-29"), 1234.567)])
    assert displays(by_id, "F3", "F5", "F26") == [
        "£1\u202f234\u202f567",
        "£1\u202f234\u202f567.00",
        "£1\u202f234\u202f567",
    ]
