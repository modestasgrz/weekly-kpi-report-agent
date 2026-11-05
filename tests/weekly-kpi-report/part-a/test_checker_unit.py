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
    assert kinds("It was n/a [F13] and 1 [F13].") == [
        ("unknown_number", "1"),
        ("wrong_reference", "[F13]"),
    ]


def test_marker_without_number_to_missing_figure_is_flagged() -> None:
    assert kinds("Strong week [F99].") == [("wrong_reference", "[F99]")]


def test_curly_quotes_and_full_stop_inside_label_are_masked() -> None:
    figures = [*FIGURES, fig("F27", "£5", 5, "ST. GEORGE 3 FLAG")]
    assert (
        check_narrative(
            '“ST. GEORGE 3 FLAG” made £5 [F27]. "SET OF 3 TINS" sold £77 [F26].',
            figures,
        )
        == []
    )


def test_non_ascii_numerals_are_flagged() -> None:
    assert kinds("Revenue rose ½ point to £1,234 [F3].") == [("unknown_number", "½")]


def test_trailing_comma_is_not_part_of_the_token() -> None:
    assert kinds("Revenue was £1,234, up.") == [("missing_reference", "£1,234")]


def test_change_shown_as_zero_ignores_direction() -> None:
    figures = [*FIGURES, fig("F14", "+0.0%", -0.01)]
    assert check_narrative("Orders rose +0.0% [F14].", figures) == []


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


def test_eval_clean_sentences_never_put_a_direction_word_on_a_shown_zero() -> None:
    from weekly_kpi_report_agent.evalset import sentences

    base = {f"F{i}": fig(f"F{i}", "1", 1.0) for i in range(1, 43)}
    base["F12"] = fig("F12", "+0.0%", -0.01)
    base["F11"] = fig("F11", "+5.0%", 5.0)
    text = " ".join(sentences(base))
    assert "+0.0% [F12]" not in text
    assert "rose +5.0% [F11]" in text
