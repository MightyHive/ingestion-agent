# LOL Protocol moved to src/shared/lol/ as part of Fase 0 of the MDS refactor.
# Re-exported from here for backward compatibility; this whole models/ package
# is scheduled for deletion in Fase 4 (see docs/migration-plan.md).
from shared.lol import (
    BaseLOL,
    TaskStep,
    CoordinatorPayload,
    CoordinatorLOL,
    SynthesizerPayload,
    SynthesizerLOL,
    DataArchitectPayload,
    DataArchitectLOL,
    AGENT_NAMES,
    GeneratedFile,
    SoftwareEngineerPayload,
    SoftwareEngineerLOL,
)

from .tool_outputs import (
    ToolOutput,
    ToolStatus,
    ConnectorRef,
    ConnectorValidationOutput,
    ConnectorListToolOutput,
    ConnectorSearchToolOutput,
    ConnectorReadToolOutput,
    ConnectorValidateToolOutput,
    ConnectorSaveToolOutput,
    GoldStandardCodeToolOutput,
    StageConnectorToolOutput,
    CloudFunctionCodeToolOutput,
    EnvironmentVariablesToolOutput,
    ConnectorRunResult,
    ConnectorExecuteToolOutput,
    to_json_safe,
    dump_tool_output,
)
