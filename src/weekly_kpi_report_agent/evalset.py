import itertools
import re
from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel

from weekly_kpi_report_agent.checker import check_narrative
from weekly_kpi_report_agent.kpis import compute_week
from weekly_kpi_report_agent.models import Figure

TYPES = [
    "digit_swap",
    "rounding",
    "sign_flip",
    "misattributed",
    "invented",
    "wrong_direction",
]
PER_TYPE = 10
CLEAN = len(TYPES) * PER_TYPE


class TypeResult(BaseModel):
    planted: int = 0
    caught: int = 0


class CheckerEval(BaseModel):
    cases: int
    clean: int
    planted: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    by_type: dict[str, TypeResult]


def direction(f: Figure) -> str:
    return "rose" if (f.value or 0) > 0 else "fell"


def sentences(f: dict[str, Figure]) -> list[str]:
    """Clean sentences built only from figure displays, each number with its own marker."""
    out = [
        f"Revenue came to {f['F3'].display} [F3] in the week of {f['F1'].display} [F1]."
    ]
    out.append(
        f"There were {f['F4'].display} [F4] orders with an average order value of {f['F5'].display} [F5]."
    )
    out.append(
        f"Customers numbered {f['F7'].display} [F7], of whom {f['F8'].display} [F8] were new."
    )
    names = {
        "F11": "Revenue",
        "F14": "Orders",
        "F17": "Average order value",
        "F20": "Units",
        "F23": "Customers",
    }
    for fid, name in names.items():
        for offset, when in [
            (0, "week on week"),
            (1, "against the four-week average"),
            (2, "year on year"),
        ]:
            c = f[f"F{int(fid[1:]) + offset}"]
            if c.value:
                out.append(f"{name} {direction(c)} {c.display} [{c.id}] {when}.")
    for fid in ["F26", "F31"]:
        if f[fid].value is not None:
            out.append(f'"{f[fid].label}" brought in {f[fid].display} [{fid}].')
    return out


def plant(
    kind: str, text: str, f: dict[str, Figure], rng: np.random.Generator
) -> str | None:
    """One planted error of `kind` in `text`, or None when the text has nothing to plant it on."""
    refs = [
        (m.group(1), m.group(2))
        for m in re.finditer(r"(\S+) \[(F\d+)\]", text)
        if f[m.group(2)].key not in ("week_start", "week_end")
    ]
    if kind == "invented":
        return text + f" Returns came to {int(rng.integers(2, 20))}% of orders."
    if kind == "wrong_direction":
        flips = [w for w in ("rose", "fell") if f" {w} " in text]
        if not flips:
            return None
        word = flips[int(rng.integers(len(flips)))]
        return text.replace(f" {word} ", f" {'fell' if word == 'rose' else 'rose'} ", 1)
    candidates = refs
    if kind == "sign_flip":
        candidates = [r for r in refs if r[0][0] in "+-"]
    if kind == "digit_swap":
        candidates = [r for r in refs if sum(ch.isdigit() for ch in r[0]) >= 2]
    if not candidates:
        return None
    token, fid = candidates[int(rng.integers(len(candidates)))]
    if kind == "sign_flip":
        wrong = ("-" if token[0] == "+" else "+") + token[1:]
    elif kind == "misattributed":
        others = [
            g.display
            for g in f.values()
            if g.value is not None
            and g.display != token
            and g.key not in ("week_start", "week_end")
        ]
        wrong = others[int(rng.integers(len(others)))]
    else:
        digits = [i for i, ch in enumerate(token) if ch.isdigit()]
        if kind == "digit_swap":
            pairs = [
                (a, b) for a, b in itertools.pairwise(digits) if token[a] != token[b]
            ]
            if pairs:
                a, b = pairs[int(rng.integers(len(pairs)))]
                wrong = (
                    token[:a] + token[b] + token[a + 1 : b] + token[a] + token[b + 1 :]
                )
            else:
                i = digits[-1]
                wrong = token[:i] + str((int(token[i]) + 1) % 10) + token[i + 1 :]
        else:
            i = digits[-1]
            wrong = (
                token[:i]
                + str((int(token[i]) + (1 if rng.integers(2) else 9)) % 10)
                + token[i + 1 :]
            )
    return text.replace(f"{token} [{fid}]", f"{wrong} [{fid}]", 1)


def evaluate(
    df: pd.DataFrame, weeks: list[date], file_name: str, seed: int
) -> CheckerEval:
    rng = np.random.default_rng(seed)
    pools = []
    for start in weeks:
        figures, _ = compute_week(df, start, file_name)
        if figures[-1].value:
            by_id = {f.id: f for f in figures}
            pools.append((figures, by_id, sentences(by_id)))
    if not pools:
        raise ValueError("no week with sales data in the range")

    def case() -> tuple[list[Figure], dict[str, Figure], str]:
        figures, by_id, pool = pools[int(rng.integers(len(pools)))]
        return (
            figures,
            by_id,
            " ".join(
                pool[int(i)]
                for i in rng.choice(len(pool), min(4, len(pool)), replace=False)
            ),
        )

    tn = fp = 0
    for _ in range(CLEAN):
        figures, _, text = case()
        if check_narrative(text, figures):
            fp += 1
        else:
            tn += 1
    by_type = {kind: TypeResult() for kind in TYPES}
    for kind in TYPES:
        for _ in range(100 * PER_TYPE):
            if by_type[kind].planted == PER_TYPE:
                break
            figures, by_id, text = case()
            planted = plant(kind, text, by_id, rng)
            if planted is None or planted == text:
                continue
            by_type[kind].planted += 1
            by_type[kind].caught += bool(check_narrative(planted, figures))
        else:
            raise ValueError(f"could not plant {PER_TYPE} {kind} errors in the range")
    tp = sum(r.caught for r in by_type.values())
    fn = CLEAN - tp
    return CheckerEval(
        cases=2 * CLEAN,
        clean=CLEAN,
        planted=CLEAN,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        precision=round(tp / (tp + fp), 3) if tp + fp else 0.0,
        recall=round(tp / CLEAN, 3),
        by_type=by_type,
    )
