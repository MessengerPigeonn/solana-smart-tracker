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
  peak_market_cap?: number | null;
  dexscreener_url?: string;
  created_at: string;
}

export interface CalloutStats {
  total_calls: number;
  avg_multiplier?: number | null;
  avg_ath_multiplier?: number | null;
  win_rate?: number | null;
  best_call_symbol?: string | null;
  best_call_address?: string | null;
  best_call_ath_multiplier?: number | null;
  buy_signals: number;
  watch_signals: number;
  sell_signals: number;
}

export interface TopCallout {
  callout: Callout;
  ath_multiplier: number;
  current_multiplier?: number | null;
  current_market_cap?: number | null;
}
