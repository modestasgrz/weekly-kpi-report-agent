from weekly_kpi_report_agent.checker import check_narrative
from weekly_kpi_report_agent.models import Figure


def fig(fid: str, display: str, value: float | None = 1.0, label: str = "") -> Figure:
    return Figure(
        id=fid, key=fid, label=label, value=value, display=display, source="s"
    )


FIGURES = [
    fig("F3", "£1,234"),
    fig("F4", "12"),
    fig("F11", "-6.8%", -6.8),
    fig("F12", "+0.0%", 0.0),
    fig("F13", "n/a", None),
    fig("F26", "£77", 77, "SET OF 3 TINS"),
]


def kinds(text: str) -> list[tuple[str, str]]:
    return [(v.kind, v.token) for v in check_narrative(text, FIGURES)]


def test_unicode_minus_and_marker_without_space() -> None:
    assert kinds("Revenue fell −6.8%[F11].") == []


def test_na_figure_matches_nothing() -> None:
    assert kinds("It was n/a [F13] and 1 [F13].") == [("unknown_number", "1")]


def test_unknown_marker_is_unknown_number() -> None:
    assert kinds("Orders were 12 [F99].") == [("wrong_reference", "12")]


def test_quoted_text_that_is_not_a_label_is_checked() -> None:
    assert kinds('"SET OF 4 TINS" sold £77 [F26].') == [("missing_reference", "4")]


def test_quoted_label_is_masked() -> None:
    assert kinds('"SET OF 3 TINS" sold £77 [F26].') == []


def test_zero_change_ignores_direction() -> None:
    assert kinds("Revenue rose +0.0% [F12].") == []


def test_direction_word_belongs_to_its_own_clause() -> None:
    assert kinds("Orders rose to 12 [F4], while revenue fell -6.8% [F11].") == []
    assert kinds("Orders fell to 12 [F4], while revenue rose -6.8% [F11].") == [
        ("wrong_direction", "-6.8%")
    ]


def test_direction_word_inside_quoted_label_is_ignored() -> None:
    figures = [*FIGURES, fig("F27", "£5", 5, "ROSE GARDEN MUG")]
    assert [
        v.kind
        for v in check_narrative(
            '"ROSE GARDEN MUG" made £5 [F27], revenue -6.8% [F11].', figures
        )
    ] == []


def test_sentences_are_split_on_full_stops() -> None:
    violations = check_narrative("Revenue was £1,234 [F3]. Orders 13 [F4].", FIGURES)
    assert [(v.kind, v.sentence) for v in violations] == [
        ("unknown_number", "Orders 13 [F4].")
    ]
