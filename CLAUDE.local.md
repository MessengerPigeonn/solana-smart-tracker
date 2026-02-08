# Solana Smart Tracker

Solana memecoin scanner and smart money tracker with callout/alert system.

## Architecture

Monorepo with two services:
- `backend/` — Python FastAPI + SQLAlchemy async + Alembic migrations
- `frontend/` — Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui + Radix

Production database: PostgreSQL (Railway). Local dev: SQLite (`smart_tracker.db`).

## Deployment — Railway

- **Project**: `loyal-clarity`
- **Frontend service**: `brilliant-education` → `solanatracker.up.railway.app`
- **Backend service**: `solana-smart-tracker` → `solana-smart-tracker-production.up.railway.app`
- **Database**: PostgreSQL at `centerbeam.proxy.rlwy.net:42424/railway` (user: postgres, pass: dRNLZYuNZkeGjNXvuiOjEMWguhuFSdmr)
- Push to `main` triggers auto-deploy on both services
- Use `railway logs -n 30` to check deploy status (use `-s <service>` to target a specific service)
- Use `railway variables` to check env vars, `railway variables -s <service>` for specific service

## Production DB Access

`psql` is not installed locally. Use the backend venv with asyncpg instead:
```bash
cd backend && source venv/bin/activate && python3 -c "
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect(host='centerbeam.proxy.rlwy.net', port=42424, user='postgres', password='dRNLZYuNZkeGjNXvuiOjEMWguhuFSdmr', database='railway')
    # ... queries here ...
    await conn.close()
asyncio.run(main())
"
```

## Build & Run

```bash
# Frontend
cd frontend && npm run build     # typecheck + build
cd frontend && npm run dev       # local dev server on :3000

# Backend
cd backend && pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload   # local dev on :8000

# Migrations
cd backend && alembic upgrade head            # run migrations
cd backend && alembic revision --autogenerate -m "description"  # new migration
```

## Backend Structure

- `app/api/` — Route handlers (tokens, callouts, auth, wallets, smart_money, payments)
- `app/models/` — SQLAlchemy models (token, callout, user, tracked_wallet, trader_snapshot, payment)
- `app/schemas/` — Pydantic request/response schemas
- `app/services/` — Business logic (scanner, callout_engine, print_scanner, birdeye, helius, dexscreener, jupiter_price, wallet_analytics, stripe_service, sol_payments)
- `app/workers/` — Background workers (callout_worker)
- `app/config.py` — Settings via pydantic-settings (env vars from `.env`)
- User tiers: `free`, `pro`, `legend` (enum in `models/user.py`)

## Frontend Structure

- `src/app/dashboard/` — Pages: scanner, callouts, wallets, smart-money, billing
- `src/components/` — Shared components (token-table, callout-card, callout-feed, trading-links, navbar, etc.)
- `src/lib/api.ts` — Fetch wrapper with JWT token refresh. `API_BASE` from `NEXT_PUBLIC_API_URL` env var
- `src/lib/trading-platforms.ts` — Trading platform configs (Photon, BullX, Axiom, Jupiter, Padre)
- `src/lib/types.ts` — Shared TypeScript interfaces (Callout, CalloutStats, MilestoneCounts, etc.)
- `src/lib/utils.ts` — Formatting helpers (formatCurrency, formatAddress, formatPercent)
- `src/components/ui/` — shadcn/ui primitives

## Trading Platform URLs

These are the correct deep-link formats. Do NOT change without verifying against the platform's actual routing:
- **Photon**: `https://photon-sol.tinyastro.io/en/lp/{address}`
- **BullX NEO**: `https://neo.bullx.io/terminal?chainId=1399811149&address={address}`
- **Axiom**: `https://axiom.trade/t/{address}`
- **Jupiter**: `https://jup.ag/swap/SOL-{address}`
- **Padre Terminal**: `https://trade.padre.gg/trade/solana/{address}` (requires `/trade/solana/` prefix — discovered by reverse-engineering their SPA bundle)

## Pricing & Payments

- **USD prices** (Stripe): Pro $199/mo, Legend $999/mo
- **SOL prices**: Dynamic — calculated as `(USD price * 0.90) / live SOL price` (10% discount)
- SOL/USD price fetched via cascade: Jupiter → CoinGecko → DexScreener (with 60s cache)
- `GET /api/payments/sol/pricing` returns live SOL amounts per tier
- Stripe price IDs are NOT set in Railway env vars — backend auto-provisions products/prices via `_get_or_create_price()` in `stripe_service.py`
- Frontend wallet provider uses Helius RPC (`NEXT_PUBLIC_HELIUS_RPC_URL` env var on `brilliant-education` service). Public Solana RPC rate-limits and returns 403.
- Helius API key: `fcc77d84-2a3f-4b9d-8af3-0f6a88fce228` (used by both backend and frontend RPC)

## Callout Engine

- **Thresholds**: BUY >= 65, WATCH >= 45
- **Quality gate**: mcap > 0, liquidity >= $5K (trending) / $1K (print_scan)
- **12-factor scoring** (v2, Feb 2026): Replaced 6-factor linear system with weighted multi-factor scoring
  - **Trending (mcap >= $500K)**: Smart Wallet Signal (20), Volume Velocity (15), Buy Pressure (12), Early Buyer Quality (12), Price Momentum (10), Token Freshness (8), Holder Distribution (8), Liquidity Health (5), Security Score (5), Social Signal (5), Wallet Overlap (+5 bonus), Anti-Rug Gate (-20 penalty)
  - **Micro-cap (PrintScan)**: Security Safety (25), Early Buyer Quality (15), Holder Distribution (15), Volume Velocity (12), Freshness (10), Buy Pressure (8), Liquidity Floor (5), Social Signal (5), Wallet Overlap (+5 bonus), Anti-Rug Gate (-30 penalty)
  - Exponential freshness decay: `exp(-age/decay_constant)` instead of step functions
  - Smart wallet classification weights: sniper 3x, KOL 2x, whale 2x, insider 1.5x, smart_money 1x
  - Volume velocity = rate of change across last 3 TokenSnapshot cycles
  - Callouts store `score_breakdown` JSON, `security_score`, `social_mentions`, `early_smart_buyers`, `volume_velocity`
- **New services**: `rugcheck.py` (Rugcheck.xyz API), `social_signals.py` (DexScreener social heuristics), `wallet_classifier.py` (SmartWallet reputation), `onchain_analyzer.py` (Helius early buyer detection)
- **New models**: `SmartWallet` (wallet reputation), `TokenSnapshot` (volume velocity time-series)
- **Dedup**: One buy/watch callout per token EVER. No re-callouts at different market caps. Sell signals dedup at 24h.
- **Repin feature**: Instead of creating duplicate callouts, tokens gaining traction get their original callout resurfaced to top of feed:
  - Trigger: score rises by >= 10 points (`REPIN_SCORE_DELTA = 10`)
  - Cooldown: 6 hours between repins (`REPIN_COOLDOWN_HOURS = 6`)
  - Updates `repinned_at` timestamp, `score`, `reason` on existing callout
  - Auto-upgrades watch → buy if new score >= BUY_THRESHOLD
  - Feed sorts by `COALESCE(repinned_at, created_at) DESC` so repinned callouts float to top
  - Frontend shows blue "GAINING" badge with Pin icon when `repinned_at` is set
  - Entry price and market cap preserved from original callout (important for accurate stats)
- **Avg Return stat**: Floored at 1.2x for coins whose ATH peaked >= 1.2x (even if they dropped to 0 after)
- **Milestone counts**: Tracks how many coins hit +20%, +40%, +60%, +80%, 2x, 5x, 10x, 50x, 100x based on ATH multipliers
- **Stats endpoint**: `GET /api/callouts/stats` — last 100 buy/watch callouts, returns avg_multiplier, avg_ath_multiplier, win_rate, best_call, milestones
- **Peak tracking**: `peak_market_cap` column on callouts model, updated by callout worker

## Known Gotchas

- **Scanner table uses bare `<a href>` tags** instead of the `<TradingLinks>` component for the quick buy column. This is intentional — the table auto-refreshes every 10-15s and React `window.open` callbacks can capture stale closure values. HTML `href` attributes with inline URLs are immune to this. The `<TradingLinks>` component still works correctly in the expanded row and on the callout cards.
- **PrintScan tab** defaults to mcap_max $500K filter. Auto-refresh is 10s (vs 15s for other tabs).
- **Alembic migrations**: Follow pattern in `backend/alembic/versions/`. Current head is `008_add_take_profit_tiers.py`.
- **Jupiter Price API v2 requires auth now** — don't rely on it for SOL/USD price. DexScreener fallback works reliably from Railway.
- **Railway outbound network**: Jupiter and CoinGecko can be flaky from Railway. DexScreener and Helius work reliably.
- **Python version**: Production runs Python 3.12 (Docker). Local venv is Python 3.9 — watch for syntax differences (e.g. `float | None` type unions work in 3.12 but need `Optional` in 3.9).
- **Email handling**: Registration and login use case-insensitive email matching (`func.lower()`). Emails are normalized to lowercase on registration. This prevents duplicate accounts from users typing their email with different casing.

## ESPN Play-by-Play & Live Tracker

- **Backend**: `app/services/espn_scores.py` — `ESPNScoreProvider` handles both scoreboard and play-by-play
- **API endpoint**: `GET /api/predictions/{id}/plays` — returns last 25 plays for a prediction's game
- **Frontend component**: `src/components/play-by-play-feed.tsx` — rendered inside `prediction-card.tsx` for live/final games
- **Soccer pitch visualization**: SVG mini-map with ball position + direction arrows from ESPN field coordinates. Hero pitch at top, inline pitch on key events (goals, cards, subs).

### ESPN Core Plays API Gotchas
- URL format: `/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/plays` — **must include `/leagues/` segment**
- Max page size is **50** (returns 404 for limit>50)
- Soccer plays often lack `text` field (fallback to `shortText` then `type.text`)
- Soccer plays have no `sequenceNumber` (sort by play `id` instead)
- Soccer `period` has no `displayValue`, only `number` — backend generates "1st Half"/"2nd Half"
- Soccer plays include `fieldPositionX/Y` and `fieldPosition2X/Y` (0-1 normalized) for pitch visualization
- Soccer extras also pass through `eventType`, `redCard`, `yellowCard`

### Player Prop Betting
- **Backend**: `app/services/prediction_engine.py` → `_analyze_player_props()`
- **Odds source**: The Odds API per-event endpoint `GET /v4/sports/{key}/events/{id}/odds` (1 credit per call)
- **Prop markets** defined in `PROP_MARKETS` dict in `odds_provider.py`:
  - NFL: `player_pass_tds,player_pass_yds,player_rush_yds,player_anytime_td`
  - NBA: `player_points,player_rebounds,player_assists,player_threes`
  - NHL: `player_points,player_assists`
  - MLB: `batter_total_bases,pitcher_strikeouts`
- **Two prop patterns**:
  - Over/Under (has `point` field): consensus line from median, edge = consensus_prob - best_prob + line bonus
  - Anytime/Yes-No (no `point`): consensus implied prob across books, find best price
- **Per-event API field mapping** (different from bulk endpoint!): `name` = side ("Over"/"Under"/"Yes"), `description` = player name
- Only fetches props for events within **72 hours** (avoids wasting credits on distant events)
- Min 3 bookmakers required (vs 4 for main markets — fewer books carry props)
- **Dedup**: Uses 3-tuple `(event_id, "player_prop", pick_text)` so multiple props per event are allowed
- **Settlement**: Via ESPN box scores (`espn_scores.py` → `get_box_score()`). Maps `player_points`→PTS, `player_rebounds`→REB, `player_assists`→AST, `player_threes`→3PT(made). DNP Over→void, DNP Under→win. Players not on roster→void.
- **Labels**: `PROP_MARKET_LABELS` dict maps market keys to clean display names ("Anytime TD", "Pass TDs", etc.)
- Frontend displays props with "Prop" badge via existing `BET_TYPE_LABELS` in `prediction-card.tsx`

### Scoring Rework (Feb 2026)
- Analysis of 51 settled bets: ML 68.8% WR (+4.88u), totals 58.8% (+2.38u), spreads 35.3% (-3.42u)
- **Confidence was NOT predictive** (82.8 avg wins vs 81.6 losses) — completely rewrote `score_pick()`
- **Sharp book weighting**: Pinnacle/BetOnline get 2x weight in consensus, DraftKings/FanDuel get 0.7x
- `SHARP_BOOKS`, `MID_BOOKS`, `SOFT_BOOKS` sets in prediction_engine.py
- `weighted_consensus_prob()` and `sharp_book_agreement()` helper functions
- **score_pick() v2 weights** (winner-focused, not arbitrage-based):
  - Consensus Strength 40% (0-40pts): Tiered — 72%+ = 40, 65%+ = 36, 58%+ = 32, 50%+ = 26, 40%+ = 18, 30%+ = 12, else 6
  - Edge Quality 20% (0-20pts): Tiered with diminishing returns — 10%+ = 20, 7%+ = 17, 5%+ = 14, 4%+ = 10
  - Sharp Agreement 20% (0-20pts): Base (2+ sharps = 15, 1 = 8) + interaction bonus (sharp + 60%+ consensus = +5)
  - Book Breadth 10% (0-10pts): `min(num_books * 1.5, 10)` (unchanged)
  - Sport Reliability 10% (0-10pts): NBA/NFL 1.0, Soccer 0.95, MLB/NHL 0.9 (unchanged)
- Key score shifts: 72% consensus favorite 63→89, 40% arb trap 73→51, 25% longshot 64→37
- Min edge raised from 2% to 4% (`prediction_min_edge` in config.py)
- Spreads disabled by default (`prediction_spreads_enabled = False`)
- Under/No picks now generated for props (was previously Over/Yes only)
- Parlay probability bug fixed (was double-inverting implied prob)
- Tests: 20 tests in `backend/tests/test_score_pick.py`

### Prediction Settlement
- Worker in `app/workers/prediction_worker.py` runs on interval
- Settlement logic in `app/services/prediction_engine.py` → `settle_predictions()`
- Uses The Odds API `/v4/sports/{key}/scores?daysFrom=3` to get final scores
- Matches by `event_id` from The Odds API (not ESPN event_id — these are different IDs)
- Can take a few minutes after game ends for Odds API to report final scores
