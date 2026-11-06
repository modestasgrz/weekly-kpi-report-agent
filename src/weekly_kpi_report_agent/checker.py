import itertools
import re
from decimal import Decimal

from weekly_kpi_report_agent.models import Figure, Violation

TOKEN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}|[+\-−]?£?(?:[0-9]{1,3}(?:[,\u202f][0-9]{3})+|[0-9]+)(?:\.[0-9]+)?%?"
)
MARKER = re.compile(r" ?\[F(\d+)\]")
ANY_MARKER = re.compile(r"\[F(\d+)\]")
QUOTED = re.compile(r'["“]([^"“”]*)["”]')
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
    masked = QUOTED.sub(
        lambda m: (
            m.group(0)[0] + "#" * len(m.group(1)) + m.group(0)[-1]
            if m.group(1) in labels
            else m.group(0)
        ),
        text,
    )
    masked = ANY_MARKER.sub(lambda m: "[" + "#" * (len(m.group(0)) - 2) + "]", masked)
    cuts = [0, *(m.end() for m in SENTENCE_END.finditer(masked)), len(text)]
    violations: list[Violation] = []
    for begin, end in itertools.pairwise(cuts):
        sentence = text[begin:end].strip()
        segment_start = begin
        consumed: set[int] = set()
        for ch in masked[begin:end]:
            if ch.isnumeric() and not ch.isascii():
                violations.append(
                    Violation(kind="unknown_number", token=ch, sentence=sentence)
                )
        for match in TOKEN.finditer(masked, begin, end):
            token = match.group(0).replace("−", "-")
            marker = MARKER.match(text, match.end())
            if not marker:
                violations.append(
                    Violation(kind="missing_reference", token=token, sentence=sentence)
                )
                continue
            figure = by_id.get(f"F{marker.group(1)}")
            if figure and figure.display == token:
                if figure.id in CHANGE_IDS and Decimal(token.strip("+-%")):
                    words = [
                        w.lower()
                        for w in WORD.findall(masked[segment_start : match.start()])
                        if w.lower() in UP | DOWN
                    ]
                    if words and (words[-1] in UP) != token.startswith("+"):
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
            consumed.add(marker.start(1))
            segment_start = marker.end()
        for marker in ANY_MARKER.finditer(text, begin, end):
            if marker.start(1) not in consumed and f"F{marker.group(1)}" not in by_id:
                violations.append(
                    Violation(
                        kind="wrong_reference", token=marker.group(0), sentence=sentence
                    )
                )
    return violations
