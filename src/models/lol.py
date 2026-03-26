"""
LOL Protocol (Lightweight Operation Language)

Pydantic schemas for the contract between agents.
Each agent MUST return an object extending BaseLOL with its own Payload type.
PydanticAI uses Field(description=...) as implicit system prompt hints.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# Extend with coordinator / synthesizer / other specialists as they are added.
AGENT_NAMES = Literal["data_architect"]


# ============================================================
# BASE LOL — Universal inter-agent contract
# ============================================================

class BaseLOL(BaseModel):
    status: Literal["OK", "WARN", "ERR"] = Field(
        description="Operation status: OK (success), WARN (partial success), ERR (failure)"
    )
    reason: str = Field(
        description=(
            "Agent rationale. If status is OK/WARN, explain the logic; if ERR, state the failure cause."
        )
    )
    usage: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Token usage metrics (prompt_tokens, completion_tokens, total_tokens)",
    )


# ============================================================
# COORDINATOR — Plans parallel dispatch
# Add: Payload/LOL per specialist agent (structured output each).
# ============================================================

class TaskStep(BaseModel):
    target_agent: AGENT_NAMES = Field(
        description="Exact name of the agent that will run this task"
    )
    instruction: str = Field(
        description=(
            "Self-contained instruction for the agent. "
            "Must include ALL required context; the agent does NOT read prior chat history. "
            "For ambiguous follow-ups, copy lists or data from the coordinator context here."
        )
    )


class CoordinatorPayload(BaseModel):
    tasks: List[TaskStep] = Field(
        description=(
            "Independent tasks for the current round. "
            "All tasks must be runnable in parallel."
        )
    )


class CoordinatorLOL(BaseLOL):
    id: Literal["coordinator"] = Field(
        default="coordinator",
        description="Fixed identifier for the coordinator agent",
    )
    payload: CoordinatorPayload = Field(
        description="Parallel dispatch plan with tasks for operator agents"
    )


# ============================================================
# SYNTHESIZER — Final answer (template)
# Add: SynthesizerAgent (PydanticAI) with this model as output_type.
# ============================================================

class SynthesizerPayload(BaseModel):
    file_path: Optional[str] = Field(
        default=None,
        description="Path of generated Markdown file if the user asked to export/save a document",
    )
    summary: str = Field(
        description=(
            "Unified final answer from specialist LOL reports on the event bus. "
            "Never mention internal tools. Use bullet points for lists."
        )
    )


class SynthesizerLOL(BaseLOL):
    id: Literal["synthesizer"] = Field(
        default="synthesizer",
        description="Fixed identifier for the synthesizer agent",
    )
    payload: SynthesizerPayload = Field(
        description="Synthesis result: final answer and optional generated file path"
    )


# ============================================================
# DATA ARCHITECT — BigQuery Raw/Bronze modeling and DDL
# ============================================================

class DataArchitectPayload(BaseModel):
    proposed_ddl: Optional[str] = Field(
        default=None,
        description=(
            "Full CREATE TABLE / CREATE SCHEMA DDL proposed for the Raw/Bronze layer, "
            "using BigQuery SQL. Omit or null if the turn only listed datasets or validated inputs without drafting DDL."
        ),
    )
    dataset_target: str = Field(
        description=(
            "Target BigQuery dataset for raw ingestion (e.g. raw_social, raw_youtube). "
            "Must align with Medallion naming: raw/bronze landing zone, not curated silver/gold."
        ),
    )
    action_taken: str = Field(
        description=(
            "Short machine-readable label for what this agent did in this turn, e.g. "
            "'listed_raw_datasets', 'proposed_schema', 'executed_ddl', 'rejected_unsafe_ddl', 'clarification_needed'."
        ),
    )


class DataArchitectLOL(BaseLOL):
    id: Literal["data_architect"] = Field(
        default="data_architect",
        description="Fixed identifier for the Data Architect (data modeler) agent",
    )
    payload: DataArchitectPayload = Field(
        description=(
            "Structured outcome: which dataset was targeted, what action was taken, "
            "and optional DDL text for the event bus / synthesizer."
        ),
    )
