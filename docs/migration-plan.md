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

### Tareas

- [x] Escribir `docs/adr/001-multi-agent-to-deterministic-pipeline.md`.
- [x] Escribir `docs/architecture.md`.
- [x] Escribir `docs/migration-plan.md` (este archivo).
- [x] **Alinear con Facundo** sobre el cambio de dirección (su trabajo en `b9b9f4f` y `427ab59` se elimina; preservado en `legacy-mds-agents`). Conversación cerrada el 2026-05-08.
- [ ] **Avisar a Mili** del rename eventual del repo (cambia origin) y compartir el contrato del nuevo `/api/catalog` para que el frontend pueda alinearse.
- [ ] Crear `legacy-mds-agents` desde `main` y push (con branch protection en GitHub: no permitir push directo después).
- [ ] Crear `new-mds-deterministic` desde `main` y push.
- [ ] Primer commit de `new-mds-deterministic`: los tres docs.
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

### Tareas

- [ ] `git submodule add <url-de-connectors-library> ./connectors-library`. Commit del `.gitmodules`.
- [ ] Crear directorios vacíos con `__init__.py`:
  - `src/ingestion/`, `src/ingestion/nodes/`, `src/ingestion/dispatcher/`, `src/ingestion/manifest/`, `src/ingestion/auth/`
  - `src/warehouse_explorer/`
  - `src/shared/`
- [ ] Mover (sin modificar lógica):
  - `src/observability.py` → `src/shared/observability.py`
  - `src/state.py` → `src/shared/state.py`
  - `src/models/lol.py` → `src/shared/lol/__init__.py` (manteniendo imports relativos)
- [ ] Ajustar imports en `main.py` y agentes para que el grafo viejo siga funcionando.
- [ ] Escribir `src/ingestion/manifest/schema.json` con el JSON Schema del manifest (ver `docs/architecture.md` §3.2).
- [ ] Escribir el primer manifest real: `connectors-library/meta/facebook/manifest.json` y commit en el submodule.
- [ ] Escribir `src/warehouse_explorer/README.md` placeholder.

### Criterios de "done"

- `pytest` (lo poco que haya) sigue pasando.
- `python src/api.py` arranca igual que antes.
- El frontend funciona idéntico (sigue pegándole al grafo viejo).
- `import src.shared.lol` funciona.
- `git submodule status` muestra el submodule sano.

### Riesgos

- Imports rotos al mover archivos a `shared/`. Mitigación: hacerlo en un commit pequeño aislado y correr el grafo antes de mergear.

---

## Fase 1 — Manifest loader + catálogo (sin cambiar el flujo aún)

**Objetivo:** que el frontend ya pueda listar el catálogo desde manifests reales, en paralelo al grafo viejo.

### Tareas

- [ ] Implementar `src/ingestion/manifest/loader.py`:
  - `scan_manifests(root: Path) -> list[Manifest]`
  - validación contra `schema.json`
  - cache en memoria
- [ ] Implementar `src/ingestion/manifest/catalog.py` y exponer endpoints `GET /api/catalog` y `GET /api/catalog/{id}` en `src/api.py`.
- [ ] **Compartir el contrato del endpoint con Mili** (shape de respuesta, ejemplos). El cambio del frontend para consumirlo lo hace ella; nosotros solo entregamos la API estable.
- [ ] Smoke test: `curl /api/catalog` devuelve al menos el manifest de Facebook con el shape acordado.

### Criterios de "done"

- `curl http://localhost:8000/api/catalog` devuelve un JSON con al menos un conector y matchea `manifest/schema.json`.
- Mili tiene el shape documentado para ajustar el frontend cuando le convenga (no es bloqueante para nosotros).
- El grafo viejo sigue intacto y funcional.

### Riesgos

- Discrepancias entre el shape que devolvemos y lo que el frontend espera. Mitigación: definir el `schema.json` con Mili antes de escribirlo, o mirar `frontend/src/lib/platforms/types.ts` y `frontend/src/lib/stores/connectorStore.ts` para inferir el contrato esperado.

---

## Fase 2 — Nodos determinísticos + grafo nuevo (en paralelo al viejo)

**Objetivo:** construir el grafo nuevo de ingesta sin desconectar el viejo. Ambos coexisten temporalmente.

### Tareas

- [ ] `src/ingestion/nodes/request_validator.py` — función pura, devuelve LOL OK con `(source, type, params, fields, tenant_id)` validado o ERR con detalle.
- [ ] `src/ingestion/nodes/data_architect.py` — implementa `Manifest.to_ddl(manifest, selected_fields, tenant) -> str`. Sin LLM.
- [ ] `src/ingestion/auth/tenant_context.py` — `TenantContext.resolve(tenant_id)` carga config del cliente. Stub inicial: lee de un YAML local en dev.
- [ ] `src/ingestion/dispatcher/base.py` + `local.py` — `LocalBackend.invoke(manifest, params, ctx)` hace `importlib.import_module(manifest.endpoint.module_path)` y llama `module.fetch(params, context)`.
- [ ] `src/ingestion/nodes/connector_runner.py` — usa `TenantContext` + `ConnectorDispatcher(runtime="local")` y devuelve LOL.
- [ ] `src/ingestion/nodes/format_response.py` — formatea records al shape final que espera el frontend; en MVP **no escribe a BigQuery todavía**, solo devuelve el preview.
- [ ] `src/ingestion/graph.py` — LangGraph: `request_validator → data_architect → connector_runner → format_response → END`. Reuse del router de self-correction del LOL Protocol.
- [ ] Tests unitarios por nodo + un test end-to-end con LocalBackend contra el conector de Facebook (o un mock fixture).

### Criterios de "done"

- `pytest src/ingestion/` pasa con un caso end-to-end Facebook → DDL + records.
- El grafo viejo sigue siendo el que sirve a `/api/run` (todavía).

### Riesgos

- Incongruencias entre lo que `Manifest.to_ddl()` produce y lo que BigQuery acepta. Mitigación: validar el DDL con el client de BQ en modo dry-run en el test.
- `importlib` y el path del submodule. Asegurarse de que `connectors-library/` esté en el `sys.path` (vía `pyproject.toml` o setup explícito).

---

## Fase 3 — Switch del entrypoint público

**Objetivo:** redirigir el tráfico real al grafo nuevo. Punto de no retorno operacional, pero el código viejo sigue en el repo.

### Tareas

- [ ] En `src/api.py`, cambiar el handler de `/api/run` para invocar `src/ingestion/graph.py`.
- [ ] Mantener una flag `MDS_USE_LEGACY_GRAPH=1` que permita volver al viejo si algo explota en staging.
- [ ] Smoke test manual desde el frontend: pedir Facebook insights, verificar que viene la respuesta correcta.
- [ ] Observability: confirmar que las trazas del grafo nuevo aparecen y que el `checkpoints.db` se sigue poblando.

### Criterios de "done"

- En staging, el flujo de ingesta de Facebook funciona vía el grafo nuevo.
- `MDS_USE_LEGACY_GRAPH=1` permite roll-back instantáneo.
- No hay diferencias funcionales para el usuario.

### Riesgos

- Diferencias sutiles en el shape de la respuesta entre grafos. Mitigación: capturar respuestas del grafo viejo antes del switch como fixtures y comparar.

---

## Fase 4 — Borrado del código legacy

**Objetivo:** PR atómico que elimina todo lo que ya no se usa.

### Prerrequisito (bloqueante)

- [ ] **Acordado con Facundo el cambio de dirección.** Su trabajo (`b9b9f4f`, `427ab59`: artifact store + temporal staging + prep multi-connector) se elimina como parte de este PR. La rama `legacy-mds-agents` debe estar creada y verificada antes de mergear.

### Tareas

- [ ] Archivos a borrar:
  - `src/agents/coordinator_agent.py`
  - `src/agents/api_researcher_agent.py`
  - `src/agents/data_architect_agent.py` (versión LLM)
  - `src/agents/software_engineer_agent.py`
  - `src/agents/synthesizer_agent.py`
  - `src/agents/__init__.py` (queda vacío o se elimina)
  - `src/connector_library/` (entero — el código generado por LLM, no el submodule `connectors-library/`)
  - `src/pending_deploy/` (artifact store, agregado en commit `b9b9f4f` de Facundo)
  - `src/main.py` (grafo viejo) — o se reduce a glue mínimo si `src/ingestion/graph.py` lo absorbe todo
  - `src/agent_registry.py`
  - `src/synthesis_enrichment.py`
  - `src/skills/software-engineer-connector-manager/`
  - `src/tools/` (revisar caso por caso — `software_engineer_tools.py` se va; lo que sirva al `warehouse_explorer` migra a `src/shared/`)
- [ ] Eliminar la flag `MDS_USE_LEGACY_GRAPH` de `src/api.py`.
- [ ] Eliminar dependencias del `requirements.txt` que solo servían a los agentes de ingesta (PydanticAI puede quedarse para `warehouse_explorer`).
- [ ] Update del `README.md` raíz: descripción del repo (mds = Media Data Studio), link a los docs.
- [ ] Verificar que `legacy-mds-agents` tiene todo lo que se borra (smoke: `git diff legacy-mds-agents new-mds-deterministic -- src/agents/ src/pending_deploy/ src/connector_library/` debería listar exactamente los archivos eliminados).

### Criterios de "done"

- `git diff legacy-mds-agents new-mds-deterministic` muestra exactamente lo que esperamos (todo el código eliminado está presente en legacy y ausente en new-mds-deterministic).
- `pytest` pasa.
- Staging (corriendo `new-mds-deterministic`) funciona sin la flag.
- El árbol de `src/` es: `api.py`, `ingestion/`, `warehouse_explorer/`, `shared/`. Nada más.

### Riesgos

- Dependencias ocultas: algún archivo de `shared/` podría todavía importar agentes. Mitigación: un grep final por `from src.agents` antes del merge.

---

## Fase 5 — Producción: HTTPBackend + Secret Manager + Cloud Functions

**Objetivo:** que mds en producción ejecute conectores reales en proyectos GCP de clientes.

### Tareas

- [ ] `src/ingestion/dispatcher/http.py` — HTTPBackend que firma id_tokens y POSTea a la URL del CF.
- [ ] Wiring de impersonación: `TenantContext` carga el SA del cliente y `HTTPBackend.invoke` usa `google.auth.impersonated_credentials`.
- [ ] `TenantContext.resolve()` ya no lee YAML — pasa a leer de la DB de mds (o Secret Manager de mds).
- [ ] Permission setup en GCP del cliente: SA de mds-prod tiene `roles/cloudfunctions.invoker` + `roles/iam.serviceAccountTokenCreator` sobre el SA del cliente.
- [ ] Deploy de la primera CF en el proyecto del primer cliente real: `scripts/deploy_connector.sh meta/facebook <project-id>`.
- [ ] El manifest del conector apunta al endpoint deployado.
- [ ] Validar en staging que `MDS_RUNTIME=http` ejecuta vía CF y devuelve los mismos records que `MDS_RUNTIME=local`.

### Criterios de "done"

- En producción, `MDS_RUNTIME=http` y un cliente real ejecuta Facebook insights vía CF.
- Las credenciales del cliente nunca pasaron por mds.
- Logs de la CF aparecen en el proyecto del cliente, no en mds.

### Riesgos

- IAM cross-project es delicado. Mitigación: un cliente piloto, runbook documentado, escalación clara.
- Cold starts de las CFs. Mitigación: medir latencias; si es problema, considerar min instances.

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

Las fases -1, 0 y 1 son aditivas (no rompen nada). La fase 2 es aditiva pero introduce código que aún no se usa. La fase 3 es la primera operacionalmente significativa. La fase 4 es la única que borra código y debería hacerse después de al menos una semana en staging con el grafo nuevo.

## Roll-back

- En cualquier fase pre-PR-final: roll-back = abandonar `new-mds-deterministic` (no se mergea a `main`). `main` nunca se ensució.
- Fase 3 (con la flag `MDS_USE_LEGACY_GRAPH=1` activa): roll-back operacional inmediato sin tocar git.
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
