# Test Coverage Analysis

**Date:** 2026-02-08
**Current coverage:** ~1% (1 test file out of 111 source files)

## Existing Tests

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/test_score_pick.py` | 20 | `score_pick()` in `prediction_engine.py` |

## Priority 1 — Critical

### 1. Callout Engine Scoring (`callout_engine.py` — 740 lines)
The 12-factor scoring algorithm with weighted calculations, exponential decay, anti-rug penalties, and threshold gates. No tests.

**Suggested tests:**
- Each of the 12 scoring factors independently
- Score boundary conditions (0, 100)
- Trending vs. micro-cap weight differences
- Quality gate enforcement (mcap > 0, liquidity >= $5K/$1K)
- BUY (>= 65) and WATCH (>= 45) threshold classification
- Repin score delta and cooldown logic

### 2. Copy Trade Executor (`copy_trade_executor.py`, `jupiter_swap.py` — 466 lines)
Real on-chain Solana trade execution with user funds. No tests.

**Suggested tests:**
- Slippage calculation
- Transaction building (mock RPC)
- Failure handling (insufficient balance, RPC errors, no route)
- Position sizing logic

### 3. Payment Processing (`stripe_service.py`, `sol_payments.py` — 423 lines)
Stripe webhooks, SOL payment verification, dynamic pricing. No tests.

**Suggested tests:**
- Webhook signature validation
- Subscription lifecycle (create, upgrade, cancel)
- SOL price cascade fallback (Jupiter → CoinGecko → DexScreener)
- Duplicate payment handling
- Dynamic SOL pricing with 10% discount

### 4. Authentication (`middleware/auth.py`, `api/auth.py` — 104+ lines)
JWT handling and tier-based access control. No tests.

**Suggested tests:**
- Valid / expired / malformed token handling
- Tier-gated endpoint enforcement
- Case-insensitive email matching
- Token refresh flow

### 5. Prediction Settlement (untested parts of `prediction_engine.py`)
Settlement logic, player props, weighted consensus. Partially tested (only `score_pick()`).

**Suggested tests:**
- `settle_predictions()` with mock Odds API scores
- `_analyze_player_props()` for each sport
- `weighted_consensus_prob()` with sharp/soft book weighting
- Player prop settlement: DNP scenarios, stat mapping
- Under/No pick generation for props

## Priority 2 — High

### 6. Background Workers (5 files, all untested)
- `callout_worker.py` — peak market cap tracking, repin logic
- `scan_worker.py` / `print_scan_worker.py` — token discovery
- `prediction_worker.py` — settlement scheduling
- `copy_trade_worker.py` — trade execution loop

**Suggested tests:** Job idempotency, error recovery, dedup (one callout per token), repin cooldown.

### 7. External API Clients (8 services, all untested)
`birdeye.py`, `dexscreener.py`, `helius.py`, `rugcheck.py`, `odds_provider.py`, `espn_scores.py`, `social_signals.py`, `onchain_analyzer.py`

**Suggested tests:** Response parsing with fixture JSON, error/timeout handling, fallback chains.

### 8. Frontend Utilities (`lib/utils.ts`, `lib/api.ts`)
Pure formatting functions and JWT refresh logic.

**Suggested tests:** `formatCurrency`, `formatAddress`, `formatPercent` edge cases; token expiry and refresh; error propagation.

## Priority 3 — Medium

### 9. Pydantic Schemas (6 files)
Request/response validation. Test malformed inputs, enum enforcement, required fields.

### 10. Database Models (12 files)
Relationship integrity, unique constraints, migration correctness.

### 11. Frontend Components (complex)
`token-table.tsx`, `prediction-card.tsx`, `play-by-play-feed.tsx`, `callout-card.tsx` — conditional rendering, sport-specific displays, tier gating.

## Recommended Test Dependencies

### Backend (`requirements.txt`)
```
pytest>=7.0
pytest-asyncio>=0.21
pytest-cov>=4.0
httpx>=0.24
aioresponses>=0.7
```

### Frontend
```bash
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

## Suggested First Test Files

| File | Covers |
|------|--------|
| `backend/tests/test_callout_engine.py` | 12-factor scoring, thresholds, quality gates |
| `backend/tests/test_prediction_settlement.py` | Settlement, prop settlement, score parsing |
| `backend/tests/test_auth.py` | JWT creation/validation, middleware, tier checks |
| `backend/tests/test_payments.py` | Stripe webhooks, SOL verification, pricing |
| `backend/tests/test_copy_trade.py` | Trade building, slippage, error handling |
| `backend/tests/test_api_clients.py` | External API response parsing with fixtures |
| `frontend/__tests__/utils.test.ts` | formatCurrency, formatAddress, formatPercent |
| `frontend/__tests__/api.test.ts` | JWT refresh, error handling |
