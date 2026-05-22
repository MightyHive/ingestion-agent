# MDS — Runbook Fase 5

**Objetivo:** Cerrar la transición a producción local con tenant-aware tables y `ingested_at` en cada fila. Backend MDS y frontend siguen corriendo en tu Mac; el connector (CF Meta) corre en `monks-mds-dev`.

---

## 0. Qué cambió en código (resumen para auditar el diff)

| Archivo | Cambio |
|---|---|
| `cloud-functions/meta-facebook-insights/main.py` | `_SYSTEM_FIELDS = {"ingested_at": "TIMESTAMP"}`; `_stamp_ingestion_timestamp(records)` se llama en `_write_records_to_bq` antes de derivar el schema; `ingested_at` queda último por orden de inserción del dict |
| `cloud-functions/meta-facebook-insights/test_main.py` | +9 tests; total 46/46 |
| `src/ingestion/dispatcher/base.py` | `ConnectorDispatcher.invoke` ahora solo delega — la validación de `context_required` ya no vive acá |
| `src/ingestion/dispatcher/local.py` | `LocalBackend.invoke` enforce `tenant.assert_satisfies(required_keys)` al inicio |
| `src/ingestion/tests/test_dispatcher_local.py` | 2 tests nuevos pin del enforce (directo en backend + vía dispatcher con runtime local) |
| `src/ingestion/tests/test_dispatcher_http.py` | 2 tests nuevos pin del bypass (HTTPBackend + AutoBackend con `cloud_function_name`) |
| `src/api.py` | `RunRequest.tenant_id: str \| None` opcional; blanco/`None` → `_DEFAULT_TENANT_ID="dev"` |
| `src/ingestion/nodes/data_architect.py` | `_resolve_table_name` acepta `tenant_id`; `to_ddl` también; nuevo token `{tenant_id}` en `bronze_pattern`; `_sanitise_bq_token` normaliza para BQ; `node()` lee `params.target_table` (override del usuario) |
| `src/ingestion/nodes/request_validator.py` | `_SYSTEM_PARAM_KEYS = frozenset({"target_table"})` — bypass del check de "unknown keys" para system params |
| `src/ingestion/manifest/schema.json` | Documenta el nuevo token `{tenant_id}` en `bronze_pattern.description` |
| `connectors-library/meta/facebook/manifest.json` | `bronze_pattern: "bronze.meta_facebook_ad_insights_{tenant_id}"` |
| `src/ingestion/tests/test_data_architect.py` | +4 tests (token, sanitise, ignored cuando no se referencia, override de target_table) |
| `src/ingestion/tests/test_request_validator.py` | +2 tests (acepta target_table, sigue rechazando typos en presencia de system params) |
| `src/ingestion/tests/test_api_run.py` | +3 tests (tenant_id explícito, blanco → fallback, override de target_table) |

**Suite:** 77/77 en sandbox + 46/46 CF. Los 11 de `test_api_run.py` requieren `fastapi` (instalado en tu Mac, no acá).

---

## 1. Configuración local — `~/.mds/tenants.json`

El loader de `TenantContext` espera un JSON con esta forma. Para Fase 5, como las credenciales reales del connector las resuelve la CF vía Secret Manager, **`context` puede ser un dict vacío** (`{}`) y `LocalBackend` no se va a quejar porque el manifest de Meta ya está bound a HTTP (tiene `cloud_function_name`).

Pero para el caso `dev` (que también es el fallback) dejá un `context` con los mismos keys por si en algún momento querés correr con `MDS_RUNTIME=local`:

```bash
mkdir -p ~/.mds
cat > ~/.mds/tenants.json <<'JSON'
{
  "dev": {
    "gcp_project": "monks-mds-dev",
    "service_account": "mds-runner@monks-mds-dev.iam.gserviceaccount.com",
    "context": {}
  },
  "cliente1": {
    "gcp_project": "monks-mds-dev",
    "service_account": "mds-runner@monks-mds-dev.iam.gserviceaccount.com",
    "context": {}
  }
}
JSON
chmod 600 ~/.mds/tenants.json
```

**Por qué `chmod 600`:** aunque hoy el dict está vacío, en cuanto cargues un `access_token` o un `service_account_json` para correr `MDS_RUNTIME=local` el archivo va a tener material sensible. Mejor el hábito de cero permisos para grupo/otros desde el día 1.

**Verificación rápida:**

```bash
python - <<'PY'
from ingestion.auth.tenant_context import TenantContext
for tid in ["dev", "cliente1"]:
    ctx = TenantContext.resolve(tid)
    print(tid, "→", ctx.gcp_project, ctx.service_account, "context_keys:", list(ctx.context.keys()))
PY
```

(Correr esto desde `src/` con el venv del back activo.)

---

## 2. Re-deploy CF Meta a `monks-mds-dev`

La CF necesita el nuevo `main.py` con `ingested_at`. Si ya tenés el script de deploy de la fase 4, es exactamente el mismo comando — solo cambió el contenido del bundle:

```bash
cd cloud-functions/meta-facebook-insights

gcloud functions deploy meta-facebook-insights \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=run \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account=mds-cf-meta@monks-mds-dev.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=monks-mds-dev \
  --memory=512MB \
  --timeout=540s \
  --project=monks-mds-dev
```

**Validar post-deploy** (smoke directo a la CF, igual que el último E2E que dio verde):

```bash
URL=$(gcloud functions describe meta-facebook-insights \
  --region=us-central1 --gen2 --project=monks-mds-dev --format='value(serviceConfig.uri)')

TOKEN=$(gcloud auth print-identity-token --audiences="$URL")

curl -s -X POST "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "cliente1",
    "manifest_id": "meta_facebook_ad_insights",
    "manifest_version": "0.1.0",
    "target_table": "bronze.meta_facebook_ad_insights_cliente1",
    "fields": ["account_id","campaign_name","spend","impressions"],
    "params": {"days_back": 7}
  }' | python -m json.tool
```

**Validar en BQ que `ingested_at` quedó al final y como TIMESTAMP:**

```bash
bq show --format=prettyjson monks-mds-dev:bronze.meta_facebook_ad_insights_cliente1 \
  | python -c "import sys,json;s=json.load(sys.stdin)['schema']['fields'];print('\n'.join(f\"{i+1:>2}. {f['name']} ({f['type']})\" for i,f in enumerate(s)))"
```

Esperás ver `ingested_at (TIMESTAMP)` en la última línea.

---

## 3. Smoke E2E vía backend MDS local

Ahora el backend (no la CF directo). Esto valida toda la cadena nueva: `RunRequest.tenant_id` → graph → `data_architect` con `{tenant_id}` → `HTTPBackend` con id_token → CF → BQ con `ingested_at`.

**Pre:**

```bash
export MDS_RUNTIME=http        # forzá HTTP backend; "auto" también sirve por el cloud_function_name
# NO seteés MDS_CF_BASE_URL — querés que el HTTPBackend resuelva la URL canónica de GCF
unset MDS_CF_BASE_URL
```

**Levantá el backend:**

```bash
cd src && uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

**Disparalo (otra terminal):**

```bash
curl -s -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "manifest_id": "meta_facebook_ad_insights",
    "tenant_id": "cliente1",
    "params": {
      "fields": ["account_id","campaign_name","spend","impressions"],
      "days_back": 7
    }
  }' | python -m json.tool
```

**Qué esperar en el body:**

- `tenant_id: "cliente1"`
- `target_table: "bronze.meta_facebook_ad_insights_cliente1"` ← el backend resolvió el `{tenant_id}` token
- `row_count > 0`
- `columns` incluye `ingested_at` al final

**Override de target_table** (caso edge para probar):

```bash
curl -s -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "manifest_id": "meta_facebook_ad_insights",
    "tenant_id": "cliente1",
    "params": {
      "fields": ["account_id","campaign_name","spend"],
      "days_back": 7,
      "target_table": "sandbox.meta_adhoc_test"
    }
  }' | python -m json.tool
```

`target_table` en el body debe ser `sandbox.meta_adhoc_test`, no la versión con `_cliente1`.

---

## 4. Frontend — cambios aplicados (Niveles 1+2+3)

> **Estado:** ya aplicados en `frontend/` en esta sesión. Pasale el diff a Mili cuando muevas la rama; el cambio respeta los patrones existentes (zustand + persist, `<select>` nativo, `<Input>` shadcn). Type-check `npx tsc --noEmit` pasa limpio.

### 4.0 Archivos tocados

| Archivo | Cambio |
|---|---|
| `frontend/src/lib/api/catalog.ts` | `runIngestion(manifestId, params, tenantId?)` — incluye `tenant_id` en el body si se pasa |
| `frontend/src/lib/stores/tenantStore.ts` (NUEVO) | Zustand store con `tenants[]` y `selectedTenantId`, persistido en `localStorage`. Lista default desde env `NEXT_PUBLIC_TENANTS` (CSV) o `["dev","cliente1"]`. Helper `getActiveTenantId()` para uso fuera de React |
| `frontend/src/lib/stores/templateStore.ts` | `SavedTemplate` gana `targetTableOverride?: string` |
| `frontend/src/lib/stores/connectorStore.ts` | `runPipeline()` lee tenant del store y lo manda a `runIngestion`; `proposeTemplateFromSelection()` pasa `tenantId` al builder para que el preview ya muestre la tabla con `{tenant_id}` sustituido |
| `frontend/src/lib/export-ingestion.ts` | `runTemplateIngestion()` lee tenant + manda `targetTableOverride` (si lo hay) en `params.target_table` |
| `frontend/src/lib/template-proposal.ts` | `resolveTableName()` acepta `tenantId`; substituye `{tenant_id}` con sanitización idéntica a la del backend |
| `frontend/src/components/layout/TenantSelector.tsx` (NUEVO) | Dropdown nativo en el Header. SSR-safe (solo renderiza tras `mounted=true` para evitar mismatch de hydration con `localStorage`) |
| `frontend/src/components/layout/Header.tsx` | Renderiza `<TenantSelector />` antes de Help/Notifications |
| `frontend/src/components/data-connection/TemplateStep.tsx` | "Suggested table" pasa a ser `TargetTableRow` editable. Auto-sincroniza con el preview hasta que el usuario edita (`targetTableDirty`); `handleApprove` persiste el override solo si está editado |

### 4.1 Contrato `POST /api/run` (el que el front ya manda)

```json
{
  "manifest_id": "meta_facebook_ad_insights",
  "tenant_id": "cliente1",
  "params": {
    "fields": ["account_id", "campaign_name", "spend"],
    "days_back": 14,
    "target_table": "bronze.meta_facebook_ad_insights_cliente1"
  }
}
```

- **`tenant_id`** se incluye automáticamente desde el `tenantStore` (selector del Header).
- **`params.target_table`** se incluye solo cuando el template guardado tiene `targetTableOverride` (= el usuario lo editó en el step "Template" antes de guardar).

### 4.2 Configuración del front (env vars nuevas)

En `frontend/.env.local` (creá el archivo si no existe):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MOCK=false
NEXT_PUBLIC_TENANTS=dev,cliente1
NEXT_PUBLIC_DEFAULT_TENANT_ID=cliente1
```

- `NEXT_PUBLIC_TENANTS` — CSV de tenants que pueblan el dropdown. Sin esto, default = `["dev","cliente1"]`.
- `NEXT_PUBLIC_DEFAULT_TENANT_ID` — cuál sale seleccionado la primera vez (después gana lo que persistió el usuario en `localStorage`).

### 4.3 Cómo se ve el flujo end-to-end ahora

1. Usuario abre la app → en el Header arriba a la derecha aparece el dropdown "CLIENT" con `dev` / `cliente1` (el último elegido queda persistido).
2. Va a **Data Connection** → elige Meta Facebook → selecciona reporting scope + campos.
3. Avanza al step **Template** → ve en el panel derecho:
   - "Active client (tenant)": `cliente1`
   - "Target BigQuery table": input prellenado con `bronze.meta_facebook_ad_insights_cliente1` (substitución vive del manifest), editable si quiere cambiarlo.
4. Guarda el template (con o sin override).
5. **Data Export** / **Export Planner** → "Run now" → `runTemplateIngestion` envía el body con `tenant_id` + `params.target_table` (si hay override).
6. Backend resuelve todo y escribe en BQ. La respuesta vuelve, `target_table` está confirmada en el panel de preview.

### 4.4 Lo que NO cambió en el front

- Stores `credentialStore`, `destinationStore`, `exportJobStore` siguen igual.
- Componentes de `data-export/` (`DestinationsStep`, `ExtractionStep`, `ExportSchedulerStep`) no se tocaron — el target table se setea en Data Connection y viaja en el template.
- Las rutas SSE `/api/chat` y `/api/submit_input` siguen sin enviar tenant (no son flujo de ingesta real).

### 4.1 Contrato actualizado de `POST /api/run`

```json
{
  "manifest_id": "meta_facebook_ad_insights",
  "tenant_id": "cliente1",
  "params": {
    "fields": ["account_id", "campaign_name", "spend"],
    "days_back": 14,
    "target_table": "bronze.meta_facebook_ad_insights_cliente1"
  }
}
```

**Lo nuevo:**

1. **`tenant_id`** (top-level, opcional pero recomendado): selector de cliente. Si no se manda o viene blanco, el back usa `"dev"`. Debe ir como input del usuario o como query param de la página.
2. **`params.target_table`** (opcional): si el usuario lo edita, va acá. Si no, **NO MANDARLO** y dejá que el back compute el default desde el manifest.

### 4.2 Cómo computar el default de `target_table` para mostrar en el form

El front no necesita lógica especial. Cuando el usuario seleccione un connector:

1. Llamá `GET /api/catalog/{manifest_id}` → vas a recibir el manifest completo, incluido `table_naming.bronze_pattern` (p.ej. `"bronze.meta_facebook_ad_insights_{tenant_id}"`).
2. Substituí los tokens cliente-side con los valores que ya tenés:
   - `{tenant_id}` → el tenant seleccionado, sanitizado (lowercase, `-`/espacios → `_`, solo `[a-z0-9_]`)
   - `{platform}`, `{connector}`, `{id}` → vienen en el manifest
   - `{version_major}` → split por `.` del `manifest.version` y agarrar el `[0]`
3. Mostrá el resultado en un input editable con label "Tabla destino".
4. Si el usuario lo edita, mandalo en `params.target_table`. Si lo dejó como vino del default, no lo mandes.

**Helper JS de referencia** (~20 líneas, dejalo en utils):

```js
function sanitiseBqToken(value) {
  return value.trim().toLowerCase()
    .replace(/[-\s]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

function resolveTargetTableDefault(manifest, tenantId) {
  const pattern = manifest?.table_naming?.bronze_pattern || 'bronze.{id}';
  const version = (manifest.version || '0.0.0').split(/[.+-]/)[0];
  const tokens = {
    platform: manifest.platform || '',
    connector: manifest.connector || '',
    id: manifest.id,
    version_major: version,
    tenant_id: sanitiseBqToken(tenantId || ''),
  };
  return pattern.replace(/\{(\w+)\}/g, (_, k) => tokens[k] ?? '');
}
```

### 4.3 UX recomendada

- **Tenant selector** primero (dropdown alimentado por la lista de tenants — por ahora hardcoded `["dev", "cliente1"]`, en una fase futura lo lee de un endpoint nuevo).
- **Connector selector** después.
- **Tabla destino**: input editable, prellenado con `resolveTargetTableDefault(manifest, tenantId)`, recalcula cuando el usuario cambia el tenant.
- El resto de los params del manifest sigue igual.

### 4.4 Lo que NO cambia

- Los códigos de respuesta (200/400/422/502/500) y el header `X-Request-Id`.
- La forma del `formatted_response` que devuelve `/api/run` (sigue trayendo `tenant_id`, `target_table`, `row_count`, `columns`, `rows_preview`, `ddl`, `errors`).
- El catálogo: `GET /api/catalog` y `GET /api/catalog/{id}` siguen iguales en forma.

---

## 5. Cómo pasar a prod (cuando estés listo)

Pregunta tuya: *"si quisiera pasarlo a prod como seria? con CF?"*

**Recomendación: Cloud Run para el back, CFs para los connectors** (que ya es lo que estás haciendo).

| Componente | Recomendación | Por qué |
|---|---|---|
| **CFs de connectors** | Seguir en CF gen2 (lo que ya tenés) | Aislamiento por connector, cold start tolerable, deploy independiente. Patrón ya consolidado en `connectors-library` |
| **Back MDS (FastAPI)** | **Cloud Run** | Long-running HTTP server, no funciona bien como CF. Cloud Run te da escala 0→N, autenticación IAM nativa, mismo modelo de SA, custom domain via load balancer |
| **Frontend** | **Cloud Run** o **Firebase Hosting** (si es estático) | Lo que use Mili. Si es Next.js con SSR → Cloud Run; si es Vite/CRA build estático → Firebase Hosting |
| **tenants.json** | **Secret Manager** (no FS) | En prod no podés depender de `~/.mds/`. El loader de `TenantContext` ya está mockeable (`set_loader_for_testing`); en prod, mete una variante que lea de SM y montala con env var `MDS_TENANTS_SOURCE=secret-manager` |
| **CORS** | Cerrar a tu dominio del front | Hoy `allow_origins=["*"]` por dev. Cambiarlo en `src/api.py` antes del deploy a prod |
| **Auth front→back** | IAP (Identity-Aware Proxy) o Firebase Auth + verificación de id_token en el handler | Decisión la dejo para cuando tengamos un user model real |

**Orden sugerido** (no para ahora, para cuando quieras pasar):

1. Containerizar el back (`Dockerfile` simple con uvicorn).
2. Implementar el loader de tenants desde SM detrás de un flag (`MDS_TENANTS_SOURCE`).
3. Cerrar CORS.
4. `gcloud run deploy mds-api --source=. --region=us-central1 --no-allow-unauthenticated --service-account=mds-api-prod@...`.
5. Cloud Run necesita IAM `roles/cloudfunctions.invoker` sobre cada CF para que pueda firmar id_tokens.
6. Frontend deploy aparte; configurar la base URL del back en una env var de build.

Si querés que armemos esto al detalle (Dockerfile, módulo SM, IAM, etc.) cuando llegue el momento, lo hacemos en una sesión nueva.

---

## 6. Checklist final

**Backend / infra (vos):**

- [ ] `~/.mds/tenants.json` creado con `dev` y `cliente1` (`chmod 600`)
- [ ] CF Meta re-deployada — `bq show` confirma `ingested_at TIMESTAMP` al final
- [ ] Smoke directo a la CF responde 200 con `meta.ingested_at` en el body
- [ ] Backend MDS local levantado con `MDS_RUNTIME=http`
- [ ] Smoke vía backend con `tenant_id=cliente1` → tabla `bronze.meta_facebook_ad_insights_cliente1`
- [ ] Smoke con `params.target_table` custom → respeta el override
- [ ] (En tu Mac) `pytest src/` corre los 88 tests verdes (77 sandbox + 11 `test_api_run.py` que requieren fastapi)

**Frontend (ya aplicado, validar en navegador):**

- [ ] `frontend/.env.local` con `NEXT_PUBLIC_TENANTS`, `NEXT_PUBLIC_DEFAULT_TENANT_ID`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_MOCK=false`
- [ ] `npm run dev` levanta sin errores; `npx tsc --noEmit` exit 0
- [ ] Header muestra el selector `CLIENT: cliente1` y persiste la elección al recargar
- [ ] Data Connection → Template step → "Target BigQuery table" muestra `bronze.meta_facebook_ad_insights_cliente1`
- [ ] Cambiar el tenant en el Header y volver al Template → el preview se actualiza (si no editaste el input)
- [ ] Editar el target table → guardar → en `localStorage` `templates-storage` el template tiene `targetTableOverride`
- [ ] Export Planner → "Run now" → la respuesta del back trae el `target_table` esperado
- [ ] PR/diff revisado con Mili antes del merge a main (cambios en `frontend/src/lib/stores`, `components/layout`, `components/data-connection`)
