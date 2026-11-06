import pytest

from weekly_kpi_report_agent.checker import check_narrative
from weekly_kpi_report_agent.models import Figure


def fig(fid: str, display: str, value: float | None = 1.0, label: str = "") -> Figure:
    return Figure(
        id=fid, key=fid, label=label, value=value, display=display, source="s"
    )


FIGURES = [
    fig("F1", "2011-11-28", 20111128),
    fig("F2", "2011-12-04", 20111204),
    fig("F3", "£1\u202f234\u202f567", 1234567),
    fig("F4", "12"),
    fig("F5", "£47.52", 47.52),
    fig("F6", "1\u202f000", 1000),
    fig("F10", "25.0%", 25.0),
    fig("F11", "+39.8%", 39.8),
    fig("F12", "+0.0%", 0.0),
    fig("F13", "n/a", None),
    fig("F17", "-6.8%", -6.8),
    fig("F26", "£77", 77, "SET OF 3 TINS"),
    fig("F27", "£5", 5, "MUG"),
    fig("F29", "n/a", None, "MUG 5"),
]


def kinds(text: str, figures: list[Figure] | None = None) -> list[tuple[str, str]]:
    return [
        (v.kind, v.token)
        for v in check_narrative(text, FIGURES if figures is None else figures)
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Revenue reached £1\u202f234\u202f567 [F3].",
        "Revenue reached £1\u202f234\u202f567[F3].",
        "The average order was £47.52 [F5].",
        "Conversion was 25.0% [F10].",
        "Units were 1\u202f000 [F6].",
    ],
)
def test_exact_display_with_own_marker_passes(text: str) -> None:
    assert kinds(text) == []


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("Revenue reached £1234567 [F3].", "£1234567"),
        ("Revenue reached £1\u202f234\u202f568 [F3].", "£1\u202f234\u202f568"),
        ("Revenue reached 1\u202f234\u202f567 [F3].", "1\u202f234\u202f567"),
        ("Order value was £47.5 [F5].", "£47.5"),
        ("Order value was £47.520 [F5].", "£47.520"),
        ("Rate was 25% [F10].", "25%"),
        ("Rate was 25.0 [F10].", "25.0"),
        ("Orders were 12.0 [F4].", "12.0"),
        ("Orders were 012 [F4].", "012"),
        ("Revenue rose 39.8% [F11].", "39.8%"),
        ("Aov fell 6.8% [F17].", "6.8%"),
    ],
)
def test_display_must_match_character_for_character(text: str, token: str) -> None:
    assert kinds(text) == [("unknown_number", token)]


def test_unicode_minus_is_normalised_in_reported_token() -> None:
    assert kinds("Aov fell −6.8% [F17].") == []
    assert kinds("Aov fell −7.8% [F17].") == [("unknown_number", "-7.8%")]
    assert kinds("Aov fell −6.8%.") == [("missing_reference", "-6.8%")]


def test_number_glued_to_text_is_not_followed_by_a_marker() -> None:
    assert kinds("We shipped 12x [F4].") == [("missing_reference", "12")]
    assert kinds("We shipped 12x.") == [("missing_reference", "12")]
    assert kinds("Sales were £1\u202f234\u202f567k [F3].") == [
        ("missing_reference", "£1\u202f234\u202f567")
    ]


def test_marker_without_space_and_marker_variants() -> None:
    assert kinds("Orders were 12[F4].") == []
    assert kinds("Orders were 12  [F4].") == [("missing_reference", "12")]
    assert kinds("Orders were 12 [ F4].") == [
        ("missing_reference", "12"),
        ("missing_reference", "4"),
    ]
    assert kinds("Orders were 12 [f4].") == [
        ("missing_reference", "12"),
        ("missing_reference", "4"),
    ]
    assert kinds("Orders were [F4] 12.") == [("missing_reference", "12")]


def test_extra_markers_to_existing_figures_pass_but_orphan_unknown_marker_is_flagged() -> (
    None
):
    assert kinds("Orders were 12 [F4] [F3].") == []
    assert kinds("Orders were 12 [F4] [F3] [F99].") == [("wrong_reference", "[F99]")]


def test_two_numbers_sharing_one_marker() -> None:
    assert kinds("Orders and revenue were 12 and £1\u202f234\u202f567 [F3].") == [
        ("missing_reference", "12")
    ]
    assert kinds("Revenue £1\u202f234\u202f567 and orders 12 [F4].") == [
        ("missing_reference", "£1\u202f234\u202f567")
    ]


def test_marker_pointing_at_na_figure_matches_nothing() -> None:
    assert kinds("Orders were 12 [F13].") == [("wrong_reference", "12")]
    assert kinds("Orders were 13 [F13].") == [("unknown_number", "13")]
    assert kinds("Orders were 12 [F29].") == [("wrong_reference", "12")]


def test_marker_pointing_at_missing_figure() -> None:
    assert kinds("Orders were 12 [F99].") == [("wrong_reference", "12")]
    assert kinds("Orders were 13 [F99].") == [("unknown_number", "13")]
    assert kinds("Orders were 12 [F0].") == [("wrong_reference", "12")]


def test_empty_and_numberless_text_has_no_violations() -> None:
    assert kinds("") == []
    assert kinds("   ") == []
    assert kinds("Sales were strong.") == []
    assert kinds("Revenue £5 [F27].", []) == [("unknown_number", "£5")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Week of 2011-11-28 [F1] to 2011-12-04 [F2].", []),
        ("Week of 2011-11-30 [F1].", [("unknown_number", "2011-11-30")]),
        ("Week of 2011-12-04 [F1].", [("wrong_reference", "2011-12-04")]),
        ("Week of 2011-11-28.", [("missing_reference", "2011-11-28")]),
        ("Week of 2011-11-28[F1].", []),
        ("Week of 2011-13-45 [F1].", [("unknown_number", "2011-13-45")]),
    ],
)
def test_dates_are_one_token_not_three_numbers(
    text: str, expected: list[tuple[str, str]]
) -> None:
    assert kinds(text) == expected


def test_date_with_other_dates_in_one_sentence_reports_each() -> None:
    assert kinds("From 2011-11-21 [F1] until 2011-12-11 [F2].") == [
        ("unknown_number", "2011-11-21"),
        ("unknown_number", "2011-12-11"),
    ]


def test_quoted_label_masks_digits_inside_it() -> None:
    assert kinds('"SET OF 3 TINS" sold £77 [F26].') == []
    assert kinds('"SET OF 3 TINS" sold well.') == []


def test_quoted_text_that_is_not_a_label_is_checked() -> None:
    assert kinds('"SET OF 4 TINS" sold £77 [F26].') == [("missing_reference", "4")]
    assert kinds('"set of 3 tins" sold £77 [F26].') == [("missing_reference", "3")]
    assert kinds('"SET OF 3 TINS " sold £77 [F26].') == [("missing_reference", "3")]
    assert kinds('"SET OF 3" sold £77 [F26].') == [("missing_reference", "3")]


def test_quoted_label_of_na_figure_is_not_masked() -> None:
    assert kinds('"MUG 5" sold nothing.') == [("missing_reference", "5")]


def test_unquoted_label_digits_are_checked() -> None:
    assert kinds("SET OF 3 TINS sold £77 [F26].") == [("missing_reference", "3")]


def test_label_masking_does_not_hide_a_number_outside_the_quotes() -> None:
    assert kinds('"SET OF 3 TINS" sold 99 units.') == [("missing_reference", "99")]
    assert kinds('"SET OF 3 TINS" sold £77 [F26] and "SET OF 3 TINS" 12.') == [
        ("missing_reference", "12")
    ]


def test_two_labels_in_one_sentence_are_both_masked() -> None:
    assert kinds('"SET OF 3 TINS" beat "MUG" at £77 [F26] vs £5 [F27].') == []


def test_direction_word_in_a_later_clause_wins() -> None:
    assert kinds("Revenue fell last week but rose +39.8% [F11] this week.") == []
    assert kinds("Revenue rose last week but fell +39.8% [F11] this week.") == [
        ("wrong_direction", "+39.8%")
    ]


def test_direction_word_resets_after_each_marker() -> None:
    assert kinds("Orders fell to 12 [F4] and revenue rose +39.8% [F11].") == []
    assert kinds("Orders rose to 12 [F4] while aov fell -6.8% [F17].") == []
    assert kinds("Orders rose to 12 [F4] while aov rose -6.8% [F17].") == [
        ("wrong_direction", "-6.8%")
    ]
    assert kinds("Revenue fell to £1\u202f234\u202f567 [F3], then +39.8% [F11].") == []


def test_direction_word_after_the_figure_is_ignored() -> None:
    assert kinds("Revenue +39.8% [F11] fell short of hopes.") == []


def test_direction_words_are_whole_words_and_case_insensitive() -> None:
    assert kinds("The upgrade downturn dropout +39.8% [F11].") == []
    assert kinds("Revenue uplifted lowered breakdown +39.8% [F11].") == []
    assert kinds("Revenue FELL +39.8% [F11].") == [("wrong_direction", "+39.8%")]
    assert kinds("Down +39.8% [F11].") == [("wrong_direction", "+39.8%")]
    assert kinds("Up -6.8% [F17].") == [("wrong_direction", "-6.8%")]


@pytest.mark.parametrize("word", ["fell", "down", "decreased", "dropped", "lower"])
def test_every_down_word_contradicts_a_positive_change(word: str) -> None:
    assert kinds(f"Revenue {word} +39.8% [F11].") == [("wrong_direction", "+39.8%")]
    assert kinds(f"Aov {word} -6.8% [F17].") == []


@pytest.mark.parametrize("word", ["rose", "up", "increased", "grew", "higher"])
def test_every_up_word_contradicts_a_negative_change(word: str) -> None:
    assert kinds(f"Aov {word} -6.8% [F17].") == [("wrong_direction", "-6.8%")]
    assert kinds(f"Revenue {word} +39.8% [F11].") == []


def test_direction_words_outside_the_closed_list_are_not_checked() -> None:
    assert kinds("Revenue surged -6.8% [F17].") == []
    assert kinds("Revenue plummeted +39.8% [F11].") == []


def test_direction_check_only_applies_to_change_figures() -> None:
    assert kinds("Orders fell to 12 [F4].") == []
    assert kinds("Rate fell 25.0% [F10].") == []
    assert kinds("Revenue fell to £1\u202f234\u202f567 [F3].") == []


def test_zero_change_passes_with_any_direction() -> None:
    assert kinds("Revenue rose +0.0% [F12].") == []
    assert kinds("Revenue fell +0.0% [F12].") == []


def test_direction_is_not_checked_on_a_token_that_already_failed() -> None:
    assert kinds("Revenue fell +39.8% [F17].") == [("wrong_reference", "+39.8%")]
    assert kinds("Revenue fell +39.9% [F11].") == [("unknown_number", "+39.9%")]


def test_unreferenced_number_does_not_hide_a_wrong_direction() -> None:
    assert kinds("Revenue rose 5 and then fell +39.8% [F11].") == [
        ("missing_reference", "5"),
        ("wrong_direction", "+39.8%"),
    ]


def test_direction_words_do_not_leak_across_sentences() -> None:
    assert kinds("Revenue fell! Then +39.8% [F11] came in.") == []
    assert kinds("Revenue fell? Hmm. +39.8% [F11] came in.") == []
    assert kinds("Did it fall. Revenue +39.8% [F11].") == []


def test_direction_words_do_not_leak_between_headline_and_paragraph() -> None:
    assert kinds("Revenue fell") == []
    assert kinds("Overall +39.8% [F11] versus last week.") == []


def test_each_violating_sentence_is_reported_with_its_own_sentence() -> None:
    violations = check_narrative(
        "Orders were 13 [F4]. All fine here. Revenue was £1.", FIGURES
    )
    assert [(v.kind, v.token, v.sentence) for v in violations] == [
        ("unknown_number", "13", "Orders were 13 [F4]."),
        ("missing_reference", "£1", "Revenue was £1."),
    ]


def test_decimals_do_not_split_sentences() -> None:
    violations = check_narrative("Aov was £47.52 [F5] and not £47.53 [F5].", FIGURES)
    assert [(v.kind, v.token, v.sentence) for v in violations] == [
        (
            "unknown_number",
            "£47.53",
            "Aov was £47.52 [F5] and not £47.53 [F5].",
        )
    ]


def test_signed_number_without_matching_sign_is_unknown() -> None:
    assert kinds("Orders were +12 [F4].") == [("unknown_number", "+12")]
    assert kinds("Orders were -12 [F4].") == [("unknown_number", "-12")]
    assert kinds("Revenue +39.8% [F11] and 39.8% [F11].") == [
        ("unknown_number", "39.8%")
    ]


def test_wrong_reference_to_a_figure_that_shares_the_display() -> None:
    figures = [fig("F4", "12"), fig("F7", "12")]
    assert kinds("Orders 12 [F4] and customers 12 [F7].", figures) == []
    assert kinds("Orders 12 [F7].", figures) == []
    assert kinds("Orders 12 [F5].", figures) == [("wrong_reference", "12")]
