# Guía de migración Terraform — GCP `monks-mds-dev`

> **Objetivo:** Documentar el proceso de migrar infraestructura GCP creada manualmente a Terraform,
> de forma segura y reproducible, sin destruir nada existente.
>
> Este documento sirve como referencia para el equipo y como guía para migrar futuros servicios.

---

## Índice

1. [Conceptos clave](#1-conceptos-clave)
2. [Estructura del repositorio](#2-estructura-del-repositorio)
3. [Qué hicimos paso a paso](#3-qué-hicimos-paso-a-paso)
4. [Cómo agregar un nuevo servicio](#4-cómo-agregar-un-nuevo-servicio)
5. [Referencia de módulos](#5-referencia-de-módulos)
6. [Servicios migrados](#6-servicios-migrados)
7. [Pendiente](#7-pendiente)

---

## 1. Conceptos clave

### `terraform.tfvars` — lo que *querés* que exista

Es el archivo donde declarás tu intención: qué APIs activar, qué Cloud Functions tener, etc.
Lo editás vos. Está gitignoreado porque puede contener valores distintos por ambiente.

### `terraform.tfstate` — lo que Terraform *sabe* que existe

Terraform guarda acá un mapa de todo lo que ya creó (o importó) en GCP.
**No lo editás a mano nunca.** Terraform lo gestiona solo.

### Backend GCS — dónde vive el state compartido

Sin backend, el `terraform.tfstate` vive en tu máquina local.
Si otra persona del equipo corre `apply`, no tiene tu state → piensa que no hay nada creado → intenta recrear todo → 💥

Con backend GCS, el state vive en un bucket compartido:

```
Tu compu          GCS Bucket
--------          ----------
terraform  ←───  monks-mds-tfstate/
  plan            ├── monks-mds-dev/terraform.tfstate
  apply           └── monks-mds-prod/terraform.tfstate
```

También **lockea el state** mientras alguien está corriendo un apply, para que dos personas no pisen el trabajo de la otra.

### `terraform import` — adoptar recursos que ya existen

Cuando la infraestructura ya está creada en GCP (a mano, por gcloud, etc.),
Terraform no sabe que existe. El import le dice:
> "Este recurso que declaré en el código ya existe en GCP con este ID — registralo en el state."

Después del import, `terraform plan` no debería mostrar cambios para ese recurso.

### Por qué `plan` limpio = todo bien

`terraform plan` compara tres cosas:

```
Lo que declaraste     Lo que hay en        Lo que hay realmente
en .tf / .tfvars  vs  terraform.tfstate vs  en GCP
```

Si el plan dice `No changes` → las tres cosas coinciden → tu código documenta fielmente lo que existe en GCP.

---

## 2. Estructura del repositorio

```
terraform/
├── .gitignore
├── environments/
│   ├── dev/
│   │   ├── main.tf                   # Provider, backend, módulos
│   │   ├── variables.tf              # Declaración de variables
│   │   ├── terraform.tfvars          # Valores reales (gitignoreado)
│   │   └── terraform.tfvars.example  # Ejemplo commiteado al repo
│   └── prod/
│       ├── main.tf
│       ├── variables.tf
│       └── terraform.tfvars
├── modules/
    ├── apis/
    │   ├── main.tf       # google_project_service con for_each
    │   ├── variables.tf
    │   └── outputs.tf
    ├── cloud_functions/
    │   ├── main.tf       # google_cloudfunctions2_function con for_each
    │   ├── variables.tf
    │   └── outputs.tf
    └── iam/
        ├── main.tf       # stub — aún sin recursos
        ├── variables.tf
        └── outputs.tf

```

### Reglas del repo

| Archivo | ¿Se commitea? | Por qué |
|---|---|---|
| `terraform.tfvars` | ❌ No | Puede tener valores sensibles o distintos por persona |
| `terraform.tfvars.example` | ✅ Sí | Referencia para el equipo |
| `terraform.tfstate` | ❌ Nunca | Vive en GCS, puede tener secrets |
| `.terraform/` | ❌ No | Generado por `terraform init`, pesa mucho |
| Todos los `.tf` | ✅ Sí | Son el código fuente |

---

## 3. Qué hicimos paso a paso

### Paso 1 — Auditoría inicial

Corrimos `gcloud services list --project=monks-mds-dev` para ver qué APIs estaban habilitadas en GCP.
Comparamos esa lista con lo que había declarado en Terraform.

**Resultado:**
- 39 APIs habilitadas en GCP
- 20 declaradas en Terraform
- 19 sin gestionar (la mayoría foundational/Google-managed, sin riesgo)


### Paso 2 — Configuración del backend GCS

En `environments/dev/main.tf` y `environments/prod/main.tf` se agregó el backend con prefijos separados:

```hcl
backend "gcs" {
  bucket = "monks-mds-tfstate"
  prefix = "monks-mds-dev/apis"   # prod usa "monks-mds-prod/apis"
}
```

> ⚠️ El bucket debe existir antes de correr `terraform init`.
> Crearlo con: `gsutil mb -p monks-mds-dev gs://monks-mds-tfstate`

### Paso 3 — Módulo de APIs

Se usa `google_project_service` con `for_each` para habilitar cada API como un recurso independiente:

```hcl
resource "google_project_service" "apis" {
  for_each = toset(var.apis)
  project  = var.project_id
  service  = each.value

  disable_on_destroy         = false  # si borrás el recurso del código, la API no se deshabilita en GCP
  disable_dependent_services = false
}
```

**Por qué `disable_on_destroy = false` es importante:**
Si alguien accidentalmente borra una API del tfvars, Terraform la saca del state pero **no la deshabilita en GCP**. Esto evita cortes de servicio.

### Paso 4 — Módulo de Cloud Functions (Gen 2)

La función existente es **Gen 2**, que en Terraform usa `google_cloudfunctions2_function`.
Gen 1 y Gen 2 son recursos completamente distintos — no son intercambiables.

```hcl
resource "google_cloudfunctions2_function" "functions" {
  for_each = var.cloud_functions

  name     = each.key
  location = each.value.region
  project  = var.project_id

  build_config {
    runtime     = each.value.runtime
    entry_point = each.value.entry_point
    source {
      storage_source {
        bucket = each.value.source_bucket
        object = each.value.source_object
      }
    }
  }

  service_config {
    service_account_email            = each.value.service_account_email
    available_memory                 = each.value.available_memory
    timeout_seconds                  = each.value.timeout_seconds
    max_instance_count               = each.value.max_instance_count
    max_instance_request_concurrency = each.value.max_instance_request_concurrency
    ingress_settings                 = each.value.ingress_settings
    all_traffic_on_latest_revision   = true
    environment_variables            = each.value.environment_variables
  }
}
```

### Paso 5 — `terraform init`

```bash
cd terraform/environments/dev
terraform init
```

Esto:
- Descarga los providers declarados (hashicorp/google ~> 5.0)
- Conecta con el backend GCS
- Crea `.terraform/` localmente (gitignoreado)

### Paso 6 — Import de recursos existentes

Como la infraestructura ya existía en GCP, hay que "adoptarla" al state.

**Formato del comando:**
```bash
terraform import 'RESOURCE_ADDRESS' 'IMPORT_ID'
```

**Para APIs** — formato `PROJECT_ID/SERVICE_NAME`:
```bash
terraform import 'module.apis.google_project_service.apis["bigquery.googleapis.com"]' \
  monks-mds-dev/bigquery.googleapis.com
```

**Para Cloud Functions Gen 2** — formato de path completo:
```bash
terraform import \
  'module.cloud_functions.google_cloudfunctions2_function.functions["meta-facebook-insights"]' \
  'projects/monks-mds-dev/locations/us-central1/functions/meta-facebook-insights'
```

> La diferencia de formato entre APIs y Cloud Functions es importante:
> cada tipo de recurso GCP tiene su propio formato de import ID.
> Siempre verificarlo en la [documentación del provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs).

### Paso 7 — Verificación con `terraform plan`

```bash
terraform plan
```

**Si el output dice `No changes. Your infrastructure matches the configuration.`** →
El código Terraform documenta fielmente lo que existe en GCP. Todo bien.

**Si muestra cambios** → hay una diferencia entre lo declarado y lo real.
Puede ser un campo que falta en el tfvars (memoria, timeout, variable de entorno, etc.)
o un campo que Terraform maneja distinto al valor por defecto de GCP.

---

## 4. Cómo agregar un nuevo servicio

### Caso A — Nueva API a habilitar

1. Agregar al `terraform.tfvars` de dev:
```hcl
apis = [
  # ... las que ya están
  "nuevaapi.googleapis.com",
]
```

2. Correr `terraform plan` → debe mostrar 1 recurso a crear.
3. Correr `terraform apply`.
4. Si la API **ya estaba habilitada** en GCP, importar primero:
```bash
terraform import \
  'module.apis.google_project_service.apis["nuevaapi.googleapis.com"]' \
  monks-mds-dev/nuevaapi.googleapis.com
```

---

### Caso B — Nueva Cloud Function existente

1. Obtener los datos reales de GCP:
```bash
gcloud functions describe NOMBRE_FUNCION --project=monks-mds-dev
```

2. Agregar al `terraform.tfvars`:
```hcl
cloud_functions = {
  "nombre-funcion" = {
    region      = "us-central1"
    runtime     = "python311"
    entry_point = "run"

    source_bucket = "gcf-v2-sources-XXXX-us-central1"
    source_object = "nombre-funcion/function-source.zip"

    service_account_email            = "sa@proyecto.iam.gserviceaccount.com"
    available_memory                 = "1Gi"
    timeout_seconds                  = 540
    max_instance_count               = 5
    max_instance_request_concurrency = 1
    ingress_settings                 = "ALLOW_ALL"

    environment_variables = {
      GCP_PROJECT = "monks-mds-dev"
    }
  }
}
```

3. Importar:
```bash
terraform import \
  'module.cloud_functions.google_cloudfunctions2_function.functions["nombre-funcion"]' \
  'projects/monks-mds-dev/locations/us-central1/functions/nombre-funcion'
```

4. Correr `terraform plan` → verificar `No changes`.

---

### Caso C — Recurso nuevo (no existe en GCP todavía)

1. Declararlo en el módulo correspondiente y en el tfvars.
2. Correr `terraform plan` → revisar que el plan sea el esperado.
3. Correr `terraform apply` → Terraform lo crea.
4. No hace falta import porque Terraform lo crea él mismo.

---

### Caso D — Nuevo tipo de recurso (ej: BigQuery dataset, Pub/Sub topic)

Si es un tipo de recurso que todavía no tiene módulo:

1. Crear `modules/NOMBRE_MODULO/main.tf`, `variables.tf`, `outputs.tf`
2. Agregar el módulo a `environments/dev/main.tf`
3. Agregar la variable a `environments/dev/variables.tf`
4. Agregar los valores a `terraform.tfvars`
5. Si el recurso ya existe en GCP → importar (ver formato de import ID en la doc del provider)
6. `terraform plan` → `No changes`

---

## 5. Referencia de módulos

### `modules/apis`

Habilita APIs de GCP. Usa `google_project_service` con `for_each`.

| Variable | Tipo | Descripción |
|---|---|---|
| `project_id` | `string` | ID del proyecto GCP |
| `apis` | `list(string)` | Lista de APIs a habilitar |

**Resource address:**
```
module.apis.google_project_service.apis["SERVICE.googleapis.com"]
```

**Import ID format:**
```
PROJECT_ID/SERVICE.googleapis.com
```

---

### `modules/cloud_functions`

Gestiona Cloud Functions Gen 2. Usa `google_cloudfunctions2_function` con `for_each`.

| Variable | Tipo | Descripción |
|---|---|---|
| `project_id` | `string` | ID del proyecto GCP |
| `cloud_functions` | `map(object)` | Mapa de funciones (ver estructura abajo) |

**Estructura del objeto:**

| Campo | Tipo | Ejemplo |
|---|---|---|
| `region` | string | `"us-central1"` |
| `runtime` | string | `"python311"` |
| `entry_point` | string | `"run"` |
| `source_bucket` | string | `"gcf-v2-sources-..."` |
| `source_object` | string | `"funcion/function-source.zip"` |
| `service_account_email` | string | `"sa@proyecto.iam..."` |
| `available_memory` | string | `"1Gi"` |
| `timeout_seconds` | number | `540` |
| `max_instance_count` | number | `5` |
| `max_instance_request_concurrency` | number | `1` |
| `ingress_settings` | string | `"ALLOW_ALL"` |
| `environment_variables` | map(string) | `{ GCP_PROJECT = "..." }` |

**Resource address:**
```
module.cloud_functions.google_cloudfunctions2_function.functions["NOMBRE"]
```

**Import ID format:**
```
projects/PROJECT_ID/locations/REGION/functions/NOMBRE
```

---

### `modules/iam`

**Estado: stub.** Sin recursos todavía.

> ⚠️ Cuando se implemente, usar siempre `google_project_iam_member` (aditivo).
> **Nunca** `google_project_iam_policy` (autoritativo — pisa todos los permisos existentes).

---

## 6. Servicios migrados

### APIs — `monks-mds-dev`

| API | Gestionada por Terraform |
|---|---|
| `analyticshub.googleapis.com` | ✅ |
| `artifactregistry.googleapis.com` | ✅ |
| `bigquery.googleapis.com` | ✅ |
| `bigqueryconnection.googleapis.com` | ✅ |
| `bigquerydatapolicy.googleapis.com` | ✅ |
| `bigquerydatatransfer.googleapis.com` | ✅ |
| `bigquerymigration.googleapis.com` | ✅ |
| `bigqueryreservation.googleapis.com` | ✅ |
| `bigquerystorage.googleapis.com` | ✅ |
| `cloudbuild.googleapis.com` | ✅ |
| `cloudfunctions.googleapis.com` | ✅ |
| `containerregistry.googleapis.com` | ✅ |
| `dataform.googleapis.com` | ✅ |
| `dataplex.googleapis.com` | ✅ |
| `datastore.googleapis.com` | ✅ |
| `pubsub.googleapis.com` | ✅ |
| `run.googleapis.com` | ✅ |
| `secretmanager.googleapis.com` | ✅ |
| `source.googleapis.com` | ✅ |
| `storage.googleapis.com` | ✅ |

APIs habilitadas en GCP pero no gestionadas por Terraform (foundational/Google-managed):

| API | Razón |
|---|---|
| `cloudapis.googleapis.com` | Meta API, auto-habilitada por Google |
| `cloudresourcemanager.googleapis.com` | Foundational, requerida para automatización |
| `iam.googleapis.com` | Core IAM, casi siempre activa |
| `iamcredentials.googleapis.com` | Auto-habilitada con workloads IAM |
| `logging.googleapis.com` | Observabilidad default de GCP |
| `monitoring.googleapis.com` | Observabilidad default de GCP |
| `servicemanagement.googleapis.com` | Infraestructura de APIs |
| `serviceusage.googleapis.com` | Usada para habilitar otras APIs |
| `storage-api.googleapis.com` | Companion de storage |
| `storage-component.googleapis.com` | Companion de storage |
| `containeranalysis.googleapis.com` | Companion de Artifact Registry |
| `telemetry.googleapis.com` | OpenTelemetry, default emergente |
| `servicehealth.googleapis.com` | Service Health, bajo impacto |
| `cloudsecuritycompliance.googleapis.com` | Confirmar si es org policy |
| `containerthreatdetection.googleapis.com` | Confirmar si es org policy |
| `websecurityscanner.googleapis.com` | Posiblemente legacy para este stack |
| `cloudtrace.googleapis.com` | Agregar si se usa Cloud Trace activamente |
| `sql-component.googleapis.com` | Agregar solo si hay Cloud SQL |

### Cloud Functions — `monks-mds-dev`

| Función | Runtime | Gen | Estado |
|---|---|---|---|
| `meta-facebook-insights` | python311 | 2nd gen | ✅ Importada |

---

## 7. Pendiente

### Por migrar a Terraform

- [ ] Service Accounts existentes en dev
- [ ] BigQuery datasets / tables
- [ ] Pub/Sub topics y subscriptions
- [ ] Cloud Run services
- [ ] Secret Manager secrets (la existencia del secret, no el valor)
- [ ] Artifact Registry repositories
- [ ] Cloud Scheduler jobs (si los hay)

### Infraestructura pendiente de definir

- [ ] Bucket GCS para el backend de state (`monks-mds-tfstate`)
- [ ] Módulo IAM — definir qué SAs y roles gestiona Terraform
- [ ] Configuración de prod — project ID, API list, backend prefix
- [ ] CI/CD pipeline para Terraform (WIF o SA key en Secret Manager)


---

*Documento generado durante la migración inicial — Mayo 2026.*
*Actualizar a medida que se migren nuevos servicios.*
