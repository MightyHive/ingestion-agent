# MDS (Media Data Studio) — Arquitectura objetivo

> Documento técnico para el equipo. Acompaña a [ADR-001](adr/001-multi-agent-to-deterministic-pipeline.md) y a [migration-plan.md](migration-plan.md).

## 0. Equipo y ownership

| Área | Owner | Notas |
|------|-------|-------|
| Backend, arquitectura, API, decisiones de proyecto | Ivan | Lidera el refactor que describe este doc. |
| Frontend (`frontend/`, Next.js) | Mili | **No tocar.** Coordinación necesaria sobre el contrato de `/api/catalog` y cualquier endpoint nuevo de ingesta. |
| SE-agent / artifact store / staging area | Facundo (legacy) | El trabajo de Facundo en el backend pre-2026-05 queda preservado en `legacy-mds-agents`. Ver §11 sobre coordinación. |

---

## 1. Vista de 30.000 pies

`mds` es una plataforma con **dos sub-sistemas** que viven en el mismo repositorio porque comparten infraestructura (LangGraph, persistencia, observabilidad, frontend) y porque los datos que uno produce, el otro los consulta.

```
┌──────────────────────────────────────────────────────────┐
│                          mds                             │
│                                                          │
│  ┌─────────────────────┐    ┌─────────────────────────┐  │
│  │   src/ingestion/    │    │ src/warehouse_explorer/ │  │
│  │                     │    │                         │  │
│  │   Determinístico    │    │   Multi-agente LLM      │  │
│  │   No LLM            │    │   Conversacional        │  │
│  │                     │    │                         │  │
│  │   Pipeline lineal   │    │   LOL Protocol          │  │
│  └──────────┬──────────┘    └────────────┬────────────┘  │
│             │                            │               │
│             └────────────┬───────────────┘               │
│                          │                               │
│                  ┌───────▼────────┐                      │
│                  │  src/shared/   │                      │
│                  │  - LOL types   │                      │
│                  │  - State       │                      │
│                  │  - Persistence │                      │
│                  │  - Observ.     │                      │
│                  └────────────────┘                      │
└──────────────────────────────────────────────────────────┘
                          │
              ┌───────────┴────────────┐
              │                        │
   ┌──────────▼──────────┐   ┌─────────▼──────────┐
   │ connectors-library  │   │ Cliente: BigQuery  │
   │ (git submodule)     │   │ + Secret Manager   │
   │ Cloud Functions     │   │ del cliente        │
   └─────────────────────┘   └────────────────────┘
```

### Responsabilidades

| Sub-sistema | Misión | Tiene LLM | Trigger |
|-------------|--------|-----------|---------|
| `ingestion` | Traer datos de plataformas publicitarias al BigQuery del cliente | No | Request HTTP / scheduler |
| `warehouse_explorer` | Permitir al usuario explorar y entender su data warehouse vía chat | Sí | Conversación |
| `shared` | Infraestructura común | No | Importado por ambos |

---

## 2. Estructura de carpetas

```
mds/
├── README.md
├── docs/
│   ├── adr/
│   │   └── 001-multi-agent-to-deterministic-pipeline.md
│   ├── architecture.md            ← este doc
│   └── migration-plan.md
├── frontend/                      ← Next.js (sin cambios estructurales)
├── connectors-library/            ← git submodule
├── src/
│   ├── api.py                     ← FastAPI / SSE entrypoint
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── graph.py               ← LangGraph del flujo de ingesta
│   │   ├── nodes/
│   │   │   ├── request_validator.py
│   │   │   ├── data_architect.py  ← función Manifest.to_ddl()
│   │   │   ├── connector_runner.py
│   │   │   └── format_response.py
│   │   ├── dispatcher/
│   │   │   ├── base.py            ← Backend ABC
│   │   │   ├── local.py           ← LocalBackend (dev)
│   │   │   └── http.py            ← HTTPBackend (prod, Cloud Functions)
│   │   ├── manifest/
│   │   │   ├── schema.json        ← JSON Schema del manifest.json
│   │   │   ├── loader.py          ← scan + parse de manifests
│   │   │   └── catalog.py         ← endpoint /connectors
│   │   └── auth/
│   │       └── tenant_context.py  ← Secret Manager multi-tenant
│   ├── warehouse_explorer/
│   │   ├── __init__.py
│   │   ├── graph.py               ← LangGraph multi-agente (futuro)
│   │   └── agents/
│   └── shared/
│       ├── __init__.py
│       ├── lol/                   ← BaseLOL, payloads comunes
│       ├── state.py               ← AgentState compartido
│       ├── persistence.py         ← AsyncSqliteSaver wrapper
│       └── observability.py       ← logging, traces, métricas
├── scripts/
│   ├── scaffold_connector.py      ← genera carpeta + manifest.json esqueleto
│   └── deploy_connector.sh        ← deploya CF a un proyecto GCP
└── requirements.txt
```

### Por qué `src/ingestion/` + `src/warehouse_explorer/` + `src/shared/`

- **Separación física = separación mental.** Es imposible importar accidentalmente un agente LLM desde el flujo de ingesta.
- **Onboarding más fácil.** Un dev nuevo abre `src/ingestion/graph.py` y ve los 4 nodos del pipeline en pantalla. No hay confusión con el sistema multi-agente.
- **Tests aislados.** `pytest src/ingestion/` no toca infraestructura LLM.
- **Despliegue independiente posible** en el futuro (si separamos en dos servicios).

---

## 3. Sub-sistema `ingestion`

### 3.1. Grafo de ingesta

```
START
  │
  ▼
┌────────────────────┐
│ request_validator  │  Valida shape: source, type, params, tenant
└────────┬───────────┘  Devuelve LOL OK/ERR.
         │
         ▼
┌────────────────────┐
│  data_architect    │  Lee manifest.json del conector solicitado.
│  (determinístico)  │  Genera DDL Bronze para los fields elegidos.
└────────┬───────────┘  No es agente — es función pura.
         │
         ▼
┌────────────────────┐
│  connector_runner  │  Resuelve auth (TenantContext) → invoca dispatcher.
└────────┬───────────┘  Local o HTTP según runtime. Devuelve records.
         │
         ▼
┌────────────────────┐
│  format_response   │  Aplica DDL a records, escribe en BigQuery (o
└────────┬───────────┘  devuelve preview en modo dry-run).
         │
         ▼
        END
```

Cada nodo sigue el contrato LOL: recibe `current_instruction`, devuelve un payload con `st: OK|WARN|ERR`. La self-correction determinística del LOL Protocol se preserva (router que hace retry hasta N veces ante ERR sin consultar LLM).

### 3.2. El manifest

Cada conector en `connectors-library/` exporta `manifest.json`:

```json
{
  "id": "meta.facebook.ads_insights",
  "version": "1.2.0",
  "name": "Facebook Ads Insights",
  "description": "Daily performance at campaign / ad set / ad level.",
  "endpoint": {
    "cloud_function": "https://<region>-<project>.cloudfunctions.net/meta_facebook_ads",
    "module_path": "meta.facebook.facebook_ads"
  },
  "auth": {
    "type": "bearer_token",
    "secret_name": "meta_access_token"
  },
  "params": {
    "date_start": { "type": "date", "required": true },
    "date_stop":  { "type": "date", "required": true },
    "level":      { "type": "enum", "values": ["campaign", "adset", "ad"], "required": true }
  },
  "available_fields": {
    "campaign_id":   { "type": "STRING", "description": "..." },
    "campaign_name": { "type": "STRING", "description": "..." },
    "impressions":   { "type": "INTEGER" },
    "clicks":        { "type": "INTEGER" },
    "spend":         { "type": "FLOAT64" },
    "date":          { "type": "DATE" }
  },
  "default_partition_field": "date",
  "default_clustering_fields": ["campaign_id"]
}
```

Ese archivo es la single source of truth y lo consumen cuatro consumidores:

1. **Frontend** (`/connectors` y `/connectors/<id>` page).
2. **`Manifest.to_ddl()`** para emitir `CREATE TABLE` BigQuery.
3. **`ConnectorDispatcher`** para saber cómo y dónde invocar.
4. **CI** (validar shape contra `schema.json`).

### 3.3. Dispatcher — dos backends

```python
class Backend(ABC):
    @abstractmethod
    def invoke(self, manifest: Manifest, params: dict, ctx: TenantContext) -> dict: ...

class LocalBackend(Backend):
    """Importa el módulo y llama fetch() in-process. Sólo dev."""

class HTTPBackend(Backend):
    """POST a la Cloud Function descripta en manifest.endpoint.cloud_function.
    Maneja IAM (id_token), retries, timeouts."""

class ConnectorDispatcher:
    def __init__(self, runtime: Literal["local", "http"]):
        self.backend = LocalBackend() if runtime == "local" else HTTPBackend()
    def run(self, manifest, params, ctx) -> dict:
        return self.backend.invoke(manifest, params, ctx)
```

El flag `MDS_RUNTIME` decide. En CI se ejecuta con `local`. En staging/prod, `http`.

### 3.4. Multi-tenancy

Cada cliente tiene su propio proyecto GCP. El flujo de auth es:

```
1. Frontend envía request con tenant_id (cliente).
2. TenantContext.resolve(tenant_id) carga config del cliente desde
   la DB de mds: gcp_project_id, secret_manager_project, service_account_email.
3. Si el cliente no tiene Secret Manager poblado, el frontend recoge
   las credenciales en setup y mds las escribe (acción explícita,
   one-time).
4. ConnectorDispatcher impersona el SA del cliente vía
   google.auth.impersonated_credentials antes de invocar la CF.
5. La CF, ya en el proyecto del cliente, lee credenciales del SM local.
```

Importante: las credenciales **nunca** transitan por mds en payload. Mds solo orquesta llamadas con identidad delegada.

### 3.5. DDL generation (`Manifest.to_ddl()`)

Función pura, sin LLM:

```python
def to_ddl(manifest: Manifest, selected_fields: list[str], tenant: TenantContext) -> str:
    cols = []
    for f in selected_fields:
        spec = manifest.available_fields[f]
        cols.append(f"  {f} {spec.type}")
    table = f"{tenant.gcp_project_id}.{tenant.dataset}.{manifest.id.replace('.', '_')}"
    partition = manifest.default_partition_field
    cluster = ", ".join(manifest.default_clustering_fields)
    return f"""
CREATE TABLE IF NOT EXISTS `{table}` (
{",\\n".join(cols)}
)
PARTITION BY {partition}
CLUSTER BY {cluster};
""".strip()
```

Cualquier decisión "creativa" sobre transformaciones (Silver/Gold) **no vive aquí**. Si en el futuro se necesita razonamiento sobre el modelado, será otro módulo (probablemente dentro de `warehouse_explorer`).

---

## 4. Sub-sistema `warehouse_explorer` (futuro, scaffolding ahora)

No es objeto de la migración inicial, pero se reserva el espacio en `src/warehouse_explorer/` para que la separación quede establecida desde el día uno. La idea actual:

- Multi-agente con LOL Protocol (igual que el `ingestion-agent` original, pero con dominio diferente).
- Agentes: schema_explorer, query_planner, sql_executor, narrator. Definitivos por escribir.
- Acceso de solo lectura a BigQuery del cliente.
- UI en el frontend: chat dedicado, separado del flujo de ingesta.

Lo único que se va a añadir ahora en este sub-sistema es el directorio vacío con un `README.md` explicando que es un placeholder.

---

## 5. Sub-sistema `shared`

Lo que sobrevive de la versión multi-agente original y se eleva a infraestructura común:

| Pieza | Origen | Justificación |
|-------|--------|---------------|
| `BaseLOL`, payload pattern | `models/lol.py` actual | Lo va a usar `warehouse_explorer` |
| `AgentState` | `state.py` actual | Compartido entre grafos |
| `AsyncSqliteSaver` setup | `main.py` actual | Persistencia única para checkpoints |
| Observability (logging, traces) | `observability.py` actual | Visibilidad en ambos sub-sistemas |

Lo que **no** sobrevive: `coordinator_agent.py`, `api_researcher_agent.py`, `software_engineer_agent.py`, `data_architect_agent.py` (en su forma LLM), `synthesizer_agent.py`, `connector_library/` interno, `agent_registry.py`, `synthesis_enrichment.py`, `skills/software-engineer-connector-manager/`.

Todos esos archivos se eliminan de `main` y se preservan en la rama `legacy-mds-agents`.

---

## 6. Frontend — contrato, no código

El frontend es propiedad de Mili. Desde backend solo nos comprometemos con un contrato. Las decisiones de UI son suyas.

| Endpoint | Owner backend | Contrato |
|----------|---------------|----------|
| `GET /api/catalog` | Backend | Devuelve la lista de conectores con manifest válido. Shape definido en `manifest/schema.json`. |
| `GET /api/catalog/{id}` | Backend | Devuelve el manifest completo de un conector. |
| `POST /api/run` | Backend | Ejecuta una ingesta. Body: `{tenant_id, connector_id, params, fields}`. Stream SSE con progreso. |

Antes de modificar cualquiera de estos endpoints o agregar uno nuevo, **acordar el shape con Mili**.

---

## 7. Integración con `connectors-library`

- `connectors-library` se incorpora como **git submodule** en la raíz del repo. Ruta: `./connectors-library/`.
- Los manifests viven dentro de cada carpeta de conector: `connectors-library/meta/facebook/manifest.json`.
- El loader de mds escanea `./connectors-library/**/manifest.json` al arranque, valida contra `manifest/schema.json`, y construye un catálogo en memoria.
- Update workflow: PR sobre `connectors-library`, merge, `git submodule update --remote` en mds, PR de bump.
- Versionado: cada manifest declara su `version`; mds puede pinearse a un commit del submodule.

---

## 8. Despliegue y entornos

| Entorno | Runtime | Backend del dispatcher | Auth |
|---------|---------|------------------------|------|
| Dev local | `python src/api.py` | LocalBackend | Credenciales del dev (env vars) |
| CI | pytest | LocalBackend | Mocks / fixtures |
| Staging | Cloud Run | HTTPBackend | SA de mds-staging impersona SA cliente |
| Prod | Cloud Run | HTTPBackend | Idem, con cliente real |

Las Cloud Functions de cada conector se despliegan **una por una**, en el proyecto GCP de cada cliente, usando `scripts/deploy_connector.sh`. Mds no las gestiona ni las redespliega.

---

## 9. Decisiones que quedan abiertas (post-MVP)

- ¿Pasar `connectors-library` de submodule a Python package en Artifact Registry? (Sí cuando haya 2+ consumidores.)
- ¿Agregar Cloud Workflows / Schedulers en el frontend para configurar runs recurrentes? (Sí, post-MVP.)
- ¿Modelar Silver/Gold dentro de mds o delegarlo a dbt? (Probablemente dbt.)
- ¿Métricas de uso del catálogo para priorizar qué conectores construir? (Trivial de añadir, post-MVP.)

---

## 10. Glosario

- **MDS** — Media Data Studio. Nombre del producto y del repo (post-rename).
- **LOL Protocol** — Lightweight Operation Language. Contrato Pydantic strongly-typed para comunicación inter-nodos en LangGraph.
- **Manifest** — `manifest.json` declarativo, único source of truth de un conector.
- **Dispatcher** — abstracción que decide entre LocalBackend (dev, in-process) y HTTPBackend (prod, Cloud Function).
- **TenantContext** — credenciales y configuración GCP del cliente para el cual se ejecuta una request.
- **Bronze / Silver / Gold** — niveles de la arquitectura medallion en BigQuery.

---

## 11. Coordinación con el trabajo previo de Facundo

En 2026-04 Facundo introdujo en backend:

- `src/pending_deploy/` — artifact store / staging area para conectores generados por el SE-agent.
- Refactor de cómo `api_research` y `table_ddl` viajan como artifacts en lugar de via `event_bus` (commit `b9b9f4f` modifica `src/main.py`).
- "Prepared SE for multiple connectors" en `src/agents/software_engineer_agent.py` y `src/skills/software-engineer-connector-manager/SKILL.md` (commit `427ab59`).

Ese trabajo **se elimina** en la Fase 4 de la migration. La rama `legacy-mds-agents` lo preserva para consulta histórica. La coordinación es prerrequisito de la Fase 4: la decisión de cambiar de dirección debe estar acordada con él antes de borrar.
