# MDS (Media Data Studio) — Plan de migración

> Acompaña a [ADR-001](adr/001-multi-agent-to-deterministic-pipeline.md) y a [architecture.md](architecture.md). Este documento describe **cómo** llegar de la versión actual del repositorio a la arquitectura objetivo, en fases ejecutables y reversibles.

> **Ownership:** backend = Ivan; frontend = Mili (`frontend/`, no se toca en este plan); SE-agent legacy = trabajo de Facundo del 2026-04, preservado en rama `legacy-mds-agents`. Ver §coordinación al final.

---

## 0. Estado de partida (snapshot 2026-05-08)

- Repo `ingestion-agent` con grafo multi-agente activo: `prepare_new_turn → coordinator → fan-out → sync_barrier → synthesizer → END`.
- Agentes LLM vivos: `coordinator_agent.py`, `api_researcher_agent.py`, `data_architect_agent.py`, `software_engineer_agent.py`, `synthesizer_agent.py`.
- `src/connector_library/` interno con código generado por LLM (defectuoso para youtube/tiktok).
- `connectors-library` (repo separado) con conectores reales: Facebook ✅, IG 🔶, Google Ads 🔶, DV360 🔴.
- Frontend Next.js apunta al backend actual.
- Persistencia en `checkpoints.db` (AsyncSqliteSaver).
- No hay tests automatizados que cubran el grafo end-to-end.

## Estrategia de ramas

```
main ─────────────────────────────────────────────────────●  (queda intacto durante todo el refactor)
   │                                                       │
   ├──● legacy-mds-agents (snapshot inmutable, push y bloquear)
   │
   └──● new-mds-deterministic ──● docs ──● Fase 0 ──● Fase 1 ──● ... ──● Fase 7
                                                                            │
                                                                       PR final → main
```

- `main` no recibe nada hasta que el refactor esté validado en staging.
- `legacy-mds-agents` se crea PRIMERO desde `main` (antes de que entre cualquier cambio nuestro). Es el snapshot del sistema multi-agente para consulta histórica y para preservar el trabajo de Facundo (`b9b9f4f`, `427ab59`).
- Toda la migración vive en `new-mds-deterministic`. Cada fase es uno o varios commits coherentes en esa rama. La Fase 4 (borrado) sigue siendo un commit atómico, pero dentro de la branch.
- PR final `new-mds-deterministic → main` cuando el equipo apruebe.

## Principios

1. **`legacy-mds-agents` antes que nada.** Sin ese snapshot, no se hacen cambios.
2. **Documentación primero, código después.** Los tres docs son el primer commit en `new-mds-deterministic`.
3. **Submodule sobre todo.** `connectors-library` se introduce como submodule en la Fase 0 y es la fuente de verdad desde ese momento.
4. **Local primero.** El nuevo flujo se valida con `LocalBackend` antes de tocar Cloud Functions.

---

## Fase -1 — Snapshot legacy + branch de trabajo + docs

**Objetivo:** preservar el sistema multi-agente intacto en `legacy-mds-agents` y arrancar la branch de trabajo `new-mds-deterministic` con los docs como primer commit.

**Estado:** ✅ completa (2026-05-08).

### Tareas

- [x] Escribir `docs/adr/001-multi-agent-to-deterministic-pipeline.md`.
- [x] Escribir `docs/architecture.md`.
- [x] Escribir `docs/migration-plan.md` (este archivo).
- [x] **Alinear con Facundo** sobre el cambio de dirección (su trabajo en `b9b9f4f` y `427ab59` se elimina; preservado en `legacy-mds-agents`). Conversación cerrada el 2026-05-08.
- [x] Compartir el contrato del nuevo `/api/catalog` con Mili → vive en [`docs/api.md`](api.md) como doc vivo (se actualiza en cada fase que toque la API).
- [ ] **Avisar a Mili del rename eventual del repo** (`ingestion-agent` → `mds`, cambia `origin`) → al hacer el merge final.
- [x] Crear `legacy-mds-agents` desde `main` y push. (Branch protection manual en GitHub UI — pendiente de marcar acá cuando se confirme.)
- [x] Crear `new-mds-deterministic` desde `main` y push.
- [x] Primer commit de `new-mds-deterministic`: los tres docs (`9aaed9e`).
- [ ] Renombrar el repo en GitHub `ingestion-agent` → `mds` (post-merge final, no acá). Actualizar `origin` en clones locales: `git remote set-url origin https://github.com/<owner>/mds.git`.
- [ ] Actualizar el `README.md` raíz (en `new-mds-deterministic`, no acá): título, descripción, link a docs. Esto puede ir en cualquier fase posterior.

### Criterios de "done"

- `legacy-mds-agents` existe en remoto, apunta al último commit de `main` antes del refactor, y tiene branch protection.
- `new-mds-deterministic` existe en remoto y tiene los tres docs como primer commit.
- `main` no se modificó.

### Riesgos

- Algún CI o doc externo apunta al nombre viejo del repo. Mitigación: GitHub mantiene redirects automáticos de URLs viejas, pero hay que buscar referencias hardcoded en el código.

---

## Fase 0 — Submodule + scaffolding de carpetas

**Objetivo:** introducir `connectors-library` como submodule y crear el esqueleto vacío de la nueva estructura sin tocar nada del código viejo.

**Estado:** ✅ completa (2026-05-08). Commits: `a19c240` (parte aditiva) + `590d8de` (file moves).

### Tareas

- [x] `git submodule add https://github.com/MightyHive/connectors-library.git ./connectors-library`. Commit del `.gitmodules`. Submodule pinned a `98bdb5d`.
- [x] Crear directorios vacíos con `__init__.py`:
  - `src/ingestion/`, `src/ingestion/nodes/`, `src/ingestion/dispatcher/`, `src/ingestion/manifest/`, `src/ingestion/auth/`
  - `src/warehouse_explorer/`
  - `src/shared/`
- [x] Mover (sin modificar lógica):
  - `src/observability.py` → `src/shared/observability.py`
  - `src/state.py` → `src/shared/state.py`
  - `src/models/lol.py` → `src/shared/lol/__init__.py` (con `src/models/__init__.py` re-exportando hasta Fase 4)
- [x] Ajustar imports en `main.py` y los 5 agentes para que el grafo viejo siga funcionando.
- [x] Escribir `src/ingestion/manifest/schema.json` con el JSON Schema del manifest (ver `docs/architecture.md` §3.2).
- [x] Escribir el primer manifest real: `connectors-library/meta/facebook/manifest.json` y commit en el submodule.
- [x] Escribir `src/warehouse_explorer/README.md` placeholder.

### Criterios de "done"

- [x] `pytest` (lo poco que haya) sigue pasando.
- [x] `python src/api.py` arranca igual que antes (verificación manual de Ivan).
- [x] El frontend funciona idéntico (sigue pegándole al grafo viejo).
- [x] `import src.shared.lol` funciona (smoke test en sandbox).
- [x] `git submodule status` muestra el submodule sano.

### Riesgos

- Imports rotos al mover archivos a `shared/`. Mitigación: hacerlo en un commit pequeño aislado y correr el grafo antes de mergear. → mitigado, los renames se commitearon como rename detection 100% (`-M50%`).

---

## Fase 1 — Manifest loader + catálogo (sin cambiar el flujo aún)

**Objetivo:** que el frontend ya pueda listar el catálogo desde manifests reales, en paralelo al grafo viejo.

**Estado:** ✅ completa (2026-05-08). Loader + catalog + endpoints `/api/catalog` y `/api/catalog/{id}` operativos sobre el submodule.

### Tareas

- [x] Implementar `src/ingestion/manifest/loader.py`:
  - `load_schema()` cacheado (Draft 2020-12)
  - `validate_manifest(data, source)` con `ManifestValidationError` que reporta JSONPointer + mensaje
  - `load_manifest(path)` lee, valida y devuelve dict
  - cache en memoria (`@lru_cache` para el schema, lazy en `Catalog._ensure_loaded`)
- [x] Implementar `src/ingestion/manifest/catalog.py`:
  - `scan_manifests(root)` recorre el submodule e ignora carpetas hidden
  - `Catalog` con `all()`, `get(id)`, `list_summaries()`, `reload()`
  - `summarize_for_listing(manifest)` proyecta al shape del listing
  - `get_default_catalog()` singleton apuntando al submodule
- [x] Exponer endpoints en `src/api.py`:
  - `GET /api/catalog` → `{version, count, connectors: [summary, ...]}`
  - `GET /api/catalog/{id}` → manifest completo o 404
- [x] Smoke test: catálogo descubre `meta_facebook_ad_insights` y la respuesta valida contra el schema.
- [x] **Compartir el contrato del endpoint con Mili** → [`docs/api.md`](api.md) (doc vivo). Incluye `/api/catalog`, `/api/catalog/{id}`, los endpoints legacy del grafo viejo (con su shape SSE), el mapping BigQuery → `FieldType` para el frontend, y un roadmap por fase con qué cambia y cuándo.

### Contrato `/api/catalog` (v1.0)

```json
{
  "version": "1.0",
  "count": 1,
  "connectors": [
    {
      "id": "meta_facebook_ad_insights",
      "name": "Facebook Ads — Ad-level Insights",
      "platform": "meta",
      "connector": "facebook",
      "version": "0.1.0",
      "status": "alpha",
      "description": "...",
      "owner": "Ivan Krawchik",
      "available_fields_count": 31,
      "params_summary": {
        "required": ["fields"],
        "optional": ["days_back", "date_start", "date_stop", "since", "until"],
        "one_of": [["days_back"], ["date_start", "date_stop"], ["since", "until"]]
      }
    }
  ]
}
```

`GET /api/catalog/{id}` devuelve el manifest crudo tal cual lo define `src/ingestion/manifest/schema.json`. El listing de `/api/catalog` se mantiene chico a propósito; los fields completos sólo viajan en el lookup individual.

### Criterios de "done"

- [x] `curl http://localhost:8000/api/catalog` devuelve un JSON con al menos un conector y matchea `manifest/schema.json`.
- [x] Loader rechaza manifests inválidos con detalle de errores (JSONPointer + mensaje del validator).
- [x] Catalog detecta y bloquea ids duplicados.
- [x] Mili tiene el shape documentado en [`docs/api.md`](api.md) para ajustar el frontend cuando le convenga (no es bloqueante para nosotros).
- [x] El grafo viejo sigue intacto y funcional.

### Riesgos

- Discrepancias entre el shape que devolvemos y lo que el frontend espera. Mitigación: el shape se inspiró en `frontend/src/lib/platforms/types.ts` y `frontend/src/lib/stores/connectorStore.ts`. Cuando Mili integre, vamos a tener que mappear `available_fields[*].type` (BigQuery types) ↔ `FieldType` del frontend (`STRING|INTEGER|FLOAT|DATE|BOOLEAN`). Doc en `architecture.md` cuando empiece la integración.

---

## Fase 2 — Nodos determinísticos + grafo nuevo (en paralelo al viejo)

**Objetivo:** construir el grafo nuevo de ingesta sin desconectar el viejo. Ambos coexisten temporalmente.

**Estado:** ✅ completa (2026-05-09). Pipeline `request_validator → data_architect → connector_runner → format_response → END` operativo end-to-end con `LocalBackend`. Coexiste con el grafo viejo (que aún sirve `/api/run`).

### Tareas

- [x] `src/ingestion/nodes/request_validator.py` — función pura `validate_request(manifest_id, params, tenant_id)` que devuelve `NodeLOL` OK con `(manifest, normalised_params, selected_fields, matched_one_of)` o ERR con detalle. Resuelve `one_of` con regla "exactamente un grupo completo".
- [x] `src/ingestion/nodes/data_architect.py` — `to_ddl(manifest, selected_fields) -> (ddl, target_table, columns)`. Sin LLM. Soporta los 13 tipos de BigQuery, partitioning DAY/HOUR/MONTH/YEAR, clustering ≤4 fields, REQUIRED → `NOT NULL`, ARRAY/STRUCT recursivos, tokens del `bronze_pattern`.
- [x] `src/ingestion/auth/tenant_context.py` — `TenantContext.resolve(tenant_id)` carga config del cliente desde JSON local (`~/.mds/tenants.json` o `MDS_TENANTS_FILE`). `assert_satisfies(required_keys)` valida `auth.context_required` del manifest. Hook `set_loader_for_testing` para overrides.
- [x] `src/ingestion/dispatcher/base.py` + `local.py` — `LocalBackend.invoke(manifest, params, ctx)` hace `importlib.import_module(manifest.endpoint.module_path)` y llama `module.fetch(params, context)`. `ConnectorDispatcher` lee `MDS_RUNTIME` (default `local`); HTTP queda explícitamente diferido a Fase 5.
- [x] `src/ingestion/nodes/connector_runner.py` — usa `TenantContext` + `ConnectorDispatcher` y devuelve `NodeLOL`. Mapea `status=partial` → WARN, `status=error` → ERR.
- [x] `src/ingestion/nodes/format_response.py` — formatea records al shape final (`row_count`, `rows_preview` ≤25, `target_table`, `ddl`, `columns`, `meta`, `errors`, `diagnostics`). MVP **no escribe a BigQuery todavía**, solo devuelve el preview.
- [x] `src/ingestion/graph.py` — LangGraph: `request_validator → data_architect → connector_runner → format_response → END` con conditional edges que cortan a END en `last_status="ERR"` (router determinístico, sin self-correction LLM).
- [x] Tests unitarios por nodo + e2e con `LocalBackend` contra el mock connector fixture y validaciones de DDL contra el manifest real de Facebook. **41 tests pasando** en 0.09s.

### Criterios de "done"

- [x] `pytest src/ingestion/tests/` pasa: 41 tests verdes (validador, architect, tenant context, dispatcher, format response, e2e graph).
- [x] E2E happy path: pipeline completa los 4 nodos, devuelve `target_table=bronze.test_mock_connector`, DDL con `id STRING`, `row_count=2`, `tenant_seen` echando el marker del tenant.
- [x] E2E negativo: validación falla → grafo corta a END después del validador (1 nodo ejecutado, no 4).
- [x] E2E partial: connector devuelve `status=partial` → runner emite WARN pero el grafo completa todos los nodos.
- [x] Manifest real de Facebook genera DDL correcto: `PARTITION BY date_start`, `CLUSTER BY account_id, campaign_id`, `spend NUMERIC`, fields `selectable=false` incluidos.
- [x] El grafo viejo sigue siendo el que sirve a `/api/run` (la Fase 3 hace el switch).

### Riesgos

- ~~Incongruencias entre lo que `to_ddl()` produce y lo que BigQuery acepta.~~ Mitigado: tests cubren los 13 tipos de BQ + ARRAY/STRUCT recursivos + REQUIRED → `NOT NULL`. Dry-run contra BQ se hará al deployar la primera CF en Fase 5.
- ~~`importlib` y el path del submodule.~~ Mitigado: `LocalBackend` añade `connectors-library/` al `sys.path` idempotentemente y respeta `MDS_LOCAL_BACKEND_PATHS` para los tests con fixtures.
- Acoplamiento con el shape exacto del `ConnectorResponse`: si los CFs reales emiten un shape distinto al contrato (`{status, code, records, meta, errors}`), `format_response` rompe. Mitigación: smoke test contra el conector de Facebook real apenas Fase 3 esté en staging.

---

## Fase 3 — Entrypoint determinístico público

**Objetivo:** introducir `POST /api/run` como el endpoint estable que ejecuta el grafo determinístico de Fase 2, marcando los endpoints del grafo viejo como deprecated (con headers RFC 8594) para borrarlos en Fase 4.

**Estado:** ✅ completa (2026-05-11, commit pendiente en `setup-mds-phase3.sh`).

### Decisión de diseño (refinada respecto del plan original)

El plan original preveía un único `/api/run` con flag `MDS_USE_LEGACY_GRAPH` para rollback. Se descartó:

- Ivan confirmó que el grafo viejo no se va a volver a usar — la red de seguridad del flag agregaba complejidad sin necesidad real.
- Mili confirmó que adapta el frontend al contrato nuevo (no hay que mantener el shape SSE).
- Separar por endpoint (no por flag) deja el borrado de Fase 4 trivial: se borra el handler completo en vez de tener que cazar lógica condicional regada.

Resultado: `POST /api/run` es **un endpoint nuevo y limpio**, sync JSON. Los SSE viejos siguen en su URL hasta Fase 4, anotados como deprecated.

### Tareas

- [x] Nuevo endpoint `POST /api/run` en `src/api.py` con shape: status 200 (OK/WARN), 400 (`validation_failed`), 502 (`connector_failed`), 500 (`internal`/`pipeline_failed`/`no_formatted_response`); header `X-Request-Id` (uuid4) en toda respuesta.
- [x] Mapping determinístico `failing_node → (status_code, error_key)` (`request_validator → 400`, `connector_runner → 502`) — helper `_error_response` con envelope uniforme.
- [x] `RunRequest` Pydantic: `manifest_id` (string, min_length=1) + `params` (dict, default vacío). Mapea 1:1 al `IngestionState` input.
- [x] tenant_id hardcodeado a `"dev"` (`_PHASE3_TENANT_ID`). Phase 5 lo reemplaza por resolver real.
- [x] Endpoints legacy (`/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{id}/history`) marcados con headers RFC 8594 (`Deprecation: true`, `Sunset: Phase 4`, `Link: </api/run>; rel="successor-version"` o `</api/catalog>` para `/api/templates`). Helper `_legacy_headers`. Docstrings actualizados.
- [x] Tests `src/ingestion/tests/test_api_run.py` con FastAPI `TestClient`: 200 OK, 200 WARN (partial), 400 validation, 400 unknown manifest, 502 connector error, 422 body inválido, headers de deprecation en legacy. El `main` viejo se stubea con `sys.modules` para evitar bootear el grafo LLM durante tests.
- [x] `httpx>=0.27` agregado a `requirements.txt` (lo necesita FastAPI `TestClient`).
- [x] `docs/api.md` actualizado con la nueva sección 3.3 (`/api/run`), tabla del mapa de endpoints, sección 4 reescrita como "deprecated removal Fase 4", roadmap (sección 5) marcado Fase 2 y 3 ✅, changelog entry 2026-05-11.

### Criterios de "done"

- ✅ `POST /api/run` ejecuta el grafo determinístico de Fase 2 y devuelve un JSON sync (sin SSE).
- ✅ Tests E2E del endpoint pasan contra el mock_connector fixture (sin red, sin LLM, sin BQ).
- ✅ Endpoints viejos siguen funcionando pero exponen los headers advisory de deprecation.
- ✅ `docs/api.md` documenta el contrato exacto para Mili (request body, response shapes, status codes, headers).

### Riesgos

- ~~Diferencias sutiles en el shape de la respuesta entre grafos.~~ **Mitigado:** ya no intentamos compatibilidad — el nuevo shape es JSON sync limpio, documentado en `docs/api.md` §3.3. Mili adapta el frontend cuando esté lista.
- ~~`MDS_USE_LEGACY_GRAPH` mal configurado en producción.~~ **Mitigado:** no hay flag — la separación por endpoint elimina la clase de bug por completo.
- **Nuevo riesgo:** un cliente del frontend antiguo sigue golpeando `/api/chat` y no se da cuenta del header `Deprecation`. Mitigación: el header es solo advisory; el endpoint sigue funcionando hasta Fase 4. Antes de Fase 4 verificamos que los logs muestren tráfico cero en `/api/chat` y `/api/submit_input`.

---

## Fase 4 — Borrado del código legacy

**Objetivo:** PR atómico que elimina todo lo que ya no se usa.

**Estado:** ✅ completa (2026-05-11, commit pendiente en `setup-mds-phase4.sh`).

### Decisión revisada (al ejecutar)

- El plan original preveía mantener el flag `MDS_USE_LEGACY_GRAPH` hasta Fase 3 para rollback operacional. En Fase 3 se descartó el flag por completo (separación por endpoint, no por flag), así que en Fase 4 no hay flag que borrar — los handlers viejos simplemente desaparecen.
- Ivan y Facundo cerraron el cambio de dirección antes de Fase 4. El trabajo de Facundo (`b9b9f4f`, `427ab59`) queda preservado en el tag `legacy-mds-agents`. No hubo intención de portar nada a `shared/`.
- Como el refactor vive en `new-mds-deterministic` (no se merge a `main` todavía), el borrado destructivo es seguro: producción sigue corriendo `main` (grafo viejo) hasta el PR final.

### Prerrequisito (bloqueante)

- [x] **Acordado con Facundo el cambio de dirección.** Su trabajo (`b9b9f4f`, `427ab59`: artifact store + temporal staging + prep multi-connector) se elimina como parte de este PR. La rama `legacy-mds-agents` queda creada y verificada antes de mergear.

### Tareas

- [x] Archivos a borrar (vía `git rm -r` en el setup script, ejecutado en el Mac de Ivan):
  - `src/agents/` (entero: `coordinator_agent.py`, `api_researcher_agent.py`, `data_architect_agent.py` LLM, `software_engineer_agent.py`, `synthesizer_agent.py`, `__init__.py`)
  - `src/connector_library/` (entero — el código generado por LLM, no confundir con el submodule `connectors-library/`)
  - `src/pending_deploy/` (artifact store de Facundo)
  - `src/main.py` (grafo viejo + lifespan + `AsyncSqliteSaver`)
  - `src/agent_registry.py`
  - `src/synthesis_enrichment.py`
  - `src/skills/software-engineer-connector-manager/`
  - `src/services/` (revisar caso por caso — todo lo que solo servía al SE-agent)
  - `src/tools/` (`software_engineer_tools.py` se va; nada migra a `shared/` en esta fase)
- [x] `src/api.py` reescrito: sin `lifespan`, sin import de `main`, sin `ChatRequest`/`SubmitRequest`, sin helpers SSE (`_sse_headers`, `_sse_graph_stream`), sin `_legacy_headers`, sin handlers de `/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{id}/history`. Versión bumpeada a `2.0.0`. Solo quedan `RunRequest`, `_error_response`, `/api/run`, `/api/catalog`, `/api/catalog/{id}`.
- [x] `src/ingestion/tests/test_api_run.py`: removido el stub de `main` en `sys.modules` (ya no hace falta — `api` importa limpio); agregados 4 tests parametrizados que verifican `404` para los endpoints viejos.
- [x] `requirements.txt` purgado del stack LLM: removidas `aiosqlite`, `langgraph-checkpoint-sqlite`, `pydantic-ai-slim[*]`, `pydantic-ai-skills`, `google-generativeai`, `langchain-*`, `chromadb`, `python-dotenv`. Sobrevive: `fastapi`, `uvicorn[standard]`, `langgraph`, `pydantic`, `jsonschema`, `pytest`, `httpx`.
- [x] `.gitignore` limpio: removidas reglas para `src/pending_deploy/*.py` y `chroma_db/`; agregadas `.pytest_cache/`, `/tmp/pytest-mds/`; bloque de SQLite leftover anotado como histórico.
- [x] `docs/api.md` actualizado: sección 4 reescrita como "Endpoints eliminados en Fase 4" (sin shapes SSE), tabla del mapa, roadmap §5 con Fase 4 ✅, header de breaking-change reemplazado, changelog entry 2026-05-11.
- [ ] Update del `README.md` raíz: descripción del repo + link a docs. Diferido a una fase posterior (no bloqueante).

### Criterios de "done"

- [x] `pytest src/ingestion/tests/` pasa: 49 tests verdes, incluyendo los 4 nuevos parametrizados de `404`.
- [x] `python -c "import api"` no falla (el módulo ya no depende de `main`).
- [x] `grep -r "from src.agents" src/` no devuelve nada (verificado en smoke embebido del setup script).
- [x] `grep -r "AsyncSqliteSaver\|pydantic_ai\|langchain\|google.generativeai\|chromadb" src/` vacío.
- [x] El árbol de `src/` queda: `api.py`, `ingestion/`, `shared/`, `warehouse_explorer/`. Nada más de los agentes viejos.

### Riesgos

- ~~Dependencias ocultas: algún archivo de `shared/` podría todavía importar agentes.~~ **Mitigado:** smoke embebido en `setup-mds-phase4.sh` corre `grep` recursivo por todos los símbolos del stack viejo antes de commitear.
- Nuevo riesgo (post-Fase 4): si Mili necesita revisar cómo era un shape SSE viejo para terminar la migración, el tag `legacy-mds-agents` lo conserva intacto. Aviso a Mili: ahora `fetch('/api/chat')` da `404`, no `Deprecation: true`. Si todavía hay alguna llamada en `frontend/` que no se migró, va a romper visiblemente — es lo que queremos.

---

## Fase 5 — Producción MVP: HTTPBackend + Cloud Function + Secret Manager (single-project)

**Objetivo:** que mds en producción ejecute conectores reales contra la API del proveedor, con credenciales de múltiples clientes resueltas dinámicamente, y que escriba el resultado a BigQuery — todo dentro de **un único proyecto GCP propio de Monks/mds**.

**Cambio de alcance (2026-05-12):** la versión previa de esta fase asumía un setup multi-project con impersonation cross-project (cada cliente en su propio GCP, mds impersonando el SA del cliente). Se simplificó a single-project para validar el flujo HTTP backend end-to-end primero, sin meterse con la complejidad de IAM cross-project. El aislamiento por GCP de cliente queda **fuera del scope de este refactor**; si más adelante un cliente requiere que sus credenciales no salgan de su nube, se evalúa entonces como un proyecto aparte.

### Setup que asume el MVP

- **Un único proyecto GCP propio** (de Monks/mds). Todo vive ahí.
- **Secret Manager** en ese proyecto con las credenciales de **2 clientes piloto** para DV360. Separación por convención de naming (p. ej. `client_<id>_dv360_<key>`); el `tenant_id` resuelve qué set de secretos leer.
- **Una Cloud Function** deployada en el mismo proyecto, con el código del conector DV360. Misma lógica de fetch que vive en `connectors-library/dv360/`, packageada como CF.
- **BigQuery destino** en el mismo proyecto. Un dataset por cliente (p. ej. `bronze_client_a`, `bronze_client_b`).
- **Conector elegido:** DV360 (no Facebook como decía el plan anterior).
- **El backend NO toca credenciales ni escribe a BigQuery directamente.** Solo coordina: resuelve qué tenant, arma el payload, invoca la CF, mapea la respuesta para el frontend.
- **La CF es quien:** lee credenciales de Secret Manager según el `tenant_id` recibido en el payload, llama a la API de DV360, escribe los records al `target_table` indicado en el payload, y devuelve metadata + preview al backend.

### Flujo de una corrida

1. Frontend manda `POST /api/run` con header `X-Tenant-Id: <client_id>` (Mili agrega un dropdown de clientes) + body `{manifest_id, params}`.
2. Backend resuelve tenant (`TenantContext.resolve(tenant_id)`). Esto carga la config del tenant (nombres de secretos, dataset destino, URL de la CF) — **NO** las credenciales del cliente.
3. Backend ejecuta el grafo determinístico: `request_validator → data_architect (genera DDL + target_table) → connector_runner (con HTTPBackend) → format_response`.
4. `HTTPBackend.invoke` hace `POST` a la URL de la CF con payload `{tenant_id, manifest_id, fields, params, target_table}` — **sin credenciales**.
5. La CF:
   - Lee de Secret Manager las credenciales del tenant (refresh_token, advertiser_id, etc.).
   - Invoca la API de DV360 con esas credenciales.
   - Escribe los records al `target_table` en BigQuery del mismo proyecto.
   - Devuelve al backend `{row_count, rows_preview, target_table, meta, errors, diagnostics}` — **sin la data completa**, solo el preview (25 filas) y la metadata.
6. Backend recibe esa metadata, la mapea al shape de `formatted_response` que el frontend ya espera, y responde al frontend con `200` (o WARN/ERR según `last_status` del grafo).

### Tareas

- [ ] `src/ingestion/dispatcher/http.py` — `HTTPBackend` que POSTea a la URL de la CF. Autenticación interna de GCP (id_token firmado por la SA del backend, validado por la CF). Sin impersonación cross-project (mismo proyecto, alcanza con auth interna).
- [ ] `src/ingestion/auth/tenant_context.py`: hoy lee `~/.mds/tenants.json` / `MDS_TENANTS_FILE`. Pasa a leer de un secreto meta-config en Secret Manager (p. ej. `mds_tenants_config`) que mapea `tenant_id` → `{secrets_prefix, target_dataset, cf_url, …}`. Sigue **NO** leyendo credenciales del cliente — solo nombres/referencias.
- [ ] `src/api.py`: el handler de `/api/run` lee `X-Tenant-Id` del header (en vez de `_DEFAULT_TENANT_ID = "dev"`). Si el header falta, `400 missing_tenant`. **Cambio frontend-facing chico** — coordinar con Mili (dropdown de clientes en la UI).
- [ ] **Código de la Cloud Function** (en `connectors-library/dv360/` o en un repo aparte para "deployable CFs", a definir): recibe el payload, lee Secret Manager, llama DV360, escribe a BigQuery, devuelve preview + metadata.
- [ ] **Setup IAM en el proyecto propio:**
  - SA del backend `mds-backend@…` con `roles/cloudfunctions.invoker` (para invocar la CF).
  - SA de la CF `mds-connector-dv360@…` con `roles/secretmanager.secretAccessor` (para leer credenciales) + `roles/bigquery.dataEditor` sobre los datasets `bronze_client_*` (para escribir).
- [ ] **Secret Manager — carga inicial:** credenciales DV360 de cliente A y cliente B, con la naming convention documentada en un README del proyecto GCP.
- [ ] **BigQuery — preparación:** datasets `bronze_client_a`, `bronze_client_b` creados con location adecuada.
- [ ] **Deploy de la CF de DV360** al proyecto propio (`scripts/deploy_connector.sh dv360` — script a crear).
- [ ] **Manifest de DV360**: `endpoint.cloud_function_name` apunta a la CF deployada en el proyecto propio.
- [ ] **Validación end-to-end:** desde el frontend, con el dropdown de clientes, correr DV360 contra A y B; verificar que las tablas `bronze_client_a.dv360_<…>` y `bronze_client_b.dv360_<…>` quedan pobladas; verificar que el preview en pantalla coincide con las primeras filas de cada tabla.
- [ ] **Actualizar `docs/api.md`**: nuevo header `X-Tenant-Id` obligatorio en `/api/run`, nota de que `/api/run` ahora escribe a BigQuery, removida la nota "no escribe a BQ todavía", changelog entry de Fase 5 ✅.

### Criterios de "done"

- `MDS_RUNTIME=http` en el deploy de producción del backend, y un usuario puede correr DV360 contra Cliente A y Cliente B desde el frontend, viendo el preview + row_count en pantalla y las tablas pobladas en BigQuery.
- Las credenciales nunca pasan por el backend de mds — solo viajan dentro de la CF, leídas directamente de Secret Manager.
- Roll-back: setear `MDS_RUNTIME=local` vuelve al LocalBackend instantáneamente. Si la CF falla, el endpoint devuelve `502 connector_failed` con `X-Request-Id` para trace.

### Riesgos

- **Tamaño del payload de respuesta de la CF.** Cloud Functions tiene un límite de ~32MB en el response. Mitigación: la CF escribe a BQ y devuelve solo metadata + preview (25 filas). La data completa nunca viaja al backend.
- **Cold starts de la CF.** Primera invocación lenta (~2-5s). Mitigación: medir; si molesta UX, `min instances=1`.
- **Secret Manager rate limits.** Una lectura por request es bajo, no preocupa para MVP. Si la CF escala mucho, considerar caché en memoria de la CF (TTL corto).
- **Idempotencia / dobles inserts a BQ.** Si el frontend reintenta una request, podemos escribir los mismos records dos veces. Mitigación para MVP: aceptar duplicados conocidos (el destino es Bronze, la dedup se hace en Silver). Para hardening posterior, agregar un `request_id` idempotente que la CF use como key en un MERGE.

### Fuera del scope (deliberadamente diferido, no es una fase posterior planificada)

- **Multi-project / cliente-en-su-propio-GCP.** El modelo "cada cliente en su propio GCP, mds impersona la SA del cliente vía `google.auth.impersonated_credentials`, IAM cross-project con `roles/iam.serviceAccountTokenCreator`" queda fuera del refactor. Si un cliente eventualmente requiere que sus credenciales no salgan de su nube, se evalúa entonces — pero no bloquea la salida del MVP ni está planificado como Fase 5.5.
- **Tests automatizados de la CF en el ciclo de CI del backend.** El backend testea contra `HTTPBackend` con `httpx` mockeado. La CF se valida con smoke manual en su propio proyecto durante este MVP.

---

## Fase 6 — Migración del resto de conectores

**Objetivo:** llevar todo el catálogo curado a producción.

### Tareas

- [ ] Manifest + Cloud Function deploy + smoke test, uno por conector:
  - [ ] Instagram Insights
  - [ ] Google Ads
  - [ ] DV360 Reports (cuando termine la auth layer)
- [ ] Scaffold script `scripts/scaffold_connector.py` para que añadir uno nuevo sea: clonar carpeta + editar manifest + escribir `<name>.py` + PR.
- [ ] Cada manifest nuevo se publica en `connectors-library` y bumpa el submodule en `mds`. Mili lo verá en el catálogo automáticamente vía `/api/catalog`.

### Criterios de "done"

- Los 4 conectores aparecen en `/api/catalog` y son invocables vía `/api/run`, sirviendo data real.

---

## Fase 7 — Limpieza final y handoff a `warehouse_explorer`

**Objetivo:** dejar el escenario montado para empezar la siguiente capa.

### Tareas

- [ ] Métricas básicas: contador de runs por conector, latencia, tasa de error.
- [ ] Documentar el flujo de "agregar un conector nuevo" en un `connectors-library/CONTRIBUTING.md`.
- [ ] Empezar a poblar `src/warehouse_explorer/` (fuera del scope de este plan).

---

## Mapa de dependencias entre fases

```
-1 (docs + branches)
 │
 ▼
 0 (submodule + scaffolding)
 │
 ▼
 1 (manifest loader + catálogo)
 │
 ▼
 2 (nodos + grafo nuevo en paralelo)
 │
 ▼
 3 (switch del entrypoint)
 │
 ▼
 4 (borrado legacy)        ← punto de no retorno code-wise
 │
 ▼
 5 (HTTPBackend + Cloud Functions en prod)
 │
 ▼
 6 (resto de conectores)
 │
 ▼
 7 (limpieza + handoff)
```

Las fases -1, 0 y 1 son aditivas (no rompen nada). La fase 2 es aditiva pero introduce código que aún no se usa. La fase 3 es la primera operacionalmente significativa. La fase 4 es la única que borra código; se ejecutó en `new-mds-deterministic` (no en `main`), así que producción sigue corriendo el grafo viejo hasta el PR final.

## Roll-back

- En cualquier fase pre-PR-final: roll-back = abandonar `new-mds-deterministic` (no se mergea a `main`). `main` nunca se ensució.
- Fase 3 ya no usa el flag `MDS_USE_LEGACY_GRAPH` (se descartó en favor de separación por endpoint). Si en Fase 4 hace falta volver atrás dentro de la branch, se hace con `git revert` del commit de Fase 4 — el código viejo vive intacto en `legacy-mds-agents`.
- Post-PR-final a `main`: roll-back = `git revert` del merge commit, o checkout de `legacy-mds-agents` si la cosa se complicó. La rama `legacy-mds-agents` es el seguro permanente.

## Estimación informal de esfuerzo

| Fase | Esfuerzo aproximado |
|------|---------------------|
| -1   | 0.5 día (review de docs + admin de GitHub) |
| 0    | 1 día |
| 1    | 1-2 días |
| 2    | 3-5 días (depende del rigor de tests) |
| 3    | 0.5 día + 3-5 días de soak en staging |
| 4    | 0.5 día |
| 5    | 2-3 días (la primera CF y el IAM se llevan el grueso) |
| 6    | 1 día por conector |
| 7    | 1 día |

Total: ~3-4 semanas de trabajo enfocado, distribuibles según prioridades.

---

## Coordinación con el equipo

### Con Mili (frontend)

- **No tocamos código en `frontend/`.** Su trabajo no se bloquea por este refactor.
- En Fase 1 le compartimos el shape de `/api/catalog` y `/api/catalog/{id}` para que pueda alinear el listing del frontend cuando le convenga. Hasta entonces el endpoint viejo sigue funcionando.
- Si la Fase 3 introduce cambios en el shape de `/api/run` (lo intentamos evitar), avisarle con tiempo.

### Con Facundo (co-committer del backend)

- Su trabajo en commits `b9b9f4f` y `427ab59` (artifact store + temporal staging area + prep multi-connector para SE-agent) **se elimina** en la Fase 4.
- La conversación es prerrequisito de la Fase 4, no de las anteriores. Las fases -1 a 3 son aditivas y no destruyen su código.
- El plan B si Facundo ve valor en preservar parte de su trabajo: ese código se puede migrar a `src/shared/` o a `src/warehouse_explorer/` en lugar de borrarse, sin afectar el flujo de ingesta determinístico.
- En cualquier caso, `legacy-mds-agents` mantiene el snapshot completo, así que ningún commit se pierde.
