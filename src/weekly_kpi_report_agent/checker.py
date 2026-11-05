import re

from weekly_kpi_report_agent.models import Figure, Violation

TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}|[+\-−]?£?\d[\d,]*(?:\.\d+)?%?")
MARKER = re.compile(r" ?\[F(\d+)\]")
MARKER_ONLY = re.compile(r"\[F\d+\]")
QUOTED = re.compile(r'"([^"]*)"')
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
UP = {"rose", "up", "increased", "grew", "higher"}
DOWN = {"fell", "down", "decreased", "dropped", "lower"}
WORD = re.compile(r"[A-Za-z]+")
CHANGE_IDS = {f"F{i}" for i in range(11, 26)}


def check_narrative(text: str, figures: list[Figure]) -> list[Violation]:
    """Every number must be a figure display followed by its own [Fn] marker (DEC-09); direction words must match change signs (DEC-17)."""
    by_id = {f.id: f for f in figures if f.value is not None}
    displays = {f.display for f in by_id.values()}
    labels = {f.label for f in by_id.values() if f.label}
    violations: list[Violation] = []
    for sentence in SENTENCE_END.split(text.strip()):
        masked = QUOTED.sub(
            lambda m: (
                '"' + "#" * len(m.group(1)) + '"'
                if m.group(1) in labels
                else m.group(0)
            ),
            sentence,
        )
        masked = MARKER_ONLY.sub(lambda m: "#" * len(m.group(0)), masked)
        segment_start = 0
        for match in TOKEN.finditer(masked):
            token = match.group(0).replace("−", "-")
            marker = MARKER.match(sentence, match.end())
            if not marker:
                violations.append(
                    Violation(kind="missing_reference", token=token, sentence=sentence)
                )
                continue
            figure = by_id.get(f"F{marker.group(1)}")
            if figure and figure.display == token:
                if figure.id in CHANGE_IDS and figure.value:
                    words = [
                        w.lower()
                        for w in WORD.findall(masked[segment_start : match.start()])
                        if w.lower() in UP | DOWN
                    ]
                    if words and (words[-1] in UP) != (figure.value > 0):
                        violations.append(
                            Violation(
                                kind="wrong_direction", token=token, sentence=sentence
                            )
                        )
            elif token in displays:
                violations.append(
                    Violation(kind="wrong_reference", token=token, sentence=sentence)
                )
            else:
                violations.append(
                    Violation(kind="unknown_number", token=token, sentence=sentence)
                )
            segment_start = marker.end()
    return violations
