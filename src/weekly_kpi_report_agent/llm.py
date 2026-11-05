import os

import anthropic
from pydantic import BaseModel

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 2000
INPUT_USD_PER_MTOK = 2.0
OUTPUT_USD_PER_MTOK = 10.0
CALL_ERRORS = (
    anthropic.AnthropicError,
    RuntimeError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
)
SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "paragraphs"],
    "additionalProperties": False,
}


class MissingAPIKeyError(RuntimeError):
    pass


class LLMReply(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int


def complete(system: str, user: str) -> LLMReply:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingAPIKeyError
    client = anthropic.Anthropic(timeout=60, max_retries=2)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = (
        "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason != "refusal"
        else ""
    )
    return LLMReply(
        text=text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
