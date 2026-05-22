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

## 11. Convenciones a respetar

- **No commitear `~/.mds/tenants.json`** ni nada con credenciales. Está fuera del repo a propósito.
- **No commitear `frontend/.env.local`** ni `config/tenants.json` poblado. Ambos están en `.gitignore`.
- **No tocar `frontend/` salvo cambios coordinados con Mili.** La excepción de Fase 5 (Niveles 1+2+3) fue puntual; cualquier UI nueva o refactor vuelve a su cola.
- **Secretos en Secret Manager**: convención `client_<tenant_id>_<platform>_<key>` (ej: `client_cliente1_meta_access_token`). El bootstrap inicial lo hace Ivan / Facu — no escribas a SM sin alinear con ellos.

## 12. Siguientes pasos

- Para entender la arquitectura: `docs/architecture.md`.
- Para el contrato de la API: `docs/api.md`.
- Para el runbook completo de Fase 5 (deploy CF, smoke E2E avanzado, plan post-MVP): `docs/fase5-runbook.md`.
- Para el checklist de cierre del MVP: `docs/mvp-phase5-checklist.md`.
