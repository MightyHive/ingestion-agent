# MDS — Checklist Fase 5 MVP

> Acompaña a [migration-plan.md](migration-plan.md) y a [architecture.md](architecture.md). Este documento es el **checklist accionable** de la Fase 5 del refactor de MDS: switch `LocalBackend → HTTPBackend`, Cloud Function DV360, Secret Manager, BigQuery destino.
>
> Reparto confirmado 2026-05-19:
> - **Ivan** — todo el backend del MVP + setup GCP + 1 cliente piloto cargado a mano en SM.
> - **Mili** — frontend (dropdown clientes, selector BQ, error rendering).
> - **Facundo** — UI y endpoints para CRUD de Secret Manager (paralelo, NO bloquea el MVP).
>
> Cada bloque tiene checkboxes con tareas individuales. Marcar `- [x]` a medida que avanza. El bloque pasa a ✅ en el header cuando todas las tareas están tildadas Y los criterios de done verificados.

---

## 0. Estado actual (snapshot 2026-05-19)

- Fases -1 / 0 / 1 / 2 / 3 / 4 ✅ completas. Backend determinístico vivo en branch `new-mds-deterministic` (mergeable a `main`).
- `LocalBackend` funciona end-to-end con `meta.facebook.facebook_ads` tras fix Option A (`_seed_module_dir` en `src/ingestion/dispatcher/local.py`).
- Ivan corrió `POST /api/run` con template de Facebook desde el frontend, vio tabla + JSON descargable. Smoke completo del flujo actual.
- 49 tests pasan en `src/ingestion/tests/`.
- `connectors-library` (submodule) ya tiene `meta/facebook/`, `meta/ig/`, `googleAds/`, `dv360/` — DV360 todavía sin `manifest.json`.
- Backend tenant config vive en `~/.mds/tenants.json` (1 tenant `dev` hardcoded en `_DEFAULT_TENANT_ID` en `src/api.py`).
- Frontend muestra solo `reason` en errores, no `details[]` (ver B5).

## 1. Definición de "MVP completo"

Un usuario abre el frontend, selecciona un cliente real del dropdown, elige el conector **DV360**, configura params y fields, elige `dataset.tabla` destino en BigQuery, da **Run Now**, y obtiene:

1. Tabla persistida en BQ del proyecto MDS con los records del fetch.
2. Preview de 25 filas + metadata (`row_count`, `target_table`, `ddl`, `columns`) en la UI.
3. JSON descargable del resultado.

**Restricciones MVP:**
- Backend **corre local** en la máquina de Ivan (no se deploya). Auth a GCP vía Application Default Credentials.
- **1 solo cliente piloto** cargado en Secret Manager para la primera prueba. Multi-cliente self-service lo entrega Facundo aparte.
- Conector único: **DV360**. Facebook ya existe pero no se incluye en el demo.
- Solo **Run Now**. Schedule, persistencia server-side de templates, observabilidad, tests CF, warehouse_explorer → **post-MVP**.
- Rough-around-the-edges aceptado.

---

## 2. Mapa de bloques

```
B0 (GCP setup) ──┬──> B2 (SM bootstrap) ──┬──> B4 (CF deploy) ──┐
                 │                         │                     │
                 └──> B5-back (endpoints) ─┘                     │
                                                                 │
B1 (DV360 manifest) ─────────────────────────────────────────────┤
                                                                 │
B3 (HTTPBackend) ────────────────────────────────────────────────┤
                                                                 │
B6 (cargar cliente real) ────────────────────────────────────────┤
                                                                 ▼
                                                       B7 (smoke E2E + docs) → ✅ MVP

[Paralelo, no bloquea] F1 — UI Secret Manager (Facundo, full-stack)
[Paralelo, no bloquea hasta B7] M1 — Frontend dropdown + BQ destino + error rendering (Mili)
```

**Camino crítico:** B0 → B2 → B4 → B7
**Total estimado Ivan solo:** ~8 días-persona (~8 días calendario si sin blockers).

---

## 3. Bloque B0 — GCP project + IAM + ADC

**Owner:** Ivan. **Estimado:** 0.5d. **Depende de:** — (bloquea B2, B4, B5-back).

### Tareas

- [x] Decidir nombre del proyecto GCP — `monks-mds-dev`, region `us-central1`.
- [x] Crear proyecto: hecho (preexistente).
- [x] Setear billing account en el proyecto: hecho (preexistente).
- [x] Habilitar APIs requeridas (2026-05-19):
  ```bash
  gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    bigquery.googleapis.com \
    iam.googleapis.com \
    cloudresourcemanager.googleapis.com \
    run.googleapis.com \
    --project=monks-mds-dev
  ```
- [x] Crear SA para la Cloud Function (2026-05-19):
  ```bash
  gcloud iam service-accounts create mds-cf-runner \
    --display-name="MDS CF runner" --project=monks-mds-dev
  ```
- [x] Asignar roles al SA de la CF (2026-05-19):
  ```bash
  gcloud projects add-iam-policy-binding monks-mds-dev \
    --member="serviceAccount:mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
  gcloud projects add-iam-policy-binding monks-mds-dev \
    --member="serviceAccount:mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com" \
    --role="roles/bigquery.dataEditor"
  gcloud projects add-iam-policy-binding monks-mds-dev \
    --member="serviceAccount:mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com" \
    --role="roles/bigquery.jobUser"
  ```
- [x] Asignar al user de Ivan los permisos para invocar la CF + listar/crear BQ datasets: **N/A**, ya tiene `roles/owner` que cubre todo. Mili también tiene Owner. Facundo ya tiene `roles/secretmanager.admin` + `roles/iam.serviceAccountAdmin` (listo para F1).
- [x] Configurar ADC en local (2026-05-19): `gcloud auth application-default login` + `gcloud config set project monks-mds-dev`.
  - **Gotcha 1:** ADC ≠ login normal. Las CLIs `bq` y `gcloud` usan el "active account" (`gcloud auth login`), NO el ADC. Si solo corrés `application-default login`, `bq mk` falla con "no active account selected". Solución: correr **ambos** (`gcloud auth login` para CLIs + `gcloud auth application-default login` para libs Python).
  - **Gotcha 2:** ADC default puede heredar el `quota_project` de otro proyecto previo (en mi caso `general-motors-global`). Corregir con `gcloud auth application-default set-quota-project monks-mds-dev`. Si no, las llamadas via libs Python facturan al proyecto equivocado.
- [x] Verificar ADC funciona (2026-05-19): `gcloud auth application-default print-access-token` devuelve un token `ya29...`.
- [x] Crear dataset BQ inicial de prueba (2026-05-19): `bq --location=US mk -d monks-mds-dev:mvp_test`, confirmado con `bq ls --project_id=monks-mds-dev` listando `mvp_test`.

### Criterios de done

- `gcloud auth application-default print-access-token` devuelve token sin error.
- `gcloud projects describe monks-mds-dev` muestra el proyecto activo con billing.
- `gcloud iam service-accounts list --project=monks-mds-dev` muestra `mds-cf-runner`.
- Dataset `mvp_test` listable con `bq ls --project_id=monks-mds-dev`.

---

## 4. Bloque B1 — Manifest DV360 ✅

**Owner:** Ivan. **Estimado:** 1.0d. **Real:** ~0.3d. **Done:** 2026-05-19. **Depende de:** — (paralelo a B0).

### Tareas

- [x] Endpoint identificado (2026-05-19): **DV360 Bid Manager Reporting API v2** (`https://doubleclickbidmanager.googleapis.com/v2`). Modelo: query pre-existente identificada por `query_id` que vive en el contexto del tenant. La CF dispara `queries/{id}:run`, polea `queries/{id}/reports/{report_id}` hasta `DONE`, descarga el CSV del `googleCloudStoragePath` y parsea. Esto reutiliza la implementación de `connectors-library/dv360/reports/dv360_reports.py` que ya existe.
- [x] `available_fields` definidos (2026-05-19): **39 fields** representativos. 21 dimensiones (Advertiser*, Insertion_Order*, Line_Item*, Campaign*, Creative*, Date/Week/Month, Country*, Device_Type, Browser, Exchange) + 18 métricas (Impressions, Clicks, CTR, Conversions*, Revenue/Media_Cost_Adv_Currency*, CPM/CPC, Video_*Completions, Active_View_*). Naming sigue el output de `_normalize_header` (Title_Case_With_Underscores).
- [x] Params definidos (2026-05-19):
  - **Required:** `fields` (field_list), `data_range` (string enum con los 18 valores válidos de DV360).
  - **Optional:** `customStartDate`, `customEndDate` (string pattern YYYYMMDD), `poll_timeout_sec` (default 400), `poll_interval_sec` (default 10).
  - **No usé `one_of`** porque la mutua exclusión `CUSTOM_DATES ↔ custom*Date` ya se valida dentro del connector (`_build_data_range`); duplicarlo en el schema solo agrega rigidez.
- [x] `connectors-library/dv360/manifest.json` creado (2026-05-19):
  - `id`: `dv360_reports`
  - `platform`: `dv360`, `connector`: `reports`
  - `version`: `0.1.0`, `status`: `alpha`
  - `endpoint.module_path`: `dv360.reports.dv360_reports`, `endpoint.function_name`: `fetch`, `endpoint.cloud_function_name`: `dv360-fetch`, `endpoint.cloud_function_region`: `us-central1`
  - `auth.context_required`: `["query_id", "service_account_json"]` — **decidí Service Account** sobre OAuth client/secret/refresh_token. Razón: una sola entrada en SM (`client_<id>_dv360_service_account_json`) en lugar de tres, y el connector legacy ya tiene resolución limpia de `service_account_info` / `service_account_json`.
  - `auth.secrets`: declara el mapeo `context_key → client_<client_id>_<connector>_<key>` (los `<client_id>` son placeholders, los reemplaza el dispatcher por el tenant real en runtime).
  - `bronze_pattern`: `bronze.dv360_reports` — sin tokens dinámicos en el MVP (el `target_table` lo elige el usuario desde el frontend; el bronze_pattern solo aplica si no se pasa override).
- [x] Scaffolding `module_path`: **no hizo falta crear nada nuevo**. El conector ya existe en `connectors-library/dv360/reports/dv360_reports.py` con la entry point `fetch(params, context) -> dict` con el shape correcto (`status / code / records / meta / errors`). El repo usa **namespace packages (PEP 420)**, así que no necesita `__init__.py` para que `dv360.reports.dv360_reports` resuelva — igual que Facebook (`meta.facebook.facebook_ads`).
- [x] Manifest valida contra `schema.json` (2026-05-19): `load_manifest('connectors-library/dv360/manifest.json')` retorna OK. 39 `available_fields`, 2 `required`, 4 `optional`.
- [x] `to_ddl()` valida (2026-05-19): seleccionando 10 fields representativos (5 dims + 5 metrics) emite DDL BQ válido con `OPTIONS(description="...")` en cada columna que tiene descripción. Sin `PARTITION BY` ni `CLUSTER BY` en el MVP (no hay `partition_field` en `table_naming`).
- [x] Smoke catalog (2026-05-19): `Catalog().list_summaries()` ahora devuelve **2 manifests** (Facebook + DV360); `Catalog().get('dv360_reports')` retorna el manifest crudo con todas las keys (`id, name, platform, connector, version, status, description, owner, endpoint, auth, params, available_fields, table_naming, limits, metadata`).
- [x] `pytest src/ingestion/tests/` verde (2026-05-19): 41 tests pasan (los 8 que faltan son `test_api_run.py` que dependen de `fastapi`, no instalado en este sandbox Linux — corren OK en la Mac de Ivan donde el venv local tiene todo). **Cero regresiones** introducidas por el manifest nuevo.

### Criterios de done

- [x] `connectors-library/dv360/manifest.json` valida contra `src/ingestion/manifest/schema.json`.
- [x] `to_ddl()` emite DDL BigQuery válido para al menos 5 fields representativos.
- [x] `Catalog.list_summaries()` incluye `dv360_reports` con `status: alpha` y `available_fields_count: 39`.
- [x] `Catalog.get('dv360_reports')` devuelve el manifest crudo.

### Decisiones que conviene saber para los bloques siguientes

- **B2 (Secret Manager)**: los nombres concretos a crear son `client_<CLIENT_ID>_dv360_query_id` (string con el id de la query DV360) y `client_<CLIENT_ID>_dv360_service_account_json` (string con el JSON entero de la SA). Reemplazar el "OAuth client_id + client_secret + refresh_token" que figuraba en el checklist original — el conector usa SA, no OAuth user flow.
- **B4 (Cloud Function)**: la CF debe leer esos 2 secretos, reconstruir el contexto `{query_id, service_account_json}` y delegar a `dv360_reports.fetch(params, context)`. El connector ya hace todo el flujo (run → poll → download → parse), así que la CF es básicamente un wrapper finito que llama esa función y manda los records a BQ.
- **B3 (HTTPBackend)**: el flag a leer es `endpoint.cloud_function_name` (`dv360-fetch`) + region (`us-central1`). La URL final se arma como `https://us-central1-monks-mds-dev.cloudfunctions.net/dv360-fetch`.
- **M1 (Frontend, Mili)**: el dropdown de DV360 va a mostrar 39 fields. El selector debería ordenarlos en 2 grupos visualmente (dimensiones primero, métricas después) — eso no está en el manifest, es UX.

---

## 5. Bloque B2 — Secret Manager bootstrap (1 cliente)

**Owner:** Ivan. **Estimado:** 0.25d. **Depende de:** B0. **Bloquea:** B4, B6.

### Tareas

- [ ] Elegir `<CLIENT_ID>` para el primer cliente piloto (ej. `acme` o el nombre real anonimizado).
- [ ] Crear los secretos para DV360 del cliente (los key names exactos dependen de qué auth use DV360, típicamente OAuth):
  ```bash
  echo -n "<value>" | gcloud secrets create client_<CLIENT_ID>_dv360_client_id \
    --data-file=- --project=monks-mds-dev
  echo -n "<value>" | gcloud secrets create client_<CLIENT_ID>_dv360_client_secret \
    --data-file=- --project=monks-mds-dev
  echo -n "<value>" | gcloud secrets create client_<CLIENT_ID>_dv360_refresh_token \
    --data-file=- --project=monks-mds-dev
  # Si DV360 requiere developer_token u otros, agregarlos acá.
  ```
- [ ] Dar acceso al SA de la CF a esos secretos (granularmente, no solo proyecto-wide):
  ```bash
  for SECRET in client_<CLIENT_ID>_dv360_client_id client_<CLIENT_ID>_dv360_client_secret client_<CLIENT_ID>_dv360_refresh_token; do
    gcloud secrets add-iam-policy-binding $SECRET \
      --member="serviceAccount:mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com" \
      --role="roles/secretmanager.secretAccessor" --project=monks-mds-dev
  done
  ```
- [ ] Actualizar `~/.mds/tenants.json` (o `config/tenants.example.json` si lo mantenemos versionado):
  ```json
  {
    "<CLIENT_ID>": {
      "display_name": "<Nombre legible>",
      "gcp_project": "monks-mds-dev",
      "secret_prefix": "client_<CLIENT_ID>"
    }
  }
  ```
- [ ] Documentar la convención de naming en `docs/architecture.md` (sección Secret Manager) — Facundo necesita esto para su F1:
  - Pattern: `client_<client_id>_<connector>_<key>`
  - Keys requeridos los lee del manifest en `auth.context_required`
  - Cada secret tiene 1 versión activa; updates son nuevas versiones (no se borra histórico)
- [ ] Smoke: leer un secreto desde local con ADC para validar permisos:
  ```bash
  gcloud secrets versions access latest --secret=client_<CLIENT_ID>_dv360_client_id --project=monks-mds-dev
  ```

### Criterios de done

- Los 3+ secretos están listables: `gcloud secrets list --project=monks-mds-dev`.
- El SA de la CF tiene `roles/secretmanager.secretAccessor` para cada secreto.
- `~/.mds/tenants.json` actualizado con el nuevo cliente.
- Sección "Secret Manager naming convention" agregada a `docs/architecture.md`.

---

## 6. Bloque B3 — HTTPBackend ✅

**Owner:** Ivan. **Estimado:** 1.5d. **Real:** ~0.4d. **Done:** 2026-05-19. **Depende de:** — (paralelo a B0/B1/B2).

### Tareas

- [x] Crear `src/ingestion/dispatcher/http.py` (2026-05-19):
  - `class HTTPBackend(BackendBase)` con `invoke(manifest, params, tenant) -> ConnectorResponse` (firma uniforme con `LocalBackend`; `tenant_id` y `target_table` salen de `tenant` y `params` respectivamente).
  - Lee `endpoint.cloud_function_name` y `endpoint.cloud_function_region`. URL final: `{MDS_CF_BASE_URL}/{cf_name}` si la env está seteada (override para emulador / smoke), si no `https://{region}-{tenant.gcp_project}.cloudfunctions.net/{cf_name}`.
  - Payload limpio: `{tenant_id, manifest_id, manifest_version, fields?, target_table?, params}`. **Scrubber recursivo** descarta cualquier key con substring `secret`, `token`, `password`, `credential`, `service_account`, `private_key`, `refresh`, `api_key` (case-insensitive) como defensa en profundidad.
  - id_token vía `google.oauth2.id_token.fetch_id_token(Request(), audience=url)` con ADC. **Se saltea** la firma cuando la URL apunta a loopback (`localhost`, `127.0.0.1`, `0.0.0.0`, `::1`) para que el emulador `functions-framework` corra sin ADC.
  - Timeout cliente = `manifest.limits.max_call_duration_seconds + 20s` o `560s` por default (CF gen2 max 540s + buffer cliente).
  - Mapping errores: `connector_auth_required` (401), `connector_forbidden` (403), `connector_not_found` (404), `connector_timeout` (408/504/`httpx.TimeoutException`), `connector_unreachable` (`httpx.ConnectError`), `connector_request_error` (otros `httpx.RequestError`), `connector_upstream_error` (5xx), `connector_invalid_response` (body no-JSON con 2xx). Cada `BackendError` incluye URL + excerpt del body para que se vea en el trace del dispatcher.
- [x] Cablear `MDS_RUNTIME=http` en `ConnectorDispatcher._build_backend` (2026-05-19): la rama de `BackendError("Phase 5")` ya no existe; ahora `from ingestion.dispatcher.http import HTTPBackend; return HTTPBackend()`.
- [x] `MDS_RUNTIME=auto` agregado (2026-05-19): nueva clase `AutoBackend(BackendBase)` que rutea per-manifest. Regla: **si `manifest.endpoint.cloud_function_name` está presente → HTTP; si no → Local.** Decidido sobre la alternativa "depende del env" porque el manifest es la única source of truth y nos permite flipear conectores (FB → Local; DV360 → HTTP) en la misma corrida sin tocar env entre deploys.
- [x] Tests en `src/ingestion/tests/test_dispatcher_http.py` (2026-05-19): 27 nuevos. Stub via `monkeypatch.setattr(httpx, "post", ...)` (no necesita `respx` ni `httpx_mock`, deps nuevas evitadas). Cobertura:
  - Happy path (200 + ConnectorResponse válida).
  - 401/403/404/408/504/500/502/503 parametrizados → prefijos de error mapeados.
  - `httpx.ReadTimeout` → `connector_timeout`. `httpx.ConnectError` → `connector_unreachable`.
  - Body no-JSON con 200 → `connector_invalid_response`.
  - Manifest sin `cloud_function_name` → `BackendError` claro al invocar HTTPBackend.
  - URL resolver: override por env, trailing slash, fallback canónico, error si project missing.
  - Scrubber: top-level + nested + case-insensitive + substring.
  - **Regression: payload NUNCA contiene credenciales** (`test_build_payload_never_contains_secrets`).
  - Timeout derivado de `manifest.limits.max_call_duration_seconds + 20s`.
  - `MDS_RUNTIME=http` → `isinstance(disp.backend, HTTPBackend)`.
  - `MDS_RUNTIME=auto` → `isinstance(disp.backend, AutoBackend)` + ruteo per-manifest.
- [x] `test_dispatcher_local.py::test_dispatcher_http_runtime_phase5_message` reemplazado por `test_dispatcher_http_runtime_builds_http_backend` (2026-05-19): el assert del placeholder de Phase 5 ya no aplica.
- [x] `src/api.py`: **no necesitó cambios** (el handler `/api/run` ya es opaque al backend; lee `MDS_RUNTIME` en el constructor de `ConnectorDispatcher`).
- [x] `pytest src/ingestion/tests/ --ignore=test_api_run.py` (2026-05-19): 68/68 ✅ (41 anteriores + 27 nuevos del HTTPBackend). `test_api_run.py` se saltea solo en este sandbox Linux (sin `fastapi` instalado); corre normal en la Mac de Ivan.
- [x] `requirements.txt` actualizado (2026-05-19): agregada `google-auth>=2.30` (comentada con el motivo: `fetch_id_token` para HTTPBackend).
- [x] `dispatcher/__init__.py` exporta `HTTPBackend` y `AutoBackend` (2026-05-19).
- [x] `docs/api.md` actualizado (2026-05-19): nuevo §6.1 "Variables de entorno relevantes" con tabla `MDS_RUNTIME` / `MDS_CF_BASE_URL` / `MDS_LOCAL_BACKEND_PATHS` + notas de seguridad sobre scrubber + timeout. Glosario menciona `AutoBackend`. Changelog entry de B3 + B1 sumadas.
- [ ] Smoke uvicorn local con `MDS_RUNTIME=http` + `MDS_CF_BASE_URL=http://localhost:9999` **pendiente, no bloqueante**: requiere levantar el venv en la Mac de Ivan. El test `test_http_backend_happy_path_skips_id_token_on_loopback` ya valida exactamente ese flujo con stubs, así que el smoke vivo es solo para tranquilidad — lo cierra Ivan en la próxima sesión.

### Criterios de done

- [x] `HTTPBackend` instanciable y testeado (27 tests).
- [x] Regression test confirma que credenciales NO se filtran al payload.
- [x] `MDS_RUNTIME=http` y `MDS_RUNTIME=auto` enrutados correctamente.
- [x] Todos los tests verdes (68/68 en el suite no-API; los 11 de `test_api_run.py` no se corren aquí por falta de `fastapi` en el sandbox).

### Decisiones que conviene saber para los bloques siguientes

- **B4 (Cloud Function)**: el contrato de entrada de la CF es exactamente lo que `_build_payload` arma: `{tenant_id, manifest_id, manifest_version, fields?, target_table?, params}`. **La CF no recibe ningún secreto** — los resuelve por sí misma desde Secret Manager con su propia identidad de SA (`mds-cf-runner@monks-mds-dev`). Esto simplifica el handler de la CF: parsea payload, lee secretos con el `tenant_id`, llama al connector, escribe a BQ.
- **B4 contrato de salida**: la CF debe devolver `{status, code, records, meta, errors}` (mismo shape que `LocalBackend` ya entiende), serializable a JSON. Si el body no es JSON, el dispatcher lo trata como `connector_invalid_response` con HTTP 200 → mejor que la CF siempre devuelva JSON, incluso en errores.
- **B4 auth**: el deploy con `--no-allow-unauthenticated` + el `id_token.fetch_id_token` del backend ya cierra el círculo. No hace falta nada extra en la CF para validar el token: la propia infra de Cloud Functions lo verifica antes de invocar el handler.
- **B5-back (`/api/run`)**: cuando se agregue el header `X-Tenant-Id`, el dispatcher ya está preparado — `TenantContext.tenant_id` se propaga al payload automáticamente. Solo hay que asegurarse de que `target_table` venga en el body de `/api/run` y se pase al `params` del graph state.
- **`MDS_RUNTIME` recomendado para el smoke E2E (B7)**: `auto`. Así Facebook (sin `cloud_function_name`) sigue corriendo Local y DV360 (con `cloud_function_name=dv360-fetch`) ya rutea a HTTP. No hay que tocar nada entre conectores.
- **`google-auth` no instalado todavía en la Mac**: cuando Ivan arranque B4/B7 con la CF real, antes de levantar uvicorn debe correr `pip install -r requirements.txt` para que pull `google-auth>=2.30`. El import de `id_token` está **lazy** dentro de `_fetch_id_token`, así que los tests + el dev local con loopback siguen corriendo sin la dep instalada.

---

## 7. Bloque B4 — Cloud Function DV360 + write a BigQuery 🚧

**Owner:** Ivan. **Estimado:** 2.5d. **Real (code):** ~0.5d. **Code done:** 2026-05-20. **Deploy pendiente:** sí (necesita B2 con secretos reales). **Depende de:** B0 + B1 + B2 (deploy). **Bloquea:** B7.

> **Estado:** todo el código del CF está en el repo y testeado en seco (34 tests hermeticos). El deploy con `gcloud functions deploy` se hace recién después de B2 (cuando los secretos del cliente piloto estén en SM) — sin secretos reales, el deploy es ejercicio puro sin valor.

### Tareas — código (hecho 2026-05-20)

- [x] Crear directorio `cloud-functions/dv360-fetch/` con layout completo (2026-05-20):
  ```
  cloud-functions/dv360-fetch/
  ├── main.py            # CF entrypoint (functions-framework HTTP, target=run)
  ├── requirements.txt   # CF runtime deps
  ├── .gcloudignore      # excluye tests + local artefacts del upload
  ├── deploy.sh          # stage + deploy script
  ├── conftest.py        # hermetic test setup (stubs functions-framework + GCP SDKs)
  ├── test_main.py       # 34 unit tests, sin GCP access
  └── README.md          # deploy + smoke instructions
  ```
- [x] `main.py` — handler HTTP que (2026-05-20):
    1. Parsea payload `{tenant_id, manifest_id, manifest_version, fields?, target_table?, params}`. **No espera credenciales en el body** — defensa en profundidad con el scrubber del HTTPBackend.
    2. Resuelve secretos con `google.cloud.secretmanager.SecretManagerServiceClient` y la identidad del CF (`mds-cf-runner`):
       - `client_<tenant_id>_dv360_query_id`
       - `client_<tenant_id>_dv360_service_account_json`
    3. Re-inyecta `fields` en `params` (el HTTPBackend lo levantó al top-level; el connector lo lee de `params`).
    4. Construye `context = {"query_id", "service_account_json"}` y llama `dv360_reports.fetch(params, context)`. El connector hace run → poll → download → parse internamente.
    5. Si `status == "OK"` y `target_table` viene en el payload: **deriva el schema BQ desde el manifest** (`available_fields` mapeado por nombre, default `STRING` para columnas no declaradas), crea la tabla si no existe (con `ALLOW_FIELD_ADDITION` para que DV360 pueda agregar columnas en el futuro), y appende los records con `load_table_from_json`.
    6. Devuelve JSON `{status, code, records (capped a `RECORDS_PREVIEW_CAP=200`), meta, errors}` con HTTP status apropiado (200 OK; 401/403/504/etc. según el código del connector; 500 para fallas del propio CF).
- [x] `requirements.txt` (2026-05-20): `functions-framework==3.*`, `google-cloud-secret-manager>=2.20,<3`, `google-cloud-bigquery>=3.20,<4`, `google-auth>=2.30`, `requests>=2.31.0`. Rangos compatibles (no pin exacto) para que security backports lleguen sin redeploy obligado.
- [x] `.gcloudignore` (2026-05-20): excluye `__pycache__/`, `test_*.py`, `*.md`, `.venv/`, `.staging/`, archivos de editor, logs.
- [x] **Decisión de idempotencia (2026-05-20):** `WRITE_APPEND` puro, **sin** columna `_ingestion_timestamp` autoinyectada en el MVP. Razón: agregar columnas no declaradas en el manifest rompería la simetría schema-manifest y forzaría caso especial en `_derive_bq_schema`. Si necesitamos un timestamp post-MVP, se agrega al manifest como `available_field` opcional y se popula desde la CF.
- [x] **Decisión de schema (2026-05-20):** record-driven con manifest como lookup. Las columnas vienen de la primera row del CSV (lo que DV360 efectivamente devolvió, no lo que el manifest declara); el tipo BQ se busca en el manifest, default `STRING`. Permite tolerar columnas nuevas de DV360 sin update del manifest.
- [x] **Decisión de table-id resolution (2026-05-20):** acepta `dataset.table` (prepende `GCP_PROJECT`) o `project.dataset.table` (verbatim). Cualquier otra forma → `INVALID_TARGET_TABLE` (HTTP 400). Esto evita ambigüedad sobre dónde escribe el CF.
- [x] **Decisión de records preview cap (2026-05-20):** la CF devuelve solo los primeros 200 records en el body HTTP (con `meta.records_preview_capped_at=200`), porque la source of truth es BQ. Evita reventar el límite de 32 MiB de Cloud Functions gen2 y satura menos los logs del backend para reportes grandes.
- [x] `deploy.sh` (2026-05-20): script bash con 4 subcomandos:
  - `stage`: vendoriza `dv360_reports.py`, `api_handler.py`, `manifest.json` desde `connectors-library/dv360/...` en `.staging/`. Copia (no symlink) porque `gcloud functions deploy` no resuelve symlinks fuera del source dir.
  - `deploy`: stage + `gcloud functions deploy` con todos los flags correctos (gen2, --no-allow-unauthenticated, SA mds-cf-runner, memory 1Gi, timeout 540s, max-instances 5).
  - `smoke`: stage + `functions-framework --target=run --port=8080`. Combinado con `MDS_RUNTIME=http MDS_CF_BASE_URL=http://localhost:8080` del backend, da round-trip completo del plumbing sin tocar GCP real (loopback skip del id_token en HTTPBackend).
  - `clean`: borra `.staging/`.
- [x] `conftest.py` (2026-05-20): stubea `functions_framework`, `google.cloud.secretmanager`, `google.cloud.bigquery` en `sys.modules` **antes** de que pytest importe `main`. Permite que los tests corran en cualquier env con solo pytest instalado. También stagea una copia del manifest para que `_load_manifest` encuentre el archivo, y la borra en `pytest_sessionfinish` para no ensuciar el source tree.
- [x] `test_main.py` (2026-05-20) — **34 tests** hermeticos, todos verdes:
  - Validation guards (4): `MISSING_TENANT_ID`, `MISSING_MANIFEST_ID`, `MANIFEST_MISMATCH`, `INVALID_PARAMS`.
  - Secret resolution (3): `MISSING_SECRET` cuando SM falla, happy path, **secrets nombrados por tenant_id** (`client_acme_dv360_query_id` no `client_<tenant_id>...`).
  - Connector error code mapping parametrizado (8): `UNAUTHORIZED`/401, `FORBIDDEN`/403, `POLL_TIMEOUT`/504, etc.
  - `CONNECTOR_RAISED` wrap de excepciones no contempladas (1).
  - `CONNECTOR_NOT_PACKAGED` cuando `dv360_reports` no se puede importar (deploy mal staged) (1).
  - Happy path sin `target_table` (1) — BQ writer NO debe correr.
  - `fields` top-level → re-inyectado en `params` para el connector (1).
  - BQ write happy path (1), `BQ_WRITE_FAILED` wrap (1), skip cuando records=[] (1), `INVALID_TARGET_TABLE` (1).
  - `_resolve_table_id` (3): 2-parts prepend, 3-parts passthrough, garbage rechazado.
  - `_derive_bq_schema` (3): manifest types para columnas conocidas, `STRING` default para desconocidas, lista vacía.
  - Records preview cap (2): se aplica cuando >200, no cuando <=200.
  - `_gcp_project` (2): falla sin env, acepta `GOOGLE_CLOUD_PROJECT` además de `GCP_PROJECT`.
  - Manifest loading (1): `_expected_manifest_id` lee del bundled manifest.
- [x] README.md con I/O contract, deploy command, smoke instructions, tabla de error codes (2026-05-20).
- [x] Test suite full: `pytest src/ingestion/tests/` 68/68 + `pytest cloud-functions/dv360-fetch/test_main.py` 34/34 = **102/102 ✅** (2026-05-20). Cero regresiones.

### Tareas — deploy (pendientes, esperan B2)

- [ ] Correr `./deploy.sh deploy` cuando B2 tenga los secretos del cliente piloto en SM.
- [ ] Verificar deploy: `gcloud functions describe dv360-fetch --region=us-central1 --project=monks-mds-dev`.
- [ ] Smoke directo (sin backend):
  ```bash
  curl -X POST \
    -H "Authorization: Bearer $(gcloud auth print-identity-token --audiences=https://us-central1-monks-mds-dev.cloudfunctions.net/dv360-fetch)" \
    -H "Content-Type: application/json" \
    -d '{"tenant_id":"<CLIENT_ID>","manifest_id":"dv360_reports","params":{"data_range":"LAST_7_DAYS","fields":["Impressions","Clicks","Date"]},"target_table":"mvp_test.dv360_smoke"}' \
    https://us-central1-monks-mds-dev.cloudfunctions.net/dv360-fetch
  ```
- [ ] Verificar que `bq query 'SELECT COUNT(*) FROM mvp_test.dv360_smoke'` devuelve > 0.
- [ ] Logs de la CF inspeccionables: `gcloud functions logs read dv360-fetch --region=us-central1 --limit=50`.

### Criterios de done

- [x] Código del CF completo y reviewable en `cloud-functions/dv360-fetch/`.
- [x] Test suite hermético (34 tests) covers payload validation, secret resolution, connector wiring, BQ write, error mapping.
- [x] Cero regresiones en el resto del backend (68/68 ingestion tests verdes).
- [ ] CF deployada y healthy (post-B2).
- [ ] `curl` autenticado devuelve `{status, code, records, meta, errors}` con shape válido (post-B2).
- [ ] Records visibles en BQ después del call (post-B2).

### Decisiones que conviene saber para los bloques siguientes

- **B2 (Secret Manager)**: los nombres exactos a crear son `client_<CLIENT_ID>_dv360_query_id` (string, ej. "1234567") y `client_<CLIENT_ID>_dv360_service_account_json` (JSON entero de la SA como string). El CF los lee literalmente, no parsea el query_id ni valida el JSON antes de pasarlo al connector. **No crear `_client_id`, `_client_secret`, `_refresh_token`** — esos son del modelo OAuth viejo, no se usan con SA.
- **B5-back (`/api/run`)**: cuando el body incluya `target_table`, el dispatcher debe pasarlo en `params` (o en un lugar dedicado del state) para que el HTTPBackend lo levante al top-level del payload. Si el target_table viene como `dataset.table`, el CF prepende `monks-mds-dev` automáticamente; si viene como `project.dataset.table`, pasa verbatim. El backend NO tiene que normalizarlo.
- **B7 (smoke E2E)**: para validar el plumbing antes del deploy real, correr `./deploy.sh smoke` (functions-framework local) + backend con `MDS_RUNTIME=http MDS_CF_BASE_URL=http://localhost:8080`. El loopback skip del id_token + el stub del connector permiten validar todo el camino backend → HTTPBackend → CF → respuesta sin necesitar credenciales DV360 reales todavía.
- **F1 (Facundo, SM UI)**: la convención de naming `client_<id>_<connector>_<key>` queda definitivamente cementada en este CF (`_build_connector_context` usa exactamente ese pattern). Si Facundo necesita validar formatos antes de upsert, el CF asume que `_query_id` es plain string y `_service_account_json` es JSON-parseable.
- **Post-MVP — multi-project tenants**: cuando llegue el momento, la CF lee secretos desde **su propio** `GCP_PROJECT`, no desde el del tenant. Si un cliente vive en otro proyecto GCP, necesita una CF separada o que el `mds-cf-runner` del proyecto MDS tenga IAM cross-project sobre los secretos del cliente. Por ahora todos los secretos viven en `monks-mds-dev` → no hay problema.

---

## 8. Bloque B5-back — Endpoints `/api/tenants` y `/api/bq-datasets`

**Owner:** Ivan. **Estimado:** 1.0d. **Depende de:** B0. **Consumido por:** Mili (M1).

### Tareas

- [ ] `GET /api/tenants` en `src/api.py`:
  - Lee `~/.mds/tenants.json`.
  - Devuelve `[{id, display_name}]` (no exponer `gcp_project` ni `secret_prefix`).
- [ ] `GET /api/bq-datasets`:
  - Usa `google.cloud.bigquery.Client()` con ADC.
  - Lista datasets del proyecto: `[{dataset_id, project, location, created}]`.
- [ ] `GET /api/bq-datasets/{dataset_id}/tables`:
  - Lista tablas del dataset: `[{table_id, num_rows, schema_summary}]` (schema_summary opcional, solo si es barato).
- [ ] `POST /api/bq-datasets` (extra, fácil):
  - Body: `{dataset_id, location}` (default location `US` o `monks-mds-dev` default).
  - Crea dataset: `bq.create_dataset(...)`. Devuelve `{dataset_id, project, location}`.
  - Error si ya existe → 409 conflict.
- [ ] Modificar `POST /api/run`:
  - Leer header `X-Tenant-Id` (fallback a `_DEFAULT_TENANT_ID="dev"` si no viene, para no romper smoke tests).
  - Aceptar `target_table` en body (`<project>.<dataset>.<table>` o `<dataset>.<table>`; si no trae project, asume `monks-mds-dev`).
  - Pasar `tenant_id` y `target_table` al graph state para que el dispatcher los incluya en el payload de la CF.
- [ ] Tests en `src/ingestion/tests/test_api_tenants.py` y `test_api_bq.py`:
  - `/api/tenants` con tenants.json mockeado.
  - `/api/bq-datasets` con BQ client mockeado (no llamar GCP real en CI).
  - `/api/run` con header `X-Tenant-Id` se propaga.
- [ ] Actualizar `docs/api.md` con los 3+1 endpoints nuevos + cambios en `/api/run`.

### Criterios de done

- Los 4 endpoints responden con shapes documentados.
- `curl http://localhost:8000/api/tenants` devuelve el cliente piloto.
- `curl http://localhost:8000/api/bq-datasets` devuelve `mvp_test` (creado en B0).
- `POST /api/run` con `X-Tenant-Id: <CLIENT_ID>` y `target_table` se propaga al payload de la CF.
- `pytest src/ingestion/tests/` verde.

---

## 9. Bloque B6 — Cargar cliente real

**Owner:** Ivan. **Estimado:** 0.25d. **Depende de:** B2 + B4. **Bloquea:** B7.

### Tareas

- [ ] Identificar 1 cliente real en el proyecto GCP de origen.
- [ ] Sacar credenciales DV360 actuales (client_id, client_secret, refresh_token, etc).
- [ ] **Validar primero** que el refresh_token sigue válido contra DV360 directamente:
  ```bash
  curl -X POST https://oauth2.googleapis.com/token \
    -d "client_id=<...>&client_secret=<...>&refresh_token=<...>&grant_type=refresh_token"
  ```
  Si devuelve `access_token`, está vivo. Si devuelve error, hay que re-autenticar al cliente (puede requerir interacción suya).
- [ ] Cargar credenciales en SM bajo `client_<CLIENT_ID>_dv360_*` (ya hecho en B2 con valores dummy → reemplazar con `gcloud secrets versions add`).
- [ ] Verificar tenants.json tiene el cliente real (no dummy).

### Criterios de done

- `gcloud secrets versions access latest --secret=client_<CLIENT_ID>_dv360_refresh_token` devuelve el token real.
- Refresh contra DV360 OAuth funciona.

---

## 10. Bloque B7 — Smoke E2E + docs

**Owner:** Ivan (coordinando con Mili). **Estimado:** 1.0d. **Depende de:** TODO el resto + M1 de Mili.

### Tareas

- [ ] Levantar backend local: `uvicorn src.api:app --reload` con `MDS_RUNTIME=http` + `MDS_CF_BASE_URL=https://us-central1-monks-mds-dev.cloudfunctions.net/`.
- [ ] Abrir frontend, verificar dropdown clientes muestra el cliente real (Mili).
- [ ] Seleccionar DV360, configurar template con fields y params, elegir dataset destino, dar **Run Now**.
- [ ] Verificar respuesta UI: tabla + JSON descargable.
- [ ] Verificar en BQ: `bq query 'SELECT COUNT(*) FROM <dataset>.<table>'` > 0.
- [ ] Repetir con caso de error (params inválidos, secreto faltante) → UI muestra `details[]` claro.
- [ ] Actualizar `docs/api.md`:
  - `X-Tenant-Id` header
  - `target_table` en `POST /api/run` body
  - Endpoints `/api/tenants`, `/api/bq-datasets`, `/api/bq-datasets/{id}/tables`, `POST /api/bq-datasets`
- [ ] Actualizar `docs/migration-plan.md`: Fase 5 ✅ con fecha.
- [ ] Mergear `ik-mmi-integration` (o branch actual) → `new-mds-deterministic` → opcional `main` cuando todo el equipo apruebe.
- [ ] Tag `mds-mvp` en git.
- [ ] Actualizar este checklist al 100%.

### Criterios de done

- Demo end-to-end ejecutable con cliente real, sin manipular nada por la consola.
- Errores se muestran con `details[]` en UI.
- Docs actualizados.
- Tag `mds-mvp` pusheado.

---

## 11. Frontend (M1) — Mili, paralelo

**Owner:** Mili. **Estimado:** 1.5–2d. **Depende de contratos:** apenas Ivan termina B0 y manda los shapes.

### Tareas (a coordinar con Mili)

- [ ] Dropdown de clientes (consume `GET /api/tenants`).
- [ ] Estado global con `tenantId` seleccionado; manda `X-Tenant-Id` header en todos los `/api/run`.
- [ ] Selector de dataset + input de nombre de tabla (consume `GET /api/bq-datasets` y opcional `/{id}/tables`).
- [ ] Botón "Crear dataset nuevo" → modal con form + POST a `/api/bq-datasets`.
- [ ] Renderizar `details[]` en componente de error (no solo `reason`). Cuando hay traceback, mostrarlo colapsable.
- [ ] Validación: bloquear Run Now si no hay cliente o no hay target_table seleccionado.

### Hand-off Ivan → Mili

- Mensaje a mandar apenas termine B0: shapes de los 4 endpoints nuevos + ejemplo de header `X-Tenant-Id` + nuevo body de `/api/run`.
- Mili puede mockear los endpoints mientras Ivan termina B5-back.

---

## 12. Secret Manager UI (F1) — Facundo, paralelo

**Owner:** Facundo (full-stack). **Estimado:** 5–7d. **No bloquea MVP.**

### Scope (a coordinar con Facundo)

- Endpoints backend:
  - `GET /api/clients` → lista clientes (desde tenants.json o desde lo que decidamos como source of truth).
  - `POST /api/clients` → crea cliente nuevo + estructura de secretos vacía.
  - `GET /api/clients/{id}/secrets` → lista keys del cliente (sin values).
  - `PUT /api/clients/{id}/secrets/{connector}/{key}` → upsert un secreto.
  - `DELETE /api/clients/{id}/secrets/{connector}/{key}` → borra secreto.
  - `DELETE /api/clients/{id}` → borra cliente entero.
- UI:
  - Listado de clientes (cards o tabla).
  - Detail view: por cliente, mostrar qué connectors tiene credenciales cargadas.
  - Form de edición: lee `auth.context_required` del manifest del conector seleccionado y arma los inputs dinámicamente.
  - Audit trail mínimo: quién cambió qué, cuándo (opcional MVP de F1).

### Hand-off Ivan → Facundo

- Convención de naming: `client_<client_id>_<connector>_<key>` (B2 lo deja documentado en architecture.md).
- `auth.context_required` del manifest define las keys.
- Permisos GCP: el SA que use el backend (en F1 ya deployado o todavía local con ADC) necesita `roles/secretmanager.admin` sobre el proyecto MDS.

---

## 13. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Refresh token DV360 del cliente vencido | Media | Alto (bloquea B6/B7) | Validar **al principio** (B6 step 1). Si vencido, pedir re-auth al cliente antes de seguir |
| Query DV360 > 9 min | Media | Medio | Usar CF gen2 con timeout 60min; post-MVP paginar+stream a BQ |
| Records DV360 con nested deep (>2 niveles) | Baja | Medio | `to_ddl()` ya soporta recursivo; validar con sample real en B1 antes de cerrar |
| Permisos cruzados ADC ↔ CF ↔ SM ↔ BQ | Media | Alto | Smoke independiente de cada eslabón antes del E2E (B0/B2/B4 cada uno cierra con verificación) |
| Mili o Facundo bloqueados por contratos | Media | Medio | Mandar shapes apenas termine B0 (no esperar al endpoint funcionando) |
| Conflicto con cambios de Facundo en F1 | Baja | Alto | Acordar **antes** que F1 NO toca `/api/run` ni el shape de tenants.json; solo agrega endpoints nuevos |

---

## 14. Hand-offs y comunicación

### Antes de arrancar B0

- [ ] Mensaje a **Mili**: scope nuevo (`X-Tenant-Id`, `target_table`, 4 endpoints nuevos), estimado, le pasamos shapes en 1-2 días.
- [ ] Mensaje a **Facundo**: alcance F1 (CRUD SM full-stack), convención naming, manifest `auth.context_required` como source of keys, su trabajo no bloquea MVP de Ivan.

### Durante

- Sync corto Ivan↔Mili cuando salga B5-back, para que ella conecte la UI a endpoints reales.
- Sync Ivan↔Facundo cuando F1 esté listo para mergear (después del MVP).

### Al cerrar MVP (B7 ✅)

- Demo grabada o en vivo del flujo end-to-end.
- Tag `mds-mvp` + PR `new-mds-deterministic → main` si el equipo aprueba.

---

## 15. Comandos útiles de referencia rápida

```bash
# Cambiar de proyecto activo
gcloud config set project monks-mds-dev

# Token de identidad para llamar la CF
gcloud auth print-identity-token --audiences=https://us-central1-monks-mds-dev.cloudfunctions.net/dv360-fetch

# Tail de logs de la CF
gcloud functions logs read dv360-fetch --region=us-central1 --project=monks-mds-dev --limit=20

# Listar secretos
gcloud secrets list --project=monks-mds-dev

# Levantar backend local con HTTPBackend apuntando a la CF
cd /Users/ivankrawchik/Monks/Agentes/ingestion-agent
source venv/bin/activate
export MDS_RUNTIME=http
export MDS_CF_BASE_URL=https://us-central1-monks-mds-dev.cloudfunctions.net/
uvicorn src.api:app --reload --port 8000

# Correr tests
pytest src/ingestion/tests/ -v

# Verificar fila en BQ
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM monks-mds-dev.<dataset>.<table>"
```

---

## 16. Tracking — estado global

| Bloque | Estado | Owner | Done date |
|---|---|---|---|
| B0 GCP setup | ✅ | Ivan | 2026-05-19 |
| B1 DV360 manifest | ✅ | Ivan | 2026-05-19 |
| B2 SM bootstrap | ⏳ | Ivan | — |
| B3 HTTPBackend | ✅ | Ivan | 2026-05-19 |
| B4 CF DV360 (code) | ✅ | Ivan | 2026-05-20 |
| B4 CF DV360 (deploy) | ⏳ | Ivan | post-B2 |
| B5-back endpoints | ⏳ | Ivan | — |
| B6 cliente real | ⏳ | Ivan | — |
| B7 smoke E2E | ⏳ | Ivan | — |
| M1 frontend | ⏳ | Mili | — |
| F1 SM UI (post-MVP) | ⏳ | Facundo | — |

Leyenda: ⏳ pendiente · 🚧 en curso · ✅ done · ⚠️ blocked

---

**Última actualización:** 2026-05-20 (B4 code cerrado — `cloud-functions/dv360-fetch/` completo con 34 tests hermeticos verdes, 102/102 tests totales, README + deploy.sh listos. Deploy a Cloud Functions queda pendiente de B2 — secretos del cliente piloto en Secret Manager).
