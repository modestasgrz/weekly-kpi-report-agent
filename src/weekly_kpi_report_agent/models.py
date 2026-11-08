from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Figure(BaseModel):
    id: str
    key: str
    label: str
    value: float | None
    display: str
    source: str


class Violation(BaseModel):
    kind: Literal[
        "unknown_number", "wrong_reference", "missing_reference", "wrong_direction"
    ]
    token: str
    sentence: str


class Narrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=120)
    paragraphs: list[Annotated[str, Field(min_length=1, max_length=600)]] = Field(
        min_length=1, max_length=4
    )

    def texts(self) -> list[str]:
        return [self.headline, *self.paragraphs]


class Cause(BaseModel):
    product: str
    invoice: str
    cancel_invoice: str | None
    rule: Literal["top_line", "top_cancel"]


class WeekReport(BaseModel):
    week_start: str
    status: Literal["ok", "needs_review", "no_data"]
    reasons: list[str]
    attempts: int
    figures: list[Figure]
    anomalies: list[str]
    violations: list[Violation]
    draft_id: str | None
    history: dict[str, list[float]] = Field(default_factory=dict)
    cause: Cause | None = None
    cancelled_products: list[str] = Field(default_factory=list)
