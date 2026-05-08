# ADR-001: De multi-agente con LLM a pipeline determinístico para ingesta

- **Status:** Proposed
- **Date:** 2026-05-08
- **Authors:** Ivan Krawchik
- **Stakeholders:** Facundo Blanco (co-committer del backend), Mili (frontend), liderazgo técnico

---

## Contexto

`ingestion-agent` (que se renombra a `mds` — **Media Data Studio**) nació como una plataforma multi-agente sobre LangGraph + PydanticAI orientada a generar conectores de plataformas publicitarias on-demand. La arquitectura original tenía cinco agentes con LLM (Coordinator, API Researcher, Data Architect, Software Engineer, Synthesizer) coordinados con el LOL Protocol.

En paralelo, el equipo construyó un repositorio independiente — `connectors-library` — con conectores prefabricados, testeados y desplegables como Cloud Functions de GCP, todos respetando el mismo contrato `fetch(params, context) → {status, code, records, meta, errors}`.

Hoy hay una superposición clara: el SE-Agent reinventa, vía LLM, lo que ya existe versionado y probado en `connectors-library`. Las consecuencias observadas son:

1. **Código generado defectuoso.** Ej. `src/connector_library/youtube/youtube_analytics.py` contiene literales como `url = "/" if "" and "" else ""`. La LLM falla en tareas determinísticas (escribir HTTP clients) que no requieren razonamiento.
2. **Costo y latencia altos** en el camino feliz: cada request de ingesta dispara hasta 5 turnos de LLM aún cuando el conector ya existe.
3. **Trazabilidad pobre.** El comportamiento depende del prompt y del modelo; no es reproducible.
4. **Frontera difusa con `connectors-library`.** Dos sources of truth para "cómo hablar con Meta/Google Ads/etc."

A futuro, el equipo necesita una segunda funcionalidad en la misma plataforma: un explorador conversacional del data warehouse del cliente (`warehouse_explorer`). Esa sí es una tarea para la cual los LLM y la arquitectura multi-agente aportan valor real.

## Decisión

Reorganizar la plataforma en dos sub-sistemas con filosofías opuestas pero infraestructura compartida:

1. **`src/ingestion/` — pipeline 100% determinístico.** Sin LLMs en el camino crítico. Consume `connectors-library` directamente.
2. **`src/warehouse_explorer/` — sistema multi-agente.** Hereda LangGraph + LOL Protocol. Es donde el costo de un LLM está justificado.
3. **`src/shared/` — infraestructura común.** State, persistencia, observabilidad, contratos LOL.

El repositorio de GitHub se renombra de `ingestion-agent` a `mds` para reflejar que es una plataforma con múltiples capacidades, no un agente único.

### Cambios concretos en `src/ingestion/`

| Antes (multi-agente LLM) | Después (determinístico) |
|--------------------------|--------------------------|
| Coordinator (LLM) | `request_validator` (función pura) |
| API Researcher (LLM) | Eliminado — la metadata vive en `manifest.json` |
| Data Architect (LLM) | `Manifest.to_ddl()` (función pura) |
| Software Engineer (LLM) | Eliminado — los conectores viven en `connectors-library` |
| Synthesizer (LLM) | `format_response` (función pura) |

Grafo final de ingesta: `request_validator → data_architect_deterministic → connector_runner → format_response → END`.

### Catálogo de conectores

`connectors-library` se consume vía **git submodule**. Cada conector exporta un `manifest.json` declarativo con: nombre, versión, parámetros aceptados, campos disponibles con tipo, requerimientos de auth, y endpoint de la Cloud Function. Ese manifest es la single source of truth que alimenta:

- El catálogo del frontend (`/connectors` listing).
- La generación de DDL (la función `Manifest.to_ddl()` lee `available_fields` del manifest).
- El dispatcher que decide qué conector ejecutar.
- Validaciones de input en CI.

### Multi-tenancy y runtime

- **Producción:** cada conector ejecuta como Cloud Function HTTP-triggered. Las credenciales viven en el Secret Manager del proyecto GCP del cliente. Cross-project IAM permite a `mds` invocar funciones e impersonar service accounts del cliente.
- **Desarrollo:** un `LocalBackend` importa el módulo del conector vía `importlib` y ejecuta `fetch()` in-process. Misma firma, misma respuesta — sin red.

El `ConnectorDispatcher` decide entre backends según un flag de configuración (`MDS_RUNTIME=local|http`).

## Consecuencias

### Positivas

- **Eliminación del fallo más recurrente:** los conectores ya no se generan con LLM, se invocan. El bug de YouTube descrito arriba deja de ser posible por construcción.
- **Costo y latencia colapsan** en el flujo de ingesta. Pasamos de N llamadas a LLM (Coordinator + Operators + Synthesizer) a cero.
- **Reproducibilidad total** del pipeline de ingesta: misma entrada, misma salida, sin variabilidad.
- **Frontera limpia entre repos:** `connectors-library` es el "qué hablar con la API"; `mds` es el "cuándo, para quién, y cómo orquestar".
- **Justificación clara para mantener LangGraph + LOL Protocol:** se preservan como infraestructura compartida que `warehouse_explorer` va a explotar de verdad.
- **Catálogo curado en el frontend:** solo se listan conectores con `manifest.json` real, no posibilidades teóricas.

### Negativas / Costos

- **Esfuerzo de migración no trivial.** Borrar agentes, montar el dispatcher, escribir el primer manifest, deploy de la primera Cloud Function.
- **Pérdida de "flexibilidad infinita".** Hoy el SE-Agent puede inventar un conector nuevo a pedido del usuario; mañana solo se sirven los que están en el catálogo. Esto es una regresión deliberada — preferimos calidad y predictibilidad sobre cobertura ilimitada generada con LLM.
- **Onboarding de un conector nuevo pasa por código humano**, no por una conversación con el agente. Más fricción para añadir; menos riesgo de servir basura.

### Mitigaciones

- Los archivos `src/agents/api_researcher_agent.py`, `software_engineer_agent.py`, `synthesizer_agent.py`, `coordinator_agent.py`, `data_architect_agent.py` (versión LLM), `connector_library/` (interno) y `src/pending_deploy/` (artifact store agregado en commit `b9b9f4f` de Facundo) se eliminan de `main` pero quedan preservados en la rama `legacy-mds-agents`. Consulta histórica garantizada.
- La especificación del manifest (`manifest_schema.json`) y un script `scripts/scaffold_connector.py` reducen la fricción de añadir un conector nuevo.
- El catálogo es expandible: el frontend (UI a cargo de Mili) puede ofrecer un canal explícito "request a connector" como feedback, no como código que se ejecuta.

### Coordinación previa con el equipo

Esta ADR cambia la dirección del backend respecto del trabajo reciente de Facundo (commits `b9b9f4f` y `427ab59` del 2026-04-01: artifact store + temporal staging area + prep multi-connector para el SE-agent). Antes de pasar a la Fase 4 del migration plan (borrado), la decisión debe estar alineada con él: la rama `legacy-mds-agents` preserva su trabajo intacto y el cambio se hace de común acuerdo.

El frontend (`frontend/`) es propiedad de Mili. Esta ADR no toca código de frontend; el único punto de coordinación con UI es el contrato del nuevo endpoint `/api/catalog`.

## Alternativas consideradas

1. **Mantener todos los agentes y agregar una "fast path" determinística cuando el conector ya existe.** Rechazado: dos caminos para la misma funcionalidad multiplican la superficie de bug y dejan al SE-Agent vivo "por si acaso", sin ownership claro.
2. **Eliminar LangGraph y LOL Protocol completamente.** Rechazado: `warehouse_explorer` justifica mantenerlos como infraestructura compartida. Borrarlos ahora obligaría a reintroducirlos.
3. **Empaquetar `connectors-library` como un Python package en Artifact Registry en lugar de submodule.** Considerado para una segunda etapa. El submodule es suficiente mientras hay un solo consumidor.
4. **Mantener el `data_architect` como agente LLM porque "diseñar DDL es razonamiento".** Rechazado tras análisis: el DDL en la capa Bronze es traducción 1-a-1 desde campos seleccionados → tipos BigQuery. Las decisiones de Silver/Gold pueden vivir en otro lado (warehouse_explorer o un módulo separado), no en el flujo crítico de ingesta.

## Referencias

- `docs/architecture.md` — arquitectura objetivo detallada
- `docs/migration-plan.md` — fases de ejecución con criterios de "done"
- `connectors-library/PRESENTATION.md` — estado actual de la librería de conectores
