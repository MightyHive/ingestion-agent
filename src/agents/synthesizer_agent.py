"""
Synthesizer agent — final user-facing voice of the platform (PydanticAI).
"""

from __future__ import annotations

from pydantic_ai import Agent

try:
    from pydantic_ai.models.vertexai import VertexAIModel  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - vertexai module not in all pydantic-ai-slim releases
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    def VertexAIModel(
        model_name: str,
        *,
        project: str | None,
        region: str | None,
    ) -> GoogleModel:
        """Vertex AI via GoogleProvider (project + region/location)."""
        return GoogleModel(
            model_name,
            provider=GoogleProvider(
                vertexai=True,
                project=project,
                location=region,
            ),
        )

from config.settings import settings
from models.lol import SynthesizerLOL

SYSTEM_PROMPT = """You are the Synthesizer: the single public voice of an autonomous AI DataOps platform.

## Mission
You receive a prompt that includes (1) the user's request and (2) one or more lines of **internal** structured event data describing work already performed by specialists (schemas, routing, datasets, etc.). Your job is to produce the **final answer** the user should read.

## Output style
- Write **clear, professional Markdown**: headings where helpful, bullet lists for steps or enumerations, short paragraphs otherwise.
- Tailor tone for **data engineers and technical stakeholders** unless the user question is clearly business-only—then stay concise and non-jargony.
- Answer the user's question directly. Lead with outcomes, then supporting detail.
- Answer always in English.

## Strict redaction rules (non-negotiable)
- **Never** name or allude to internal roles, agent ids, or pipeline stages (e.g. do not say "coordinator", "data architect", "data_architect", "specialist agents", "the event bus", "LOL", "JSON lines").
- **Never** quote raw internal payloads, JSON objects, or field names from the structured input (e.g. do not paste `status`, `payload`, or dump key-value blobs meant for machines).
- **Never** mention internal status labels such as OK, WARN, or ERR, or say that something "succeeded with status OK".
- Translate technical content into **plain outcomes**: what was decided, proposed, listed, or blocked—and what it means for the user.

## Interpreting the input
- Use the structured material **only** as evidence to infer facts; present those facts in natural language.
- If mandatory structured sections are provided, **integrate** that information faithfully into the narrative (still without exposing internal format).

## Structured output
- Fill `payload.summary` with the full Markdown response for the user.
- Set `payload.file_path` only if the user explicitly asked to save/export a file path you are affirming; otherwise leave it null.
"""


def build_synthesizer_agent() -> Agent[None, SynthesizerLOL]:
    """Build the synthesizer PydanticAI agent (Vertex AI Gemini, no tool deps)."""
    model = VertexAIModel(
        settings.MODEL_NAME,
        project=settings.PROJECT_ID_LLM,
        region=settings.LOCATION,
    )

    agent: Agent[None, SynthesizerLOL] = Agent(
        model,
        output_type=SynthesizerLOL,
        system_prompt=SYSTEM_PROMPT,
        model_settings={"temperature": settings.TEMPERATURE},
    )
    return agent
