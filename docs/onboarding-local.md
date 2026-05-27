# MDS — Onboarding local (Fase 5 MVP)

Esta guía cubre lo necesario para levantar MDS (backend FastAPI + frontend Next.js) en una Mac y disparar el flujo end-to-end contra la Cloud Function real (`meta-facebook-insights` en `monks-mds-dev`).

Audiencia: desarrolladores del equipo MDS (Ivan, Mili, Facundo) que clonan el repo por primera vez o que cambian de máquina.

> **TL;DR**: instalá prerequisitos, pedile a Ivan el rol IAM para impersonar `mds-cf-runner`, corré `gcloud auth application-default login` con `--impersonate-service-account`, copiá los dos templates de `config/` y `frontend/`, levantá `uvicorn` + `npm run dev`, abrí `localhost:3000`.

---

## 1. Prerequisitos

| Herramienta | Versión mínima | Cómo verificar |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| Google Cloud SDK | reciente | `gcloud --version` |
| git | 2.40+ | `git --version` |

Instalá lo que falte vía Homebrew (`brew install python@3.11 node gcloud`).

## 2. Permisos GCP que necesitás

Pedile a Ivan (owner del proyecto `monks-mds-dev`) que te conceda **sobre la service account `mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com`** el rol:

- `roles/iam.serviceAccountTokenCreator`

Esto te permite impersonar esa SA desde tu cuenta personal. Sin este rol, los pasos 5 y 8 de abajo van a tirar `PermissionDenied`.

## 3. Clonar el repo

```bash
mkdir -p ~/Monks/Agentes
cd ~/Monks/Agentes
git clone https://github.com/MightyHive/ingestion-agent.git
cd ingestion-agent
git checkout new-mds-deterministic
git submodule update --init --recursive
```

> **Nota:** el repo se va a renombrar a `mds`. Mientras no se haga, el clone sigue siendo `ingestion-agent`.

## 4. Configurar el archivo de tenants

```bash
mkdir -p ~/.mds
cp config/tenants.json.example ~/.mds/tenants.json
chmod 700 ~/.mds
chmod 600 ~/.mds/tenants.json
```

Editá `~/.mds/tenants.json` y dejalo así (para HTTPBackend no van credenciales en `context` — la CF las resuelve sola):

```json
{
  "tenants": {
    "dev": {
      "gcp_project": "monks-mds-dev",
      "service_account": "mds-cf-meta@monks-mds-dev.iam.gserviceaccount.com",
      "context": {}
    },
    "cliente1": {
      "gcp_project": "monks-mds-dev",
      "service_account": "mds-cf-meta@monks-mds-dev.iam.gserviceaccount.com",
      "context": {}
    }
  }
}
```

> **Importante**: este archivo vive en tu home, FUERA del repo, para que ningún `git add` accidental lo capture.

## 5. Autenticación GCP (Application Default Credentials)

```bash
gcloud auth login                                  # tu cuenta Monks
gcloud config set project monks-mds-dev
gcloud auth application-default login \
  --impersonate-service-account=mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com
gcloud auth application-default set-quota-project monks-mds-dev
```

**Validar**:

```bash
gcloud auth application-default print-access-token | head -c 20 && echo
```

Tiene que imprimir un token (no error). Si tira `PermissionDenied`, te falta el rol del paso 2.

> Las credenciales quedan guardadas en `~/.config/gcloud/application_default_credentials.json` y no necesitás repetir este paso hasta que expiren o cambies de cuenta.

## 6. Backend — instalar dependencias

```bash
cd ~/Monks/Agentes/ingestion-agent
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Smoke test rápido**:

```bash
pytest src/ingestion/tests/ -q
```

Tienen que pasar los 77 tests verdes.

**Variables de entorno opcionales del backend** (defaults entre paréntesis):

| Variable | Default | Cuándo tocarla |
|---|---|---|
| `MDS_RUNTIME` | `local` | Setealo a `http` para que el dispatcher llame a la CF real en vez de importar el conector en proceso. Lo hacés en el paso 8. |
| `MDS_CF_INVOKER_SA` | unset | SA a impersonar cuando el HTTPBackend pide un id_token vía gcloud CLI. Setealo a `mds-cf-meta@monks-mds-dev.iam.gserviceaccount.com` si tu ADC es de usuario (no SA key). Vos necesitás `roles/iam.serviceAccountTokenCreator` sobre esa SA. |
| `MDS_SECRETS_BACKEND` | `local` | Dónde guarda payloads la CRUD de credenciales. `local` → JSON en `<repo>/.credentials_secrets.json` (dev). `gcp` → Secret Manager vía gcloud CLI (cuando trabajás contra Secret Manager real). |
| `MDS_GCP_PROJECT` | `monks-mds-dev` | Proyecto para `MDS_SECRETS_BACKEND=gcp`. |
| `MDS_DB_PATH` | `<repo>/mds_credentials.db` | Path al SQLite de credenciales. El default va al repo root (gitignored). |
| `MDS_TENANTS_FILE` | `~/.mds/tenants.json` | Override del path del registry de tenants. |

Estas variables podés exportarlas a mano o ponerlas en un `.env` en la raíz del repo — el backend hace `load_dotenv()` al arrancar.

## 7. Frontend — instalar dependencias

```bash
cd frontend
cp .env.example .env.local
npm install
```

Editá `frontend/.env.local` si necesitás cambiar algo. Los defaults sirven para correr contra el backend local en el puerto 8000.

**Type-check**:

```bash
npx tsc --noEmit
```

Exit 0 = ok.

## 8. Levantar todo

**Terminal 1 — backend**:

```bash
cd ~/Monks/Agentes/ingestion-agent
source .venv/bin/activate
export MDS_RUNTIME=http
unset MDS_CF_BASE_URL
unset GOOGLE_APPLICATION_CREDENTIALS
cd src
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Por qué cada cosa:

- `cd src` + `uvicorn api:app` (no `src.api:app`) → el módulo `ingestion` vive dentro de `src/`, Python necesita que `src/` sea el working directory para encontrarlo. Correr `uvicorn src.api:app` desde la raíz da `ModuleNotFoundError: No module named 'ingestion'`.
- `MDS_RUNTIME=http` → usa `HTTPBackend`, que llama a la CF real en GCP. Sin esto, el dispatcher cae a `LocalBackend` que intenta importar el módulo del conector localmente.
- `unset MDS_CF_BASE_URL` → si esta variable estuviera seteada, el HTTPBackend apuntaría a un emulador local en lugar de la CF real.
- `unset GOOGLE_APPLICATION_CREDENTIALS` → fuerza el uso del ADC configurado en el paso 5 (`~/.config/gcloud/application_default_credentials.json`). Si estuviera seteado a un path de key JSON, usaría esas credenciales en cambio.

**Terminal 2 — frontend**:

```bash
cd ~/Monks/Agentes/ingestion-agent/frontend
npm run dev
```

Esperá a ver `Ready in X.Xs` y abrí `http://localhost:3000`.

## 9. Validar el flujo end-to-end

1. Abrí `http://localhost:3000` y mirá arriba a la derecha: tiene que estar el dropdown **CLIENT** con `cliente1` seleccionado.
2. Andá al flujo de conectores → elegí `Meta Facebook Ad Insights`.
3. Seleccioná algunos fields (por ejemplo: `account_id`, `campaign_name`, `spend`, `impressions`).
4. En `TemplateStep` confirmá que el target table muestra `bronze.meta_facebook_ad_insights_cliente1` (editable).
5. Dispará la ingesta. En los logs del backend (terminal 1) tenés que ver el request con `tenant_id: "cliente1"`.
6. Validá en BigQuery:

```bash
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS rows, MAX(ingested_at) AS last_batch
   FROM \`monks-mds-dev.bronze.meta_facebook_ad_insights_cliente1\`"
```

Tiene que devolver filas y un timestamp reciente.

7. Cambiá el dropdown a `dev` y repetí: la tabla destino tiene que pasar a `bronze.meta_facebook_ad_insights_dev` automáticamente.

## 10. Troubleshooting

| Síntoma | Causa más probable | Fix |
|---|---|---|
| `tenants file not found at ~/.mds/tenants.json` | Saltaste el paso 4 | Hacer el paso 4 |
| `PermissionDenied` al imprimir el ADC token | Falta `roles/iam.serviceAccountTokenCreator` sobre `mds-cf-runner` | Pedirle el rol a Ivan |
| El frontend levanta pero el dropdown CLIENT no aparece | `frontend/.env.local` no tiene `NEXT_PUBLIC_TENANTS` | Copiar de `.env.example` |
| `POST /api/run` devuelve 401 / 403 | Tu ADC no está impersonando `mds-cf-runner` | Repetir paso 5 con `--impersonate-service-account` |
| `POST /api/run` devuelve 500 con `connector_auth_required` | Los secretos del tenant no están en Secret Manager con la convención esperada | Ver `docs/fase5-runbook.md §3`, hablar con Facu |
| `npx tsc --noEmit` tira errores | Falta `npm install` o hay cambios sin tipar | Correr `npm install` y revisar el error |

## 11. Cargar credenciales para tu tenant (primer setup)

Para que `cliente1` corra contra Meta de verdad necesitás que haya una credencial cargada. Hay dos caminos:

**Camino A — desde la UI (recomendado para todo flujo nuevo):**

1. Levantá el backend + frontend (pasos 8).
2. Abrí `http://localhost:3000`, andá a **Credentials Library**.
3. Click "Add Connection" → elegí plataforma (META), completá `access_token` + `ad_account_id`, dale nombre/brand/market.
4. La UI llama `PUT /api/credentials/meta/<id>` → el backend escribe el secret en el backend configurado (`MDS_SECRETS_BACKEND=local` o `gcp`) y crea la row en `mds_credentials.db`.
5. La próxima vez que dispares un Run desde Export Planner, el frontend pasa `connection_id` en el body de `/api/run` y la CF resuelve ese secret.

**Camino B — importar secretos ya existentes en Secret Manager**:

Si tu tenant ya tiene secretos cargados con la convención legacy (`client_<tenant>_<provider>_<field>`), corré el script de migración:

```bash
PYTHONPATH=src python src/scripts/import_gcp_secrets.py \
  --project monks-mds-dev \
  --tenants dev,cliente1
```

El script lee los secretos viejos, los empaqueta en el formato nuevo (`{tenant}-{provider}-{connection_id}` con JSON payload) y agrega las rows correspondientes a la DB. Los secretos legacy quedan vivos: la CF cae al formato viejo cuando el request no incluye `connection_id`.

Más detalle de la CRUD (endpoints, errores, rotación, revocación) en [`api.md` §4](api.md#4-credentials) y [`fase5-runbook.md` §3](fase5-runbook.md#3-credentials-operations).

## 12. Convenciones a respetar

- **No commitear `~/.mds/tenants.json`** ni nada con credenciales. Está fuera del repo a propósito.
- **No commitear `frontend/.env.local`**, `config/tenants.json` poblado, `mds_credentials.db`, ni `.credentials_secrets.json`. Todos están en `.gitignore`.
- **Antes de cualquier `git add .`**, correr `git status` y verificar que no aparezcan archivos con material sensible. Preferí `git add <archivo>` explícito.
- **Cambios al frontend**: coordinar con Mili. La excepción de Fase 5 (selector de tenant + target table editable + CRUD credenciales wired) fue puntual; refactors o UI nueva vuelven a su cola.
- **Secrets en Secret Manager**: hoy hay dos convenciones en producción.
  - **Nueva** (usada por la CRUD): `{tenant_id}-{provider}-{connection_id}` con payload JSON `{access_token, ad_account_id, ...}`.
  - **Legacy** (bootstrap manual previo a la CRUD): `client_<tenant_id>_<platform>_<key>` con payload plano por key.

  Las dos siguen funcionando para no romper el piloto; las cargas nuevas pasan por la CRUD.

## 13. Siguientes pasos

- Arquitectura: [`docs/architecture.md`](architecture.md).
- Contrato API: [`docs/api.md`](api.md).
- Operaciones recurrentes (re-deploy CF, smoke E2E, troubleshooting, plan post-MVP): [`docs/fase5-runbook.md`](fase5-runbook.md).
- Decisión arquitectónica del refactor: [`docs/adr/001-multi-agent-to-deterministic-pipeline.md`](adr/001-multi-agent-to-deterministic-pipeline.md).
