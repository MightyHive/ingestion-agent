function clean(s: string): string {
  return s.toLowerCase().trim().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "")
}

export function buildExportTableName(
  region: string,
  brand: string,
  platform: string,
  endpoint: string
): string {
  return `01_bronze_${clean(brand)}_${clean(region)}_${clean(platform)}_${clean(endpoint)}`
}
