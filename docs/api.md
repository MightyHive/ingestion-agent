# MDS API — referencia de contratos

> **Audiencia:** Mili (frontend, `frontend/`). Este documento es la fuente de verdad de los endpoints HTTP que sirve el backend de MDS.
> **Estado:** doc vivo. Se actualiza en cada fase del refactor que toque la API. Última edición: **2026-05-11 (Fase 3 ✅)**.
>
> Documentos relacionados: [`migration-plan.md`](migration-plan.md), [`architecture.md`](architecture.md), [`adr/001-multi-agent-to-deterministic-pipeline.md`](adr/001-multi-agent-to-deterministic-pipeline.md).
>
> ⚠️ **Breaking change en Fase 3:** los endpoints `/api/chat`, `/api/submit_input`, `/api/templates` y `/api/sessions/{id}/history` quedan **deprecated** y serán **eliminados en Fase 4**. El reemplazo es `POST /api/run` (sync JSON, sin SSE, sin estado de sesión). Cuando puedas, migrá el frontend a `/api/run`.

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

| Método | Path | Estado | Reemplaza a |
|--------|------|--------|-------------|
| POST   | `/api/run`                              | ✅ estable (v1.0)             | reemplaza `/api/chat` + `/api/submit_input` |
| GET    | `/api/catalog`                          | ✅ estable (v1.0)             | reemplaza `/api/templates` |
| GET    | `/api/catalog/{id}`                     | ✅ estable (v1.0)             | sin equivalente legacy |
| GET    | `/api/templates`                        | 🔴 deprecated — removal Fase 4 | usar `/api/catalog` |
| POST   | `/api/chat`                             | 🔴 deprecated — removal Fase 4 | usar `/api/run` |
| POST   | `/api/submit_input`                     | 🔴 deprecated — removal Fase 4 | usar `/api/run` |
| GET    | `/api/sessions/{session_id}/history`    | 🔴 deprecated — removal Fase 4 | sin sucesor (el nuevo flujo no tiene estado de sesión) |

> ✅ = estable, parte del contrato a largo plazo.
> 🔴 = se borra en Fase 4. Mientras tanto sigue funcionando, pero las responses traen los headers `Deprecation: true` y `Sunset: Phase 4` (RFC 8594) como aviso. El header `Link` apunta al sucesor.

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
| `tenant_id`   | `string`                   | Tenant resuelto. En Fase 3 está hardcodeado a `"dev"`. En Fase 5 viene del header `X-Tenant-Id`. |
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
| 422  | El JSON del body no parsea contra el shape mínimo de `RunRequest` (FastAPI/Pydantic lo intercepta antes del handler). | (formato Pydantic estándar) |
| 502  | El conector falló (api unreachable, upstream 5xx, `status=error` reportado por el conector).        | `connector_failed`   |
| 500  | Error inesperado del pipeline (DDL falló, excepción no manejada, no se produjo `formatted_response`). | `internal` / `pipeline_failed` / `no_formatted_response` |

**Headers de toda response:**

- `X-Request-Id`: uuid4 generado en cada request, para tracing. **Loguéalo en el frontend** cuando muestres un error — facilita mucho debug.
- `Content-Type: application/json`.

**Idempotencia y reintentos:** `/api/run` no escribe a BigQuery en Fase 3, así que reintentar es seguro. Cuando habilitemos write en Fase 5 vamos a agregar un `request_id` idempotente que el cliente puede pasar para evitar dobles inserts (te aviso por este doc cuando llegue).

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

## 4. Endpoints deprecated (removal en Fase 4)

Estos endpoints siguen sirviendo al grafo multi-agente viejo. **Se borran completos en Fase 4** (junto con el código de los agentes LLM). Mientras tanto siguen funcionando para que tengas tiempo de migrar el frontend a `/api/run`.

Todos exponen los headers advisory:

```
Deprecation: true
Sunset: Phase 4
Link: </api/run>; rel="successor-version"
```

(`/api/templates` apunta a `/api/catalog` en su `Link`.) Estos headers son aviso, no bloquean nada — el endpoint sigue respondiendo normal.

> **Por qué los borramos:** el grafo nuevo es sincrónico, determinístico y sin estado de sesión. No hay equivalente directo entre "SSE con `ui_trigger`" del viejo y "JSON sync" del nuevo. La forma cómoda de migrar es: una llamada `/api/run` por intento; si necesitás "pedirle al usuario que elija columnas antes", hacés ese flow en el cliente (con `GET /api/catalog/{id}` para los `available_fields`) y después llamás `/api/run` con los `fields` ya elegidos.

### 4.1 `GET /api/templates` (deprecated)

Devuelve un set hardcoded de templates de paid media:

```json
{
  "templates": [
    {"id": "tiktok",     "name": "TikTok Ads", "category": "Paid Media", "status": "active"},
    {"id": "meta",       "name": "Meta Ads",   "category": "Paid Media", "status": "active"},
    {"id": "google-ads", "name": "Google Ads", "category": "Paid Media", "status": "active"}
  ]
}
```

### 4.2 `POST /api/chat` (deprecated, SSE)

Arranca un turno del grafo viejo.

**Request body:**

```json
{
  "session_id": "string (LangGraph thread_id)",
  "message":    "string (user query)"
}
```

**Response:** `text/event-stream` (SSE). Cada evento es `data: <json>\n\n`. Headers:

```
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

**Eventos SSE que emite (en orden):**

1. **Connection establecido**
   ```json
   {"type": "connection", "status": "connected"}
   ```

2. **Progreso de cada nodo del grafo** (uno por nodo que se ejecuta):
   ```json
   {"type": "progress", "node": "coordinator"}
   ```

3. **Error durante el stream** (si algo explota mid-grafo):
   ```json
   {"type": "error", "detail": "<mensaje>"}
   ```

4. **Estado final** (último evento, cierra el stream):
   ```json
   {
     "type": "final",
     "response_text": "string",
     "requires_human_input": true,
     "ui_trigger": {
       "component": "ColumnSelector" | "SchemaApproval",
       "message": "string?",
       "data": { /* depende del component */ }
     },
     "session_id": "string"
   }
   ```

**Variantes de `ui_trigger.data` que emite hoy el grafo:**

- `component: "SchemaApproval"`:
  ```json
  {
    "ddl": "CREATE TABLE ...",
    "columns": [
      {"field_name": "...", "type": "STRING", "mode": "NULLABLE", "description": "..."}
      /* … */
    ],
    "tableName": "Pending Schema"
  }
  ```
- `component: "ColumnSelector"`:
  ```json
  {"available_fields": ["account_id", "campaign_name", ...]}
  ```

### 4.3 `POST /api/submit_input` (deprecated, SSE)

Reanuda el grafo viejo después de un input humano (selección de columnas, aprobación de schema, etc).

**Request body:**

```json
{
  "session_id": "string (mismo thread_id que /api/chat)",
  "user_input": "string | { message?: string, text?: string, user_message?: string, columns_selected?: string[], ... }"
}
```

Si pasás un dict, el backend prioriza `message` → `text` → `user_message` para extraer el texto. Si ninguno está, lo serializa como JSON.

**Response:** mismo formato SSE que `/api/chat`.

### 4.4 `GET /api/sessions/{session_id}/history` (deprecated)

Devuelve el state checkpointeado de un thread sin correr el grafo.

**Response 200:**

```json
{
  "session_id": "string",
  "conversation_context": [/* turnos previos */],
  "event_bus": [/* eventos de los agentes */],
  "artifacts": {/* k/v producido por el grafo */},
  "is_paused": true
}
```

**Status codes:**

- `200` si la sesión existe.
- `404` si no se encuentra o está vacía.

`is_paused: true` indica que el grafo está esperando input humano (hay nodos pendientes).

---

## 5. Roadmap por fase

| Fase | Entrega | Cambios en la API |
|------|---------|-------------------|
| **0** ✅ | Submodule + scaffolding | Sin cambios en la API. |
| **1** ✅ | Manifest loader + catálogo | **Nuevos:** `GET /api/catalog`, `GET /api/catalog/{id}`. |
| **2** ✅ | Nodos determinísticos + grafo nuevo en paralelo | Sin cambios públicos en la API todavía. El nuevo grafo se prueba con `LocalBackend` adentro. |
| **3** ✅ | Entrypoint determinístico | **Nuevo:** `POST /api/run` (sync JSON). **Deprecated** (con headers RFC 8594): `/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{id}/history`. Los deprecated siguen funcionando hasta Fase 4. tenant_id hardcodeado a `"dev"`; se reemplaza por header `X-Tenant-Id` en Fase 5. |
| **4** | Borrado del legacy | Se borran `/api/chat`, `/api/submit_input`, `/api/templates`, `/api/sessions/{id}/history` del backend + el código de los agentes LLM. **Único endpoint POST de ingesta a partir de acá: `/api/run`.** |
| **5** | HTTPBackend + Cloud Functions en producción | Sin cambios en la API frontend-facing. Cambios internos: el dispatcher empieza a invocar Cloud Functions del cliente con SA impersonation. Para el frontend es transparente. |
| **6** | Resto de conectores (IG, Google Ads, DV360) | El catálogo crece automáticamente — vas a ver más entries en `/api/catalog`. Sin cambios estructurales. |
| **7** | Limpieza final | Doc final del flujo "agregar conector nuevo" en `connectors-library/CONTRIBUTING.md`. |

Cuando algo de esto cambie, edito este doc + te aviso.

---

## 6. Glosario rápido

- **Manifest:** `manifest.json` por conector dentro de `connectors-library/`. Single source of truth: el frontend lo consume para el catálogo, el backend para validar params, generar DDL y dispatchear al runtime correcto. Definido por `src/ingestion/manifest/schema.json` (Draft 2020-12).
- **Catálogo:** colección en memoria de manifests escaneados al levantar el server. Cache lazy; se invalida con un restart del backend (no hay hot-reload por ahora).
- **`LocalBackend` / `HTTPBackend`:** estrategias del dispatcher para ejecutar un conector. Local importa el módulo Python del submodule (dev). HTTP firma id_tokens y POSTea a una Cloud Function (prod). El frontend no necesita saber cuál corre, lo decide la env `MDS_RUNTIME=local|http`.
- **Tenant:** cliente con su propio proyecto GCP. Cada tenant tiene su Secret Manager y su Service Account. El backend impersona el SA del tenant para ejecutar conectores en su proyecto, sin exponer credenciales en payload.
- **Bronze:** capa raw en BigQuery donde escribimos los records crudos del conector. Definida por `manifest.table_naming`.

---

## 7. Changelog

- **2026-05-11 (Fase 3 ✅)** — Nuevo endpoint estable `POST /api/run` (sync JSON, sin SSE, sin estado de sesión). Marcamos `/api/chat`, `/api/submit_input`, `/api/templates` y `/api/sessions/{id}/history` como **deprecated** con headers RFC 8594 (`Deprecation`, `Sunset: Phase 4`, `Link` al sucesor). Los deprecated siguen funcionando hasta el borrado en Fase 4. Se descartó el flag `MDS_USE_LEGACY_GRAPH` previsto en la doc anterior — separamos por endpoint, no por flag, para hacer el borrado de Fase 4 más limpio.
- **2026-05-08** — Doc inicial. Endpoints estables: `/api/catalog`, `/api/catalog/{id}` (Fase 1). Documentados también los endpoints legacy del grafo viejo. Mapping BigQuery → `FieldType` propuesto.
