# Informe de auditoría pre-merge — Rama `Sub-agents-dev` (post-correcciones)

**Alcance:** auditoría de solo lectura del estado actual del repositorio frente a la arquitectura obligatoria (LOL Protocol, patrón dual-layer de herramientas, cableado LangGraph, ejecución dual CLI/API).  
**Fecha de referencia:** 31 de marzo de 2026.

---

## Veredicto final

🟢 **LISTO PARA MERGE**

Los cuatro ejes del checklist de tolerancia cero quedan **cumplidos** en el código revisado. Las salidas `print()` del **camino del grafo** que se ejecuta vía `compiled_graph` (FastAPI u otros importadores) están acotadas a `settings.RUN_MODE == "cli"` donde correspondía. El `input()` bloqueante del coordinador sigue acotado a CLI. No se detectan infracciones que impidan el merge según las cuatro reglas evaluadas.

**Nota de alcance:** más abajo se documentan **observaciones menores** (deuda de diseño, no bloqueadores del checklist).

---

## Resumen de cambios detectados

- **Agentes:** *Software Engineer* (`software_engineer`), *API Researcher* / *Data Sourcer* (`api_researcher`), *Data Architect* (`data_architect`), más coordinador y sintetizador con contratos LOL.
- **Herramientas:** capas puras en `tools/*.py`; registro fino vía PydanticAI; *API Researcher* serializa salidas con `dump_tool_output` en los wrappers (`src/agents/api_researcher_agent.py`).
- **Grafo LangGraph:** `prepare_new_turn` → `coordinator` → fan-out de especialistas → `sync_barrier` → `synthesizer` → `END`; nodos de guardrail y fallo coordinador conservados.
- **API:** `src/api.py` importa `main.compiled_graph` sin arrancar CLI; documentación `RUN_MODE=api`.
- **Frontend:** andamiaje Next.js bajo `frontend/`.
- **Biblioteca de conectores:** `src/connector_library/` (convención de paths en herramientas del Software Engineer).

---

## 1. LOL Protocol (`src/models/lol.py` y salidas)

### Estado

- **`BaseLOL`:** define `status: Literal["OK", "WARN", "ERR"]` y `reason: str` (más `usage` opcional). Cumple el contrato universal.
- **Subclases:** `CoordinatorLOL`, `SynthesizerLOL`, `SoftwareEngineerLOL`, `APIResearcherLOL`, `DataArchitectLOL` heredan `BaseLOL` y fijan `id` con `Literal` y `payload` tipado.
- **`AGENT_NAMES`:** `Literal["data_architect", "software_engineer", "api_researcher"]` (aprox. líneas 7–8). Alineado con `NORMAL_AGENT_NAMES` en `src/agent_registry.py` y con los nodos paralelos del grafo.
- **`TaskStep.target_agent`:** restringido a `AGENT_NAMES`; coherente con la salida estructurada del coordinador.

### Infracciones (bloqueadores — regla 1)

**Ninguna.**

---

## 2. Patrón dual-layer (`src/tools/*.py` y wrappers en `src/agents/`)

### Estado

- **Coordinator / Data Architect:** funciones `_…` devuelven `ToolOutput` (o equivalente); los registradores llaman `dump_tool_output`.
- **API Researcher:** `api_researcher_tools.py` expone `_search_web`, `_read_documentation_url`, `_analyze_json_schema` que devuelven subclases de `ToolOutput` (`SearchWebOutput`, etc.). Los `@agent.tool` en `api_researcher_agent.py` envuelven con `dump_tool_output(_…(...))` dentro de `run_logged_tool` (~254–289).
- **Software Engineer:** funciones públicas `_*` exponen resultados vía `dump_tool_output(...)` sobre modelos de `tool_outputs.py`.

### Secretos

- No se observan API keys, tokens ni contraseñas fijadas en código en las herramientas auditadas; los *stubs* de código generado usan `os.getenv` y nombres de variables.

### Infracciones (bloqueadores — regla 2)

**Ninguna.**

**Observación menor:** `_execute_connector` en `software_engineer_tools.py` no está registrado como `@agent.tool` en el agente (código muerto o preparación futura); no viola el patrón ni el merge.

---

## 3. Cableado LangGraph (`src/main.py`, `src/state.py`)

### Estado

- **`builder.add_node`:** registrados `prepare_new_turn`, `coordinator`, `api_researcher`, `data_architect`, `software_engineer`, `out_of_scope`, `capabilities_help`, `coordinator_failure`, `sync_barrier`, `synthesizer` (aprox. líneas 768–777).
- **Enrutamiento:** `route_from_coordinator` envía listas de `NORMAL_AGENT_NAMES` al fan-out; aristas `for agent_name in NORMAL_AGENT_NAMES: builder.add_edge(agent_name, "sync_barrier")` (~788–789); luego `sync_barrier` → `synthesizer` (~791).
- **`prepare_new_turn`:** reinicia `event_bus`, `task_plan`, `dispatch_targets`, `coordinator_result`, etc., y mantiene `conversation_context` (aprox. líneas 356–381).
- **`event_bus`:** reducer en `state.py` — lista vacía reinicia; actualizaciones no vacías hacen *append* (~13–21).

### Infracciones (bloqueadores — regla 3)

**Ninguna.**

**Observación menor:** `out_of_scope` y `capabilities_help` siguen en el grafo y en `SPECIAL_AGENT_NAMES`, pero un `CoordinatorLOL` válido **no** puede listar esos ids en `tasks` (no están en `AGENT_NAMES`). Por tanto, en la práctica solo serían alcanzables si el estado inyectara `dispatch_targets` sin pasar por el esquema del coordinador. Es deuda de modelo/grafo, no un fallo de las cuatro reglas auditadas.

---

## 4. Ejecución dual (CLI vs API)

### Estado

- **Grafo (`main.py`):**
  - `_run_specialist_node` (~329–330): `print` solo si `settings.RUN_MODE == "cli"` y observabilidad desactivada.
  - `coordinator_node` (~386–390): mismos `print` solo si `settings.RUN_MODE == "cli"`.
  - `out_of_scope_node`, `capabilities_help_node`, `synthesizer_node` (~626–627, 645–646, 670–671): igual.
- **`_cli_loop()`:** `print`, `sys.stdin.read()` y trazas de asistente (~811–889) permanecen **dentro** del bucle CLI; no se ejecutan al importar el módulo.
- **`coordinator_tools.py`:** `input()` y `print` asociados a `_request_human_input` / `_update_ui_status` bajo `settings.RUN_MODE == "cli"` (~72–76, 94–95).
- **Import-safe:** `asyncio.run(_cli_loop())` únicamente bajo `if __name__ == "__main__":` (~903–904).

### `print` en `src/observability.py`

`log_console` solo escribe si la observabilidad local está activada (`-obs` en CLI); la API típica no activa ese flag. No constituye violación del checklist tal como está redactado (no bloquea ni congela el servidor por defecto en modo API).

### Infracciones (bloqueadores — regla 4)

**Ninguna.**

---

## Infracciones arquitectónicas (blockers)

**Ninguna** según las cuatro reglas del checklist con política de tolerancia cero aplicadas al código actual.

---

## Snippets de solución

**No aplicable:** no hay bloqueadores que requieran parches obligatorios antes del merge.

**Mejoras opcionales (fuera del checklist):**

1. **Nodos especiales y contrato LOL:** o bien se amplía `AGENT_NAMES` y `TaskStep` para permitir `out_of_scope` / `capabilities_help`, o bien se eliminan esos nodos del grafo si no hay entrada legítima; o se documenta que solo aplican a estados de prueba inyectados.
2. **`_execute_connector`:** exponerlo como herramienta del Software Engineer o retirarlo si no hay roadmap inmediato.
3. **Scripts auxiliares** (`src/scripts/*.py`): usan `print` en línea de comandos; no afectan el servidor FastAPI.

---

## Tabla resumen

| Regla | Estado |
|-------|--------|
| 1. LOL / `AGENT_NAMES` / `status` + `reason` | Conforme |
| 2. Dual-layer / sin secretos hardcodeados | Conforme |
| 3. LangGraph / barrera / `prepare_new_turn` / reducer | Conforme |
| 4. CLI vs API (`input`/`print` en rutas compartidas, import-safe) | Conforme |

---

*Fin del informe.*
