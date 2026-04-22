
export function generateCredentialId(platform: string, brand: string, market: string): string {
  const shortId = String(Math.floor(1000000 + Math.random() * 9000000));
  
  const p = platform.toLowerCase().trim();
  const b = brand.toLowerCase().trim().replace(/\s+/g, '_');
  const m = market.toLowerCase().trim().replace(/\s+/g, '_');

  if (!platform || !brand || !market) return "pending_data...";

  return `${p}_${b}_${m}_${shortId}`;
}