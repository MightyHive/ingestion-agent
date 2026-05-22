# MDS API — referencia de contratos

> **Audiencia:** Mili (frontend, `frontend/`). Este documento es la fuente de verdad de los endpoints HTTP que sirve el backend de MDS.
> **Estado:** doc vivo. Se actualiza en cada fase del refactor que toque la API. Última edición: **2026-05-11 (Fase 4 ✅)**.
>
> Documentos relacionados: [`migration-plan.md`](migration-plan.md), [`architecture.md`](architecture.md), [`adr/001-multi-agent-to-deterministic-pipeline.md`](adr/001-multi-agent-to-deterministic-pipeline.md).
>
> 🟢 **Estado post-Fase 4:** los endpoints `/api/chat`, `/api/submit_input`, `/api/templates` y `/api/sessions/{id}/history` **fueron eliminados** del backend. El único endpoint de ingesta es `POST /api/run` (sync JSON). Si el frontend todavía les hace fetch va a recibir `404`. Para el historial de cómo eran esos endpoints, ver el tag `legacy-mds-agents` en git.

---

## Índice

1. [Cómo correrlo en local](#1-cómo-correrlo-en-local)
2. [Mapa rápido de endpoints](#2-mapa-rápido-de-endpoints)
3. [Endpoints estables](#3-endpoints-estables)
   - 3.1 [`GET /api/catalog`](#31-get-apicatalog) — listing del catálogo (cards del picker)
   - 3.2 [`GET /api/catalog/{id}`](#32-get-apicatalogid) — manifest completo (ColumnSelector + form de params)
   - 3.3 [`POST /api/run`](#33-post-apirun) — ejecución sync del pipeline de ingesta
   - 3.4 [Mapping de tipos: BigQuery → frontend `FieldType`](#34-mapping-de-tipos-bigquery--frontend-fieldtype)
4. [Endpoints eliminados en Fase 4](#4-endpoints-eliminados-en-fase-4) — qué reemplaza a cada uno
5. [Roadmap por fase](#5-roadmap-por-fase) — qué cambia (o no) en la API en las próximas fases
6. [Glosario rápido](#6-glosario-rápido)
7. [Changelog](#7-changelog)

> **¿Necesitás un endpoint nuevo o un cambio en uno existente?** Decime (Ivan) por Slack o abrime un issue en `ingestion-agent` con el caso de uso (qué pantalla / qué flujo del frontend lo necesita y qué body/response esperás). Me alineo con Facundo y lo metemos en la fase que corresponda. Cambios chicos compatibles los hago en una iteración; breaking changes van bumpeando `version` del response y los anuncio en este doc + Slack antes de mergear.

---

## 1. Cómo correrlo en local

El backend es FastAPI y se levanta desde `src/`:

```bash
cd src
RUN_MODE=api uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

- Base URL en dev: `http://localhost:8000`
- Variable que el frontend ya usa: `NEXT_PUBLIC_API_URL`
- CORS: abierto a todos los orígenes (`allow_origins=["*"]`, `allow_credentials=False`). Para dev no hace falta nada extra.
- Submodule `connectors-library` requerido para los endpoints de catálogo: después de clonar el repo, `git submodule update --init --recursive`.

---

## 2. Mapa rápido de endpoints

| Método | Path | Estado | Notas |
|--------|------|--------|-------|
| POST   | `/api/run`                              | ✅ estable (v1.0)             | Único endpoint de ingesta. Sync JSON. Reemplazó a `/api/chat` + `/api/submit_input`. |
| GET    | `/api/catalog`                          | ✅ estable (v1.0)             | Listing del catálogo. Reemplazó a `/api/templates`. |
| GET    | `/api/catalog/{id}`                     | ✅ estable (v1.0)             | Manifest completo de un conector. |

> ✅ = estable, parte del contrato a largo plazo.
>
> **Endpoints eliminados en Fase 4** (devuelven `404` desde hoy): `/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{session_id}/history`. Ver tag `legacy-mds-agents` si necesitás el historial.

---

## 3. Endpoints estables

### 3.1 `GET /api/catalog`

Lista todos los conectores disponibles en el submodule `connectors-library`. Es el reemplazo determinístico de `/api/templates`. Pensado para el listing del frontend (cada card del picker).

**Request:** sin parámetros.

**Response 200:**

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
      "description": "Daily ad-level performance insights from the Meta Marketing API (Facebook). ...",
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

**Campos del summary (estable v1.0):**

| Campo                       | Tipo                                          | Notas |
|-----------------------------|-----------------------------------------------|-------|
| `id`                        | `string` (snake_case)                         | Clave primaria global. La usamos como path param en `/api/catalog/{id}` y como sufijo en BigQuery (Bronze). |
| `name`                      | `string`                                      | Nombre humano para mostrar en el picker. |
| `platform`                  | `string` (snake_case)                         | Agrupación top-level (`meta`, `google_ads`, `dv360`, …). Útil para tabs en el frontend. |
| `connector`                 | `string` (snake_case)                         | Identificador específico dentro de la plataforma (`facebook`, `ig`, `reports`). |
| `version`                   | `string` (semver)                             | Versión del manifest. Bumpea major si cambia params; minor si agrega fields opcionales. |
| `status`                    | `"alpha"` \| `"beta"` \| `"stable"` \| `"deprecated"` | El frontend puede ocultar no-stable bajo feature flag si querés. |
| `description`               | `string?`                                     | Opcional. Tooltip o subtítulo del card. |
| `owner`                     | `string?`                                     | Opcional. Nombre/equipo responsable. |
| `available_fields_count`    | `integer`                                     | Cantidad de fields que expone el conector. Útil para "tiene 31 columnas" sin pedir el manifest completo. |
| `params_summary.required`   | `string[]`                                    | Nombres de los parámetros obligatorios. |
| `params_summary.optional`   | `string[]`                                    | Nombres de los parámetros opcionales. |
| `params_summary.one_of`     | `string[][]`                                  | Grupos mutuamente excluyentes (ej. `[["days_back"], ["date_start","date_stop"], ["since","until"]]`). El validador del backend exige exactamente uno presente. |

**Status codes:**

- `200` siempre que el catálogo cargue. Si el catálogo está vacío (submodule no inicializado), devuelve `count: 0` y `connectors: []`, no error.
- `500` si algún `manifest.json` del submodule no valida contra `src/ingestion/manifest/schema.json`. El detail incluye el path del manifest defectuoso y los errores del validator (JSONPointer + mensaje). Esto es por diseño: queremos fallar ruidoso si CI deja entrar un manifest inválido.

**Versioning:** el campo top-level `version` arranca en `"1.0"`. Si tenemos que romper la shape, lo bumpamos y te aviso por este doc + un Slack/mail antes.

---

### 3.2 `GET /api/catalog/{id}`

Devuelve el manifest completo de un conector. Se usa cuando el usuario hace click en un card del catálogo y necesitás los `available_fields` con sus tipos para renderizar el `ColumnSelector`.

**Request:** path param `id` = `manifest.id` del listing (snake_case). No acepta query params.

**Response 200:** el manifest tal cual está definido en `src/ingestion/manifest/schema.json`. Para Facebook hoy:

```json
{
  "id": "meta_facebook_ad_insights",
  "name": "Facebook Ads — Ad-level Insights",
  "platform": "meta",
  "connector": "facebook",
  "version": "0.1.0",
  "status": "alpha",
  "description": "...",
  "owner": "Ivan Krawchik",
  "endpoint": {
    "module_path": "meta.facebook.facebook_ads",
    "function_name": "fetch",
    "cloud_function_name": "meta-facebook-insights",
    "cloud_function_region": "us-central1"
  },
  "auth": {
    "context_required": ["ad_account_id", "access_token"],
    "secrets": [
      {"context_key": "access_token", "secret_id": "meta-access-token", "version": "latest"}
    ],
    "scopes": ["ads_read", "read_insights"]
  },
  "params": {
    "required": [
      {"name": "fields", "type": "field_list", "description": "List of available_fields names to retrieve. If empty, all selectable fields are returned."}
    ],
    "optional": [
      {"name": "days_back",  "type": "integer", "default": 14, "minimum": 1, "maximum": 90, "description": "..."},
      {"name": "date_start", "type": "date",    "description": "..."},
      {"name": "date_stop",  "type": "date",    "description": "..."},
      {"name": "since",      "type": "date",    "description": "..."},
      {"name": "until",      "type": "date",    "description": "..."}
    ],
    "one_of": [["days_back"], ["date_start", "date_stop"], ["since", "until"]]
  },
  "available_fields": [
    {"name": "account_id",    "type": "STRING",   "description": "Meta ad account id (without the 'act_' prefix)."},
    {"name": "campaign_name", "type": "STRING"},
    {"name": "date_start",    "type": "DATE",     "selectable": false, "description": "..."},
    {"name": "spend",         "type": "NUMERIC",  "description": "..."},
    {"name": "actions",       "type": "JSON",     "description": "..."}
    /* … 31 en total */
  ],
  "table_naming": {
    "bronze_pattern": "bronze.meta_facebook_ad_insights",
    "partition_field": "date_start",
    "partition_type": "DAY",
    "clustering_fields": ["account_id", "campaign_id"]
  },
  "limits": {
    "max_records_per_call": 200000,
    "max_call_duration_seconds": 540,
    "rate_limit_qps": 5
  },
  "metadata": {
    "api_reference": "https://developers.facebook.com/docs/marketing-api/insights",
    "graph_api_version": "v23.0",
    "response_subkey": "ads"
  }
}
```

**Para el frontend, los bloques que importan son:**

- `available_fields` → renderizar el `ColumnSelector`. Cada item: `{name, type, mode?, description?, items_type?, fields?, selectable?}`. Si `selectable: false`, no lo muestres como opción.
- `params` → renderizar el form de parámetros. Cada `param`: `{name, type, default?, minimum?, maximum?, enum?, pattern?, description?}`. `params.one_of` te dice qué grupos son mutuamente excluyentes.
- `name`, `description`, `version`, `status` → header del flujo.
- Todo lo demás (`endpoint`, `auth`, `secrets`, `table_naming`, `limits`, `metadata`) es para el backend; podés ignorarlo en el frontend salvo que quieras mostrar `metadata.api_reference` como link "Docs oficiales".

**Status codes:**

- `200` con el manifest.
- `404` si no existe un manifest con ese `id`.
- `500` si hay manifests inválidos en el submodule (mismo motivo que `/api/catalog`).

---

### 3.3 `POST /api/run`

Ejecuta el pipeline determinístico de ingesta para un manifest dado, en una sola llamada **sincrónica** (sin SSE, sin estado de sesión). Es el entrypoint estable que reemplaza a `/api/chat` + `/api/submit_input` (que tenían que tomarse varias llamadas + streaming SSE + UI triggers para llegar al mismo resultado).

**Request body:**

```json
{
  "manifest_id": "meta_facebook_ad_insights",
  "params": {
    "fields": ["account_id", "campaign_name", "spend"],
    "days_back": 7
  }
}
```

| Campo         | Tipo                  | Notas |
|---------------|-----------------------|-------|
| `manifest_id` | `string` (snake_case) | Id del manifest, tal como aparece en `GET /api/catalog`. |
| `params`      | `object`              | Parámetros del conector. Debe incluir `fields` (lista de nombres de `available_fields` seleccionables; lista vacía = "todos los selectables"). Las otras keys tienen que matchear el `params` del manifest (validado contra los grupos `required` + `optional` + `one_of`). |

**Response 200 (OK o WARN):**

Body con el shape de `formatted_response` que produce el nodo `format_response`:

```json
{
  "manifest_id": "meta_facebook_ad_insights",
  "tenant_id": "dev",
  "target_table": "bronze.meta_facebook_ad_insights",
  "ddl": "CREATE TABLE `bronze.meta_facebook_ad_insights` (...)",
  "columns": ["account_id", "campaign_name", "spend"],
  "row_count": 3,
  "rows_preview": [
    {"account_id": "act_123", "campaign_name": "Brand", "spend": 12.5}
  ],
  "meta": {"...": "..."},
  "errors": [],
  "diagnostics": {"...": "..."}
}
```

| Campo         | Tipo                       | Notas |
|---------------|----------------------------|-------|
| `manifest_id` | `string`                   | Eco del request. |
| `tenant_id`   | `string`                   | Tenant resuelto. Hoy está hardcodeado a `"dev"` en el handler (`_DEFAULT_TENANT_ID` en `src/api.py`). En Fase 5 va a venir del header `X-Tenant-Id` (el frontend agrega un dropdown de clientes) y se resuelve contra Secret Manager. |
| `target_table`| `string`                   | Tabla destino en BigQuery, con tokens del `bronze_pattern` ya sustituidos. **MVP**: no se ejecuta el insert aún — eso queda para Fase 5. |
| `ddl`         | `string`                   | DDL `CREATE TABLE` determinístico generado por `Manifest.to_ddl()`. Mismo contrato que ya usabas en `SchemaApproval.ddl`. |
| `columns`     | `string[]`                 | Subset solicitado (o todos los selectables si pasaste `fields: []`). |
| `row_count`   | `integer`                  | Total de records traídos. |
| `rows_preview`| `object[]`                 | Primeras 25 filas para preview (configurable en el backend; estable en 25 por ahora). |
| `meta`        | `object`                   | Metadata cruda del conector (`pagination`, `total_count`, etc.). |
| `errors`      | `string[]`                 | Errores no-fatales reportados por el conector. Vacío si todo OK. **En WARN, acá vas a ver el motivo** (ej. `rate_limited_partial`). |
| `diagnostics` | `object`                   | Telemetría adicional (timings, retries, paginación). |

**Response 4xx / 5xx (envelope uniforme):**

```json
{
  "error":      "validation_failed" | "connector_failed" | "internal" | "pipeline_failed" | "no_formatted_response",
  "request_id": "8c4f...",
  "node":       "request_validator" | "connector_runner",
  "reason":     "single-line summary",
  "details":    ["error 1", "error 2"]
}
```

**Status codes:**

| Code | Cuándo                                                                                              | `error`              |
|------|-----------------------------------------------------------------------------------------------------|----------------------|
| 200  | Pipeline terminó OK o WARN.                                                                         | (no aplica — body es el shape de éxito) |
| 400  | `request_validator` falló: faltan params, formato inválido, manifest_id desconocido, grupo `one_of` no satisfecho. | `validation_failed`  |
| 422  | El JSON del body no parsea contra el shape mínimo de `RunRequest` (FastAPI/Pydantic lo intercepta antes del handler). Body: `{detail: <pydantic errors>, request_id}`. **También trae `X-Request-Id`**, vía un exception handler dedicado. | (formato Pydantic estándar + `request_id`) |
| 502  | El conector falló (api unreachable, upstream 5xx, `status=error` reportado por el conector).        | `connector_failed`   |
| 500  | Error inesperado del pipeline (DDL falló, excepción no manejada, no se produjo `formatted_response`). | `internal` / `pipeline_failed` / `no_formatted_response` |

**Headers de toda response:**

- `X-Request-Id`: uuid4 generado en cada request, para tracing. **Loguéalo en el frontend** cuando muestres un error — facilita mucho debug.
- `Content-Type: application/json`.

**Idempotencia y reintentos:** `/api/run` todavía no escribe a BigQuery (eso llega en Fase 5), así que reintentar es seguro. Cuando habilitemos write vamos a agregar un `request_id` idempotente que el cliente puede pasar para evitar dobles inserts (te aviso por este doc cuando llegue).

### 3.4 Mapping de tipos: BigQuery → frontend `FieldType`

El manifest expone tipos crudos de BigQuery (porque el backend los usa para emitir DDL). Tu `FieldType` actual en `frontend/src/lib/platforms/types.ts` es un set más chico. Mapeo recomendado:

| Manifest type (`available_fields[*].type`) | `FieldType` frontend | Notas |
|--------------------------------------------|----------------------|-------|
| `STRING`                                   | `STRING`             | Directo. |
| `INT64`                                    | `INTEGER`            | Directo. |
| `FLOAT64`, `NUMERIC`, `BIGNUMERIC`         | `FLOAT`              | El frontend no necesita distinguir precisión. |
| `BOOL`                                     | `BOOLEAN`            | Directo. |
| `DATE`, `DATETIME`, `TIMESTAMP`, `TIME`    | `DATE`               | Si en algún flujo hace falta separar fecha de timestamp, lo discutimos. |
| `JSON`, `BYTES`, `GEOGRAPHY`, `ARRAY`, `STRUCT` | `STRING`        | "Estructurado / opaque" — mostrar como string en preview hasta que tengamos un widget mejor. |

Si te conviene, te mando un helper `bigqueryTypeToFieldType(t: string): FieldType` para que lo dropees en `frontend/src/lib/platforms/`.

`mode` puede ser `NULLABLE | REQUIRED | REPEATED`. El frontend hoy maneja `NULLABLE | REQUIRED`; cuando aparezca `REPEATED` (arrays), tratamos como `NULLABLE` por ahora.

---

## 4. Endpoints eliminados en Fase 4

Estos endpoints **ya no existen** en el backend a partir de Fase 4 (2026-05-11). Cualquier request los recibe con `404` por la falta del handler — no devuelven headers de deprecation porque el código de los handlers fue borrado junto con el grafo multi-agente.

| Endpoint                                | Sucesor                              | Notas de migración |
|-----------------------------------------|--------------------------------------|--------------------|
| `POST /api/chat`                        | `POST /api/run`                      | El nuevo flujo es sync JSON, sin SSE. Si necesitabas "elegir columnas antes", obtenelo con `GET /api/catalog/{id}` (campo `available_fields`) y mandá los `fields` directo en `/api/run`. |
| `POST /api/submit_input`                | `POST /api/run`                      | No hay estado de sesión; cada llamada es independiente. |
| `GET /api/templates`                    | `GET /api/catalog`                   | Misma idea (lista para el picker), pero contra los manifests reales del submodule en vez del set hardcoded. |
| `GET /api/sessions/{session_id}/history`| (sin sucesor)                        | El flujo determinístico no tiene estado de sesión. Si querés persistir historial en el frontend, hacelo client-side. |

Si te encontrás con un caso que dependía del comportamiento SSE / `ui_trigger` viejo y no ves cómo modelarlo con `/api/run`, decime y lo pensamos.

---

## 5. Roadmap por fase

| Fase | Entrega | Cambios en la API |
|------|---------|-------------------|
| **0** ✅ | Submodule + scaffolding | Sin cambios en la API. |
| **1** ✅ | Manifest loader + catálogo | **Nuevos:** `GET /api/catalog`, `GET /api/catalog/{id}`. |
| **2** ✅ | Nodos determinísticos + grafo nuevo en paralelo | Sin cambios públicos en la API todavía. El nuevo grafo se prueba con `LocalBackend` adentro. |
| **3** ✅ | Entrypoint determinístico | **Nuevo:** `POST /api/run` (sync JSON). **Deprecated** (con headers RFC 8594): `/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{id}/history`. Los deprecated seguían funcionando hasta Fase 4. tenant_id hardcodeado a `"dev"`; se reemplaza por header `X-Tenant-Id` en Fase 5. |
| **4** ✅ | Borrado del legacy | Se borraron `/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{id}/history` del backend + el código de los agentes LLM (`src/agents/`, `src/main.py`, `src/services/`, etc.), el checkpointer `AsyncSqliteSaver`, y todas las dependencias del stack LLM en `requirements.txt`. **Único endpoint POST de ingesta a partir de acá: `/api/run`.** |
| **5** | HTTPBackend + Cloud Function (DV360) en producción, single-project | **Pequeño cambio frontend-facing:** nuevo header `X-Tenant-Id` obligatorio en `/api/run` (Mili agrega un dropdown de clientes y lo manda en cada request). Internamente el dispatcher pasa a invocar una Cloud Function deployada en el GCP propio de mds; la CF lee credenciales de Secret Manager y escribe los records directamente a BigQuery (el backend ya no recibe la data completa, solo preview + row_count). |
| **6** | Resto de conectores (IG, Google Ads, DV360) | El catálogo crece automáticamente — vas a ver más entries en `/api/catalog`. Sin cambios estructurales. |
| **7** | Limpieza final | Doc final del flujo "agregar conector nuevo" en `connectors-library/CONTRIBUTING.md`. |

Cuando algo de esto cambie, edito este doc + te aviso.

---

## 6. Glosario rápido

- **Manifest:** `manifest.json` por conector dentro de `connectors-library/`. Single source of truth: el frontend lo consume para el catálogo, el backend para validar params, generar DDL y dispatchear al runtime correcto. Definido por `src/ingestion/manifest/schema.json` (Draft 2020-12).
- **Catálogo:** colección en memoria de manifests escaneados al levantar el server. Cache lazy; se invalida con un restart del backend (no hay hot-reload por ahora).
- **`LocalBackend` / `HTTPBackend`:** estrategias del dispatcher para ejecutar un conector. Local importa el módulo Python del submodule (dev). HTTP firma id_tokens vía ADC y POSTea a una Cloud Function (prod). El frontend no necesita saber cuál corre, lo decide la env `MDS_RUNTIME=local|http|auto`.
- **`AutoBackend`:** elige por manifest. Si el manifest tiene `endpoint.cloud_function_name`, ruta a HTTP; si no, cae a Local. Es el modo recomendado durante la migración Fase 5 — flipá conectores uno por uno agregando el campo, sin tocar env entre deploys.
- **Tenant:** cliente con su propio proyecto GCP. Cada tenant tiene su Secret Manager y su Service Account. El backend impersona el SA del tenant para ejecutar conectores en su proyecto, sin exponer credenciales en payload.
- **Bronze:** capa raw en BigQuery donde escribimos los records crudos del conector. Definida por `manifest.table_naming`.

---

## 6.1 Variables de entorno relevantes

| Variable | Valores | Default | Para qué sirve |
|---|---|---|---|
| `MDS_RUNTIME` | `local` \| `http` \| `auto` | `local` | Selecciona el backend del dispatcher. `auto` decide por manifest (HTTP si declara `cloud_function_name`, Local en caso contrario). |
| `MDS_CF_BASE_URL` | URL absoluta (sin trailing slash) | unset | Override del host de Cloud Functions. Si está seteado, `HTTPBackend` arma la URL como `{MDS_CF_BASE_URL}/{cloud_function_name}` y **salta el id_token** cuando apunta a loopback (`localhost`, `127.0.0.1`). Útil para el emulador `functions-framework` y smoke tests sin ADC. Si está vacío, se usa la forma canónica `https://{region}-{tenant.gcp_project}.cloudfunctions.net/{name}`. |
| `MDS_LOCAL_BACKEND_PATHS` | paths colon-separados | unset | Roots extra para que `LocalBackend` resuelva conectores de fixtures (tests, CI ad-hoc). |

Notas de seguridad para `HTTPBackend`:

- El payload que viaja al CF es **siempre** `{tenant_id, manifest_id, manifest_version, fields?, target_table?, params}`. Nunca incluye credenciales: hay un scrubber recursivo que descarta cualquier clave con substring `secret`, `token`, `password`, `credential`, `service_account`, `private_key`, `refresh`, `api_key`, etc. (case-insensitive) como defensa en profundidad, además del contrato de que `params` viene del request body del usuario.
- El CF resuelve por sí mismo los secretos del tenant desde Secret Manager con su propia identidad de SA. El backend no necesita leer ni reenviar nada.
- Timeout cliente: `manifest.limits.max_call_duration_seconds + 20s` de buffer, o `560s` por default. Sirve para que el timeout del CF dispare antes que el del cliente y recibamos un error estructurado en vez de un abort de httpx.

---

## 7. Changelog

- **2026-05-19 (Fase 5 / B3 ✅)** — `HTTPBackend` aterrizó (`src/ingestion/dispatcher/http.py`). `MDS_RUNTIME=http` ya no levanta `BackendError`; ahora instancia el backend HTTP. Se agregó `MDS_RUNTIME=auto` (router per-manifest, ver §6) y la variable `MDS_CF_BASE_URL` para apuntar el emulador local o staging. Payload garantiza no leak de credenciales (scrubber + test de regresión). Mapping de errores: `connector_auth_required` (401), `connector_forbidden` (403), `connector_not_found` (404), `connector_timeout` (408/504/`httpx.TimeoutException`), `connector_unreachable` (`httpx.ConnectError`), `connector_upstream_error` (5xx), `connector_invalid_response` (body no-JSON). Nueva dep: `google-auth>=2.30`. El catálogo público no cambia.
- **2026-05-19 (Fase 5 / B1 ✅)** — Manifest de DV360 (`connectors-library/dv360/manifest.json`) agregado al catálogo. 39 fields disponibles (21 dimensiones + 18 métricas), naming alineado a `_normalize_header` del conector. Auth via Service Account (`service_account_json` + `query_id` en context). `endpoint.cloud_function_name = "dv360-fetch"` lista para que `AutoBackend` la rutee a HTTP cuando MDS arranque con `MDS_RUNTIME=auto`.
- **2026-05-11 (Fase 4 ✅)** — **Breaking:** se borraron del backend los handlers de `/api/chat`, `/api/submit_input`, `/api/templates` y `/api/sessions/{session_id}/history` (devuelven `404` desde hoy). Se eliminó todo el código del grafo multi-agente: `src/agents/`, `src/main.py`, `src/services/`, el checkpointer `AsyncSqliteSaver` y el `lifespan` que lo cargaba. `requirements.txt` quedó reducido al stack determinístico (FastAPI + uvicorn + langgraph + pydantic + jsonschema + pytest + httpx). `src/api.py` bumpeado a `2.0.0`. Se agregaron 4 tests parametrizados que verifican el `404` de los endpoints viejos para que cualquier regresión sea cazada por CI. Tag `legacy-mds-agents` apunta al commit pre-Fase 4 por si hay que volver a mirar la implementación histórica.
- **2026-05-11 (Fase 3 ✅)** — Nuevo endpoint estable `POST /api/run` (sync JSON, sin SSE, sin estado de sesión). Marcamos `/api/chat`, `/api/submit_input`, `/api/templates` y `/api/sessions/{id}/history` como **deprecated** con headers RFC 8594 (`Deprecation`, `Sunset: Phase 4`, `Link` al sucesor). Los deprecated siguieron funcionando hasta el borrado en Fase 4. Se descartó el flag `MDS_USE_LEGACY_GRAPH` previsto en la doc anterior — separamos por endpoint, no por flag, para hacer el borrado de Fase 4 más limpio.
- **2026-05-08** — Doc inicial. Endpoints estables: `/api/catalog`, `/api/catalog/{id}` (Fase 1). Documentados también los endpoints legacy del grafo viejo. Mapping BigQuery → `FieldType` propuesto.
