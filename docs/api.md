# MDS API — referencia de contratos

> **Audiencia:** Mili (frontend, `frontend/`). Este documento es la fuente de verdad de los endpoints HTTP que sirve el backend de MDS.
> **Estado:** doc vivo. Se actualiza en cada fase del refactor que toque la API. Última edición: 2026-05-08 (Fase 1 ✅).
>
> Documentos relacionados: [`migration-plan.md`](migration-plan.md), [`architecture.md`](architecture.md), [`adr/001-multi-agent-to-deterministic-pipeline.md`](adr/001-multi-agent-to-deterministic-pipeline.md).

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
| GET    | `/api/catalog`                          | ✅ estable (v1.0)            | sustituirá a `/api/templates` |
| GET    | `/api/catalog/{id}`                     | ✅ estable (v1.0)            | sin equivalente legacy |
| GET    | `/api/templates`                        | 🟡 legacy — sigue activo     | usar `/api/catalog` |
| POST   | `/api/chat`                             | 🟡 legacy (grafo viejo, SSE) | será reemplazado en Fase 3 |
| POST   | `/api/submit_input`                     | 🟡 legacy (grafo viejo, SSE) | será reemplazado en Fase 3 |
| GET    | `/api/sessions/{session_id}/history`    | 🟡 legacy (grafo viejo)      | TBD — depende de cómo quede el flujo Fase 3 |

> 🟢 = nuevo y estable, 🟡 = legacy mantenido para no bloquearte, 🔴 = a remover.
> Mientras un endpoint esté en 🟡 lo dejamos andando — no hace falta migrar el frontend de golpe.

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

### 3.3 Mapping de tipos: BigQuery → frontend `FieldType`

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

## 4. Endpoints legacy (siguen activos)

Estos sirven al grafo multi-agente actual. Nada los va a apagar de golpe — el plan es que `/api/chat` y `/api/submit_input` queden detrás del grafo determinístico nuevo en Fase 3, manteniendo el mismo shape SSE en lo posible. Si tenemos que cambiar el shape, te aviso con tiempo y dejamos una flag `MDS_USE_LEGACY_GRAPH=1` para roll-back inmediato.

### 4.1 `GET /api/templates` (legacy)

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

Lo dejamos prendido para no romper nada. Cuando muevas el listing del frontend a `/api/catalog`, podés borrarlo del backend en un PR aparte.

### 4.2 `POST /api/chat` (legacy, SSE)

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

### 4.3 `POST /api/submit_input` (legacy, SSE)

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

### 4.4 `GET /api/sessions/{session_id}/history` (legacy)

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
| **2** | Nodos determinísticos + grafo nuevo en paralelo | Sin cambios públicos en la API todavía. El nuevo grafo se prueba con `LocalBackend` adentro. |
| **3** | Switch del entrypoint | `/api/chat` y `/api/submit_input` empiezan a invocar el grafo nuevo. **Intentamos no cambiar la shape** (mismos eventos SSE: `connection`/`progress`/`error`/`final`). Si algo cambia, lo documento acá y dejamos `MDS_USE_LEGACY_GRAPH=1` para rollback. |
| **4** | Borrado del legacy | `/api/templates` queda candidato a borrar (ya tenés `/api/catalog`). Si en ese momento el frontend todavía lo usa, lo dejamos hasta que migres. |
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

- **2026-05-08** — Doc inicial. Endpoints estables: `/api/catalog`, `/api/catalog/{id}` (Fase 1). Documentados también los endpoints legacy del grafo viejo. Mapping BigQuery → `FieldType` propuesto.
