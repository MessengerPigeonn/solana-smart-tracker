export interface Callout {
  id: number;
  token_symbol: string;
  token_address: string;
  signal: string;
  score: number;
  reason: string;
  smart_wallets: string[];
  price_at_callout: number;
  scan_source?: string;
  token_name?: string | null;
  market_cap?: number | null;
  volume_24h?: number | null;
  liquidity?: number | null;
  holder_count?: number | null;
  rug_risk_score?: number | null;
  dexscreener_url?: string;
  created_at: string;
}
