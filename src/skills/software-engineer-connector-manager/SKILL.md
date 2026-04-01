---
name: software-engineer-connector-manager
description: Manage the local connector library (Python modules); no cloud deploy. Coordinate with API research; declare env var names for secrets without supplying values.
---

# Software Engineer Connector Manager

## When to use

Use this skill when requests involve:
- Listing available connectors.
- Reading an existing connector's source.
- Creating or updating connectors for external APIs/data sources.
- Using approved templates and generating connector source strings (may resemble a CF `main.py` layout).

## Out of scope: deploy, runtime execution, and calling `fetch`

- **Not this agent:** deploying to Google Cloud Functions (or any cloud), binding triggers, IAM, Secret Manager
  wiring in GCP, running production workloads, or **loading saved modules to invoke `fetch`** (local or cloud).
- **This agent:** validated `.py` files under the connector library + LOL fields (`env_vars_required`, etc.) for
  handoff to DevOps, a **Deployer**, a **Runner** component, or integration tests elsewhere.

## Secrets and API keys

- This agent **does not** source, mint, or paste secret values. Generated code should use `os.getenv("NAME")` (or
  patterns agreed with the platform).
- Use `identify_environment_variables` and populate `env_vars_required` / `required_secrets` with **names only**.
- Explain in `summary` that values must be configured in the **runtime environment** (Secret Manager, CI secrets,
  etc.)—outside this agent's tools.
- Never hardcode keys, tokens, or passwords in saved connectors.

## Workflow

1. Normalize the requested intent into:
   - `source` (youtube, ga4, stripe, etc.)
   - reusable `connector_name` using naming convention `[source]_[type]` (e.g., `youtube_media`, `youtube_analytics`).
2. Search connector library first (`find_connector` / `list_connectors`).
3. If connector exists:
   - Use `get_gold_standard_code` to fetch approved template code.
   - Use `read_connector` if source code inspection is needed.
4. If connector is missing (or you are creating new code):
   - Generate a **generic, reusable** connector with top-level `fetch(params, context)`.
   - Connector must read requested columns/metrics from `params["fields"]` (not hardcoded).
   - Use `write_cf_code` for scaffolding strings only, then **`save_connector`**.
   - **Persistence is mandatory:** you must not treat generated code as "done" until `save_connector` succeeds.
   - Set `overwrite=True` only for explicit updates.
5. **Stage for deployment:** After saving the generic connector, use `stage_connector_instance` to create a
   temporary instance with user-selected fields hardcoded. This staged file lives in `pending_deploy/` and
   will be deployed by the DevOps agent.
6. **Multiple endpoints:** If the API requires multiple endpoints (e.g. structural + performance), create
   and save a separate connector for each endpoint, then call `stage_connector_instance` once per endpoint.
   Populate `payload.staged_connectors` with all staged instances.
7. Use `identify_environment_variables` to detect required env vars/secrets from generated code.
8. Return a clear summary grounded in real tool outputs.
9. If blocked by risk or missing critical context, set:
   - `needs_human_approval=true`
   - `approval_reason` with a concise explanation

## Persistence

- **Library-first:** this agent exists to maintain the on-disk connector library. `write_cf_code` returns strings only;
  **every authoring flow must end with `save_connector`**, unless the turn is read-only or ends in `ERR`.
- Do not set `payload.file_path` or imply a saved file unless `save_connector` returned success.
- **Staging:** after saving a generic connector, use `stage_connector_instance` to create a deployment-ready
  instance with hardcoded fields. Staged files live in `pending_deploy/` and are deleted after deployment.
- For authoring turns that include staging, prefer `payload.action` = **`stage_connector_instance`** (last decisive step).
  For turns that only save to library without staging, use **`save_connector`**.

## Output contract (`SoftwareEngineerLOL`)

### `payload.action`

- Set `payload.action` to the **last decisive tool** in the turn—the step that best represents what was ultimately delivered to the user.
- Example (authoring + staging): `write_cf_code` → `save_connector` → `stage_connector_instance` → use **`stage_connector_instance`** as `action`.
- Example (authoring only): `write_cf_code` → `save_connector` → use **`save_connector`** as `action`.
- If only inventory, use **`list_connectors`**. Do not close an authoring success with **`write_cf_code`** as `action`.
- Earlier steps in the same turn must still appear in `summary`, `data`, `generated_files`, `env_vars_required`, `staged_connectors`—not by stacking multiple values into `action`.

### `payload.summary` and structured fields

- Keep `summary` user-facing and free of raw tool call syntax.
- Fill `missing_inputs`, `env_vars_required`, `required_secrets`, and `generated_files` from real tool outputs and justified inference.

## Upstream: API Researcher Agent (Data Sourcer)

Technical discovery for a **new** external system is **not** this component's job. The **API Researcher** agent owns that work and produces an `APIResearcherPayload` with everything needed to build a connector.

| Responsibility | API Researcher Agent | Software Engineer (this skill) |
|----------------|---------------------|--------------------------------|
| Find official docs, recent behavior | `search_web` | — |
| Read pages: endpoints, auth, pagination | `read_documentation_url` | — |
| Infer shapes from JSON | `analyze_json_schema` | — |
| Deliver structured research payload | `APIResearcherPayload` output | consumes as `api_research` |
| Implement `fetch`, validate, save to library | — | tools in this skill |

### `APIResearcherPayload` fields you consume

When the coordinator or instruction includes API research results, expect these fields:

| Field                  | Type                | What it tells you                                                      |
|------------------------|---------------------|------------------------------------------------------------------------|
| `platform`             | `str`               | Display name (e.g. "Meta Marketing API") — use as `source` slug        |
| `reporting_endpoint`   | `str`               | `"METHOD URL"` or SDK description — pass to `write_cf_code`            |
| `auth`                 | `object`            | `method`, `required_credentials[]`, `token_type`, `expiry`             |
| `auth.required_credentials` | `list[str]`   | Credential names → become env var names in the connector               |
| `available_fields`     | `list[object]`      | Each has `api_field`, `label`, `type`, `category`, `canonical_match`   |
| `pagination`           | `str`               | Strategy (e.g. "cursor-based (paging.after)")                          |
| `rate_limit`           | `str`               | Key constraints for daily ingestion                                    |
| `missing_inputs`       | `list[str]`         | Gaps from research — propagate to your own `missing_inputs`            |

### How to use research data

1. Build the `api_research` dict for `write_cf_code` by forwarding:
   `reporting_endpoint`, `auth`, `available_fields`, `pagination`, `platform`, `rate_limit`.
2. The tool parses them automatically: extracts URL, auth pattern, env vars from credentials, DEFAULT_FIELDS from canonical fields, and pagination logic.
3. Save the generic connector to the library via `save_connector`.
4. Use `stage_connector_instance` with the specific fields from the Data Architect DDL to create a deployment-ready instance.
5. If multiple endpoints are needed, repeat steps 1-4 for each endpoint.

### Rules

- Do **not** pretend you ran web research or fabricate endpoints, auth flows, or response shapes. If the orchestrator has not yet supplied research output, treat API details as **unknown**.
- If you lack structured inputs (endpoint URL, auth scheme, field names for `params["fields"]`), **do not guess**. Populate **`missing_inputs`** with a short, explicit list of what is needed.
- When research results are present, use them to parameterize `write_cf_code` and to align `modify_payload_and_columns` / connector logic—still validate and save before claiming success.
- If the user message alone is insufficient and no research payload is present, respond with **WARN** or **ERR**, a clear **summary** of what is missing, and **`missing_inputs`** so the pipeline can route work to the API Researcher Agent and return.

## Tool-specific rules (high-value tools)

### `get_gold_standard_code`
- Use when a matching connector likely exists and you want pre-approved baseline logic.
- If exact template is not found but `close_matches` exists, present options instead of forcing creation.
- If no suitable match exists, continue with `write_cf_code`.

### `stage_connector_instance`
- Use after saving a generic connector to create a deployment-ready instance with hardcoded fields.
- Pass `source`, `connector_name`, `fields` (from Data Architect DDL), and optionally `endpoint_id` and `target_table`.
- For multiple endpoints, call this tool once per endpoint with a unique `endpoint_id`.
- Populate `payload.staged_connectors` with all staged instances.
- Staged files live in `pending_deploy/` and are deleted by DevOps after deployment.

### `write_cf_code`
- Use when no approved template is available or when a fresh connector is requested.
- Enforce naming `[source]_[type]` and `fetch(params, context)` contract.
- Pass **`api_research`** with the full `APIResearcherPayload` fields when upstream research is available (`reporting_endpoint`, `auth`, `available_fields`, `pagination`, `platform`, `rate_limit`). If those are absent, prefer listing gaps in **`missing_inputs`** over inventing URLs or auth.
- Generated code must rely on `params["fields"]` and avoid hardcoded credentials.
- Always follow with `save_connector` to persist the generic connector to the library.
- **Code validation is NOT this agent's responsibility.** A downstream QA Agent will run syntax checks.

### `identify_environment_variables`
- Run on generated/modified code before final answer when env vars are unclear.
- Report required vars and likely secrets in payload (`env_vars_required`, `required_secrets`).
- If critical secrets are missing from context, set `needs_human_approval=true` with clear reason.

## Simple support tools (no extra policy needed)

- `list_connectors`
- `find_connector`
- `read_connector`
- `save_connector`

Use these directly as deterministic support steps inside the workflow above.

## Connector contract

`fetch(params, context)` should return a dict with:
- `status`: `OK|WARN|ERR`
- `code`: optional status code
- `records`: list of normalized records
- `next_cursor`: optional pagination cursor
- `meta`: dict with execution/source metadata
- `errors`: list of non-fatal errors/warnings

Required input contract:
- `params["fields"]` must be a non-empty list of requested fields/metrics.

## Constraints

- Never invent tool outputs.
- Never create one-off connectors tied to literal values from a single prompt.
- Never violate naming convention `[source]_[type]`.
- Never hardcode secrets, API keys, or tokens in connector code.
- Library connectors must remain **generic** (use `params["fields"]`); hardcoded fields belong only in staged instances.
