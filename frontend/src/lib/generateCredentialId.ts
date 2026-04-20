
export function generateCredentialId(platform: string, brand: string, market: string): string {
  const shortId = Math.random().toString(36).substring(2, 8);
  
  const p = platform.toLowerCase().trim();
  const b = brand.toLowerCase().trim().replace(/\s+/g, '_');
  const m = market.toLowerCase().trim().replace(/\s+/g, '_');

  if (!platform || !brand || !market) return "pending_data...";

  return `${p}_${b}_${m}_${shortId}`;
}