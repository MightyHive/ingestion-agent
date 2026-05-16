# Plan de integración frontend ↔ backend determinístico
> Rama: `ik-mmi-integration` | Última edición: 2026-05-12

---

## Contexto rápido

El backend pasó de un grafo multi-agente con SSE a un pipeline determinístico sync.
El frontend todavía habla con los endpoints viejos y usa datos mockeados.

**Nuevo flujo de la API:**
1. `GET /api/catalog` → lista de conectores reales (reemplaza el array hardcodeado)
2. `GET /api/catalog/{id}` → manifest completo con `available_fields` (reemplaza el SSE de `/api/chat`)
3. `POST /api/run` → ejecuta la ingesta, devuelve DDL + preview (reemplaza `/api/submit_input` + `generateMockTemplate`)

---

## Archivos a tocar

| Archivo | Qué hacer |
|---|---|
| `connectorStore.ts` | Reescritura: sacar SSE, agregar fetch sync |
| `ConnectionStep.tsx` | Fetch `GET /api/catalog` en lugar del array hardcodeado |
| `SelectionStep.tsx` | Usar `available_fields` del manifest, sacar "reporting scope" |
| `TemplateStep.tsx` | Llamar `POST /api/run` en vez de `generateMockTemplate` |
| `useAgentStream.ts` | Eliminar (ya no hay streaming) |
| `sessions.ts` | Eliminar (ya no hay sesión) |

---

## Paso 1 — Crear helpers de API

Crear `frontend/src/lib/api/catalog.ts`:

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function fetchCatalog() {
  const res = await fetch(`${API_BASE}/api/catalog`)
  if (!res.ok) throw new Error(`GET /api/catalog → ${res.status}`)
  return res.json() // { version, count, connectors: [...] }
}

export async function fetchManifest(id: string) {
  const res = await fetch(`${API_BASE}/api/catalog/${id}`)
  if (!res.ok) throw new Error(`GET /api/catalog/${id} → ${res.status}`)
  return res.json() // manifest completo
}

export async function runIngestion(manifestId: string, params: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manifest_id: manifestId, params }),
  })
  // Guardar X-Request-Id para debug
  const requestId = res.headers.get("X-Request-Id")
  const body = await res.json()
  if (!res.ok) throw Object.assign(new Error(body.reason ?? `HTTP ${res.status}`), { requestId, body })
  return { ...body, requestId }
}
```

---

## Paso 2 — Mapping de tipos BigQuery → FieldType

Agregar en `frontend/src/lib/platforms/types.ts` (o en el nuevo `catalog.ts`):

```ts
export function bigqueryTypeToFieldType(t: string): FieldType {
  if (t === "STRING" || t === "BYTES" || t === "JSON" || t === "GEOGRAPHY" || t === "ARRAY" || t === "STRUCT") return "STRING"
  if (t === "INT64" || t === "INTEGER") return "INTEGER"
  if (t === "FLOAT64" || t === "NUMERIC" || t === "BIGNUMERIC" || t === "FLOAT") return "FLOAT"
  if (t === "BOOL" || t === "BOOLEAN") return "BOOLEAN"
  if (t === "DATE" || t === "DATETIME" || t === "TIMESTAMP" || t === "TIME") return "DATE"
  return "STRING" // fallback
}
```

---

## Paso 3 — Actualizar `connectorStore.ts`

La estrategia es **no tirar nada**: el código de SSE / mock queda intacto, y le sumamos
estado y actions nuevas encima. El `IS_MOCK` que ya existe en el archivo actúa de switch.

### 3.1 — Agregar tipos nuevos (arriba del todo, después de los tipos existentes)

```ts
// Card del catálogo (GET /api/catalog)
export interface CatalogConnector {
  id: string
  name: string
  platform: string
  status: "alpha" | "beta" | "stable" | "deprecated"
  description?: string
  available_fields_count: number
  params_summary: {
    required: string[]
    optional: string[]
    one_of: string[][]
  }
}

// Un field dentro del manifest (GET /api/catalog/{id})
export interface ManifestField {
  name: string
  type: string
  mode?: "NULLABLE" | "REQUIRED" | "REPEATED"
  description?: string
  selectable?: boolean
}

// Un parámetro del manifest
export interface ManifestParam {
  name: string
  type: string
  default?: unknown
  minimum?: number
  maximum?: number
  description?: string
}

// El manifest completo (solo lo que usa el frontend)
export interface Manifest {
  id: string
  name: string
  platform: string
  params: {
    required: ManifestParam[]
    optional: ManifestParam[]
    one_of: string[][]
  }
  available_fields: ManifestField[]
  table_naming: { bronze_pattern: string }
}

// Respuesta exitosa de POST /api/run
export interface RunResult {
  manifest_id: string
  target_table: string
  ddl: string
  columns: string[]
  row_count: number
  rows_preview: Record<string, unknown>[]
  errors: string[]
  requestId?: string
}
```

### 3.2 — Agregar helper de conversión de tipos (junto a los otros helpers)

```ts
// Convierte tipo BigQuery del manifest → FieldType del ColumnSelector
function bigqueryTypeToFieldType(t: string): FieldType {
  if (t === "INT64" || t === "INTEGER") return "INTEGER"
  if (t === "FLOAT64" || t === "NUMERIC" || t === "BIGNUMERIC") return "FLOAT"
  if (t === "BOOL" || t === "BOOLEAN") return "BOOLEAN"
  if (t === "DATE" || t === "DATETIME" || t === "TIMESTAMP" || t === "TIME") return "DATE"
  return "STRING" // STRING, JSON, BYTES, ARRAY, STRUCT → opaque
}

// Convierte available_fields del manifest → FieldRow[] para el ColumnSelector
function manifestFieldsToFieldRows(manifest: Manifest): FieldRow[] {
  return manifest.available_fields
    .filter((f) => f.selectable !== false)
    .map((f) => ({
      id: f.name,
      name: f.name,
      type: bigqueryTypeToFieldType(f.type),
      kind: "metric" as const,  // el manifest no distingue metric/dimension por ahora
      endpoint: manifest.id,
      description: f.description,
    }))
}
```

> Para que `FieldType` esté importado agregá `FieldType` al import de arriba:
> `import type { FieldRow, FieldType } from "@/lib/platforms/types"`

### 3.3 — Agregar estado nuevo en la interface `ConnectorStore`

Buscá la `interface ConnectorStore` y agregá estos campos **al final, antes del cierre `}`**:

```ts
  // --- Estado nuevo (real API path) ---
  catalogConnectors: CatalogConnector[]
  isLoadingCatalog: boolean
  catalogError: string | null
  manifest: Manifest | null
  params: Record<string, unknown>  // valores del form de parámetros (days_back, etc.)
  isRunning: boolean
  runError: string | null
  runRequestId: string | null      // para mostrar en mensajes de error
  runResult: RunResult | null

  // --- Actions nuevas ---
  loadCatalog: () => Promise<void>
  selectConnector: (id: string, name: string) => Promise<void>
  setParam: (key: string, value: unknown) => void
  runPipeline: () => Promise<void>
```

### 3.4 — Agregar el estado inicial en `initialState`

```ts
  // real API path
  catalogConnectors: [] as CatalogConnector[],
  isLoadingCatalog: false,
  catalogError: null,
  manifest: null,
  params: {} as Record<string, unknown>,
  isRunning: false,
  runError: null,
  runRequestId: null,
  runResult: null,
```

### 3.5 — Agregar las actions nuevas en el store (al final, antes de `reset`)

Las pegás después de `abortStream` y antes del `reset`:

```ts
  loadCatalog: async () => {
    if (IS_MOCK) return  // en mock el catálogo es el array hardcodeado de ConnectionStep
    set({ isLoadingCatalog: true, catalogError: null })
    try {
      const res = await fetch(`${API_BASE}/api/catalog`)
      if (!res.ok) throw new Error(`GET /api/catalog → ${res.status}`)
      const data = await res.json()
      set({ catalogConnectors: data.connectors ?? [], isLoadingCatalog: false })
    } catch (e) {
      set({ catalogError: e instanceof Error ? e.message : "Error cargando catálogo", isLoadingCatalog: false })
    }
  },

  selectConnector: async (id, name) => {
    if (IS_MOCK) {
      // Path mock: igual que antes
      const sessionId = getConnectorSessionId(id)
      get().setConnector(id, name, sessionId)
      await get().startInvestigation(sessionId, "Mock query")
    } else {
      // Path real: fetch manifest + mapea fields
      set({
        connectorId: id,
        connectorName: name,
        manifest: null,
        fields: [],
        selectedFields: [],
        templateProposal: null,
        runResult: null,
        runError: null,
        params: {},
        isInvestigating: true,       // reusamos el spinner que ya existe en SelectionStep
        investigationError: null,
      })
      try {
        const res = await fetch(`${API_BASE}/api/catalog/${id}`)
        if (!res.ok) throw new Error(`GET /api/catalog/${id} → ${res.status}`)
        const manifest: Manifest = await res.json()
        set({ manifest, fields: manifestFieldsToFieldRows(manifest), isInvestigating: false })
      } catch (e) {
        set({
          investigationError: e instanceof Error ? e.message : "Error cargando el conector",
          isInvestigating: false,
        })
      }
    }
  },

  setParam: (key, value) =>
    set((state) => ({ params: { ...state.params, [key]: value } })),

  runPipeline: async () => {
    const { connectorId, selectedFields, sessionId, params } = get()
    if (!connectorId) return

    if (IS_MOCK) {
      // Path mock: submitUserInput con SSE, igual que antes
      await get().submitUserInput(sessionId!, { columns_selected: selectedFields })
    } else {
      // Path real: POST /api/run
      set({ isRunning: true, runError: null, runRequestId: null })
      try {
        const res = await fetch(`${API_BASE}/api/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            manifest_id: connectorId,
            params: { fields: selectedFields, ...params },
          }),
        })
        const requestId = res.headers.get("X-Request-Id") ?? null
        const body = await res.json()
        if (!res.ok) {
          set({ runError: body.reason ?? `Error ${res.status}`, runRequestId: requestId, isRunning: false })
          return
        }
        const result: RunResult = { ...body, requestId }
        set({
          runResult: result,
          templateProposal: {
            tableName: result.target_table,
            ddl: result.ddl,
            columns: result.columns.map((colName) => ({
              name: colName,
              original: colName,
              type: "STRING",
              mode: "NULLABLE" as const,
            })),
          },
          isRunning: false,
        })
      } catch (e) {
        set({ runError: e instanceof Error ? e.message : "Error ejecutando el pipeline", isRunning: false })
      }
    }
  },
```

### 3.6 — Agregar el import de `getConnectorSessionId` (lo necesita `selectConnector` en mock path)

```ts
import { getConnectorSessionId } from "@/lib/sessions"
```

---

## Paso 4 — `ConnectionStep.tsx`

**Sacar:**
- Array hardcodeado `CONNECTORS`
- Import de `getConnectorSessionId` y `sessions`
- Llamada a `store.startInvestigation`

**Agregar:**
- `useEffect` que llama `store.loadCatalog()` al montar
- Render de `store.catalogConnectors` en lugar del array hardcodeado
- Loading state mientras carga
- Al hacer click: `store.selectConnector(connector.id)` + `onUpdate({ platform: connector.id })`

**Estructura de cada card desde el catálogo:**
```
connector.name         → título
connector.platform     → subtítulo / badge
connector.description  → descripción
connector.available_fields_count → "31 fields"
connector.status       → badge alpha/beta/stable
```

---

## Paso 5 — `SelectionStep.tsx`

**Sacar:**
- `isInvestigating` y `AgentProgressPanel` (ya no hay investigación async)
- El bloque "Reporting scope" con `getReportEndpoints` y `filterFieldsByReportingLevel` (el manifest no tiene esa jerarquía)
- `platformLabel`, `resolveScopeLabel`, `endpoints` — todo viene del manifest ahora

**Agregar:**
- Si `store.fields.length === 0` y `store.manifest === null`: "Seleccioná un conector primero"
- Si `store.fields.length === 0` y `store.manifest !== null`: "Este conector no tiene fields selectables"
- **Form de parámetros** del manifest: iterar `store.manifest.params.optional` y `store.manifest.params.required` para mostrar inputs (days_back → number input, date_start/date_stop → date pickers, etc.). Usar `store.setParam(key, value)`.
- El `ColumnSelector` ya existe y funciona bien — solo cambia la fuente de datos (viene de `store.fields`)

**El grupo `one_of` del manifest** hay que respetarlo:
```
params.one_of = [["days_back"], ["date_start", "date_stop"], ["since", "until"]]
```
Renderizar como radio buttons que habilitan/deshabilitan los grupos de inputs correspondientes.

---

## Paso 6 — `TemplateStep.tsx`

**Sacar:**
- `generateMockTemplate` y su `useEffect` con el `setTimeout` simulado
- Import de `buildBigQueryCreateDdl` (el DDL ahora viene del backend)
- El concepto de "Data Architect Agent proposes..." — ya no hay agente

**Agregar:**
- `useEffect` que llama `store.runPipeline()` cuando hay `selectedFields` y no hay `templateProposal` ni `runError`
- Loading: `store.isRunning` → spinner
- Error: `store.runError` → panel de error con el `requestId` para debug
- **Preview de datos**: `store.runResult.rows_preview` → tabla con las primeras filas reales
- El DDL que muestra ahora es `templateProposal.ddl` que viene directo del backend

**El `handleApprove` queda casi igual** — guarda el template en `templateStore` — pero ya no necesita recalcular el DDL con `buildBigQueryCreateDdl` porque el backend ya lo da.

---

## Paso 7 — Limpieza (sin borrar los mocks)

**No borrar** `useAgentStream.ts`, `sessions.ts` ni `mock-agent.ts`. Quedan como la rama mock, igual que hoy.

La variable `IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"` ya existe en el store — usarla como switch en cada action:

```ts
// Ejemplo en selectConnector:
selectConnector: async (id) => {
  if (IS_MOCK) {
    // lógica vieja: sessionId + startInvestigation SSE
    const sessionId = getConnectorSessionId(id)
    set({ connectorId: id, sessionId, ... })
    await get().startInvestigation(sessionId, "Mock query")
  } else {
    // lógica nueva: fetch manifest
    const manifest = await fetchManifest(id)
    const fields = mapManifestFields(manifest)
    set({ connectorId: id, connectorName: manifest.name, manifest, fields })
  }
}
```

Lo mismo para `runPipeline`:
```ts
runPipeline: async () => {
  if (IS_MOCK) {
    // lógica vieja: submitUserInput SSE
    await get().submitUserInput(get().sessionId!, { columns_selected: get().selectedFields })
  } else {
    // lógica nueva: POST /api/run
    const result = await runIngestion(...)
    set({ templateProposal: ..., runResult: result })
  }
}
```

Para arrancar con mock: `NEXT_PUBLIC_MOCK=true npm run dev`
Para arrancar con integración real: `NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev`

---

## Orden de trabajo recomendado

```
[ ] Paso 1: crear frontend/src/lib/api/catalog.ts
[ ] Paso 2: agregar bigqueryTypeToFieldType en types.ts (o en catalog.ts)
[ ] Paso 3: actualizar connectorStore.ts (es el núcleo — seguir los sub-pasos 3.1 a 3.6)
[ ] Paso 4: actualizar ConnectionStep.tsx
[ ] Paso 5: simplificar SelectionStep.tsx + agregar form de params
[ ] Paso 6: actualizar TemplateStep.tsx
[ ] Prueba end-to-end con el backend levantado
```

> `useAgentStream.ts`, `sessions.ts` y `mock-agent.ts` **no se tocan** — quedan para el path mock.

---

## Para probar

**Tenant local (obligatorio para `POST /api/run` con conectores reales):**

1. Copiá `config/tenants.json.example` → `config/tenants.json` (o editá el `config/tenants.json` ya creado).
2. Reemplazá placeholders: `gcp_project`, `ad_account_id`, `access_token` (ver `auth.context_required` del manifest Meta).
3. En la raíz del repo, en `.env`: `MDS_TENANTS_FILE=../config/tenants.json` (ver `.env.example`).
4. La API usa `tenant_id: "dev"` — la clave en JSON debe ser `"dev"`.

Alternativa: `~/.mds/tenants.json` sin `MDS_TENANTS_FILE`.

```bash
# Terminal 1: backend (recomendado — setea MDS_TENANTS_FILE automático)
./scripts/dev-api.sh

# O manual:
# export MDS_TENANTS_FILE="$(pwd)/config/tenants.json"   # desde repo root
# cd src && RUN_MODE=api uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: frontend
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Flujo a verificar:
1. Data Connection → Step 1: aparece "Facebook Ads – Ad-level Insights" (del catálogo real)
2. Click → Step 2: aparecen los 31 fields reales + form de parámetros
3. Seleccionar reporting scope + fields, Next (la ventana `days_back` va por default del manifest, no en UI)
4. Step 3: spinner → DDL real → preview con datos → Save template

---

## Notas

- `tenant_id` está hardcodeado a `"dev"` en el backend (Fase 5 lo reemplaza con header `X-Tenant-Id`). No hace falta tocar nada en el frontend ahora.
- El `X-Request-Id` de cada respuesta es clave para debug — mostrarlo en los mensajes de error.
- `rows_preview` tiene máximo 25 filas (configurable en el backend, estable por ahora).
- En Fase 5 el backend deja de devolver los datos completos y solo da preview + row_count (el insert lo hace la Cloud Function). El store no cambia — solo `runResult` tendrá menos data.
