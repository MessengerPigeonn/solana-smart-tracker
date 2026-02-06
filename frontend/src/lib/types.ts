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
  repinned_at?: string | null;
  dexscreener_url?: string;
  created_at: string;
}

export interface MilestoneCounts {
  pct_20: number;
  pct_40: number;
  pct_60: number;
  pct_80: number;
  x2: number;
  x5: number;
  x10: number;
  x50: number;
  x100: number;
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
  milestones: MilestoneCounts;
}

export interface TopCallout {
  callout: Callout;
  ath_multiplier: number;
  current_multiplier?: number | null;
  current_market_cap?: number | null;
}

// Copy Trade types

export interface CopyTradeConfig {
  id: number;
  user_id: string;
  enabled: boolean;
  signal_types: string[];
  max_trade_sol: number;
  max_daily_sol: number;
  slippage_bps: number;
  take_profit_pct: number | null;
  stop_loss_pct: number | null;
  cooldown_seconds: number;
  min_score: number;
  max_rug_risk: number | null;
  min_liquidity: number;
  min_market_cap: number;
  skip_print_scan: boolean;
  trading_wallet_pubkey: string | null;
  created_at: string;
  updated_at: string;
}

export interface CopyTradeRecord {
  id: number;
  user_id: string;
  callout_id: number;
  token_address: string;
  token_symbol: string;
  side: "buy" | "sell";
  sol_amount: number;
  token_amount: number;
  price_at_execution: number;
  slippage_bps: number;
  tx_signature: string | null;
  tx_status: "pending" | "confirmed" | "failed";
  error_message: string | null;
  parent_trade_id: number | null;
  sell_trigger: string | null;
  pnl_sol: number | null;
  pnl_pct: number | null;
  created_at: string;
}

export interface TradingWallet {
  id: number;
  user_id: string;
  public_key: string;
  balance_sol: number;
  balance_updated_at: string | null;
  created_at: string;
}

export interface OpenPosition {
  trade_id: number;
  callout_id: number;
  token_address: string;
  token_symbol: string;
  entry_sol: number;
  token_amount: number;
  entry_price: number;
  current_price: number | null;
  unrealized_pnl_sol: number | null;
  unrealized_pnl_pct: number | null;
  created_at: string;
}
