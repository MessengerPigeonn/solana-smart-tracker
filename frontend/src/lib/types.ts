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
  score_breakdown?: Record<string, number> | null;
  security_score?: number | null;
  social_mentions?: number | null;
  early_smart_buyers?: number | null;
  volume_velocity?: number | null;
  bundle_pct?: number | null;
  bundle_held_pct?: number | null;
  bundle_risk?: string | null;
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

export interface TakeProfitTier {
  gain_pct: number;
  sell_pct: number;
}

export interface CopyTradeConfig {
  id: number;
  user_id: string;
  enabled: boolean;
  signal_types: string[];
  max_trade_sol: number;
  max_daily_sol: number;
  slippage_bps: number;
  take_profit_pct: number | null;
  take_profit_tiers: TakeProfitTier[] | null;
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

// Sports Predictions types

export interface ParlayLeg {
  pick: string;
  odds: number;
  confidence: number;
  sport: string;
  event: string;
}

export interface Prediction {
  id: number;
  sport: string;
  league: string;
  event_id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  bet_type: "moneyline" | "spread" | "total" | "player_prop" | "parlay";
  pick: string;
  pick_detail: Record<string, unknown>;
  best_odds: number;
  best_bookmaker: string;
  implied_probability: number;
  confidence: number;
  edge: number;
  reasoning: string;
  parlay_legs: ParlayLeg[] | null;
  result: "win" | "loss" | "push" | "pending" | "void" | null;
  actual_score: string | null;
  pnl_units: number | null;
  settled_at: string | null;
  created_at: string;
  odds_display: string;
}

export interface LiveScoreData {
  prediction_id: number;
  home_score: number;
  away_score: number;
  clock: string | null;
  period: string | null;
  status: string;
  bet_status: "winning" | "losing" | "push" | "unknown";
  score_display: string;
  espn_event_id: string | null;
}

export interface PlayByPlayEntry {
  id: string;
  sequence_number: number;
  text: string;
  short_text: string | null;
  clock: string | null;
  period: string | null;
  period_number: number;
  home_score: number;
  away_score: number;
  scoring_play: boolean;
  score_value: number;
  play_type: string | null;
  team_id: string | null;
  wallclock: string | null;
  extras: Record<string, unknown>;
}

export interface PlayByPlayData {
  event_id: string;
  sport: string;
  total_plays: number;
  plays: PlayByPlayEntry[];
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
}

export interface PredictionStats {
  total_predictions: number;
  win_rate: number | null;
  roi_pct: number | null;
  current_streak: number;
  best_sport: string | null;
  sport_breakdown: Record<string, {
    total: number;
    wins: number;
    losses: number;
    pushes: number;
    pnl_units: number;
    win_rate: number;
  }>;
}
