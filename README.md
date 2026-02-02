# Solana Smart Tracker

Real-time Solana memecoin scanner with smart money tracking, automated callouts, and **PrintScan** micro-cap token discovery.

## Features

### Token Scanner
- Multi-source discovery via Birdeye trending + volume endpoints
- Real-time price changes (5m, 1h, 24h), volume, liquidity, market cap
- Token classification (memecoin, defi, stablecoin)
- Buy/sell ratio analysis and whale accumulation detection
- Top trader snapshots with PnL tracking
- Auto-refresh every 15 seconds

### PrintScan (Micro-Cap Discovery)
- Catches newly listed tokens ($1K-$500K market cap) within minutes of launch
- Security analysis: mint authority, freeze authority, metadata mutability
- Holder distribution: top 10 holder concentration, dev wallet tracking
- Rug risk scoring (0-100) based on security flags and holder data
- 15-second polling cycle with dedicated background worker
- Auto-cleanup of stale tokens after 24 hours

### Callout Engine
- Smart money scoring (0-100) for trending tokens: whale accumulation, buy/sell ratio, volume momentum, smart money PnL, freshness, liquidity
- Security-weighted scoring for micro-caps: security safety, holder distribution, freshness, buy pressure, volume/mcap ratio, liquidity floor
- Auto-reject: tokens with active mint authority + >30% dev wallet capped at score 20
- Three signal types: BUY (65+), WATCH (45+), SELL (reversal detection)
- Real-time SSE streaming for Pro/Legend tier users

### Dashboard
- Live signal counts (BUY, WATCH, SELL, PrintScan Alerts)
- Top movers and smart money token rankings
- Recent callouts with price performance tracking
- Scanner health monitoring

### User Tiers
- **Free**: 10 tokens, 5 callouts with 5-min delay
- **Pro**: Full access, real-time SSE feed
- **Legend**: All features, priority data

## Tech Stack

### Backend
- **FastAPI** with async SQLAlchemy (SQLite dev / PostgreSQL prod)
- **Birdeye API** for token data, security info, holder data, new listings
- **Three background workers**: scan_worker (30s), callout_worker (30s), print_scan_worker (15s)
- JWT authentication with refresh tokens
- SSE streaming for real-time callouts
- Stripe + SOL payment integration

### Frontend
- **Next.js 14** with App Router
- **Tailwind CSS** + shadcn/ui components
- Token table with sortable columns, expandable rows, PRINT badges, risk indicators
- Scanner page with filter tabs (All, Trending, New, Smart Money, PrintScan)
- Callout feed with confidence bars and price delta tracking

## Project Structure

```
solana-smart-tracker/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py                 # FastAPI app + worker startup
│       ├── config.py               # Settings (env vars)
│       ├── database.py             # Async SQLAlchemy setup
│       ├── models/
│       │   ├── token.py            # ScannedToken (price, security, holders)
│       │   ├── callout.py          # Callout signals
│       │   ├── user.py             # User accounts + tiers
│       │   ├── trader_snapshot.py  # Top trader data
│       │   ├── tracked_wallet.py   # Wallet tracking
│       │   └── payment.py          # Payment records
│       ├── schemas/                # Pydantic request/response models
│       ├── services/
│       │   ├── birdeye.py          # Birdeye API client (10 endpoints)
│       │   ├── scanner.py          # Trending token discovery + enrichment
│       │   ├── print_scanner.py    # Micro-cap discovery + security analysis
│       │   ├── callout_engine.py   # Scoring + signal generation
│       │   ├── analyzer.py         # Token analysis utilities
│       │   ├── helius.py           # Helius API client
│       │   └── wallet_analytics.py # Wallet analysis
│       ├── workers/
│       │   ├── scan_worker.py      # Trending scanner (30s cycle)
│       │   ├── callout_worker.py   # Callout generation (30s cycle)
│       │   └── print_scan_worker.py # PrintScan (15s cycle)
│       ├── api/                    # REST endpoints
│       └── middleware/             # JWT auth middleware
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app/
        │   ├── dashboard/
        │   │   ├── page.tsx        # Dashboard overview
        │   │   ├── scanner/        # Token scanner + PrintScan tab
        │   │   ├── callouts/       # Callout feed
        │   │   ├── wallets/        # Wallet tracking
        │   │   └── smart-money/    # Smart money analysis
        │   ├── login/
        │   ├── signup/
        │   └── pricing/
        ├── components/
        │   ├── token-table.tsx     # Token table with risk column
        │   ├── callout-card.tsx    # Signal cards with PRINT badges
        │   ├── callout-feed.tsx    # Live callout feed + SSE
        │   └── ui/                 # shadcn/ui components
        └── lib/
            ├── api.ts              # API client with token refresh
            ├── auth.ts             # Auth utilities
            └── utils.ts            # Formatting helpers
```

## Getting Started

### Prerequisites
- Python 3.9+
- Node.js 18+
- Birdeye API key ([birdeye.so](https://birdeye.so))

### Local Development

1. **Clone the repo**
   ```bash
   git clone https://github.com/MessengerPigeonn/solana-smart-tracker.git
   cd solana-smart-tracker
   ```

2. **Backend setup**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env and add your BIRDEYE_API_KEY
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Frontend setup** (in a new terminal)
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Create an admin user**
   ```bash
   # From project root
   python3 create_admin.py admin@example.com yourpassword
   ```

5. Open http://localhost:3000

### Docker Deployment

```bash
cp .env.example .env
# Edit .env with your API keys

docker compose up --build
```

This starts PostgreSQL, the backend (port 8000), and frontend (port 3000).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login, get tokens |
| GET | `/api/tokens` | List scanned tokens (filterable) |
| GET | `/api/tokens?scan_source=print_scan` | PrintScan micro-cap tokens |
| GET | `/api/tokens/{address}` | Token detail + top traders |
| GET | `/api/tokens/search?q=` | Search by ticker/address |
| GET | `/api/callouts` | List callout signals |
| GET | `/api/callouts/stream` | SSE real-time feed (Pro+) |
| GET | `/api/health` | Health check |

### Token Filters
- `sort_by`: volume_24h, market_cap, price_change_24h, smart_money_count, rug_risk_score, last_scanned, etc.
- `token_type`: memecoin, defi, stablecoin, unknown
- `scan_source`: trending, print_scan
- `mcap_min` / `mcap_max`: market cap range

## PrintScan Scoring

| Factor | Points | Description |
|--------|--------|-------------|
| Security Safety | 25 | Start at max, deduct for mint/freeze/mutable |
| Holder Distribution | 20 | Ideal: top 10 hold 30-60%, bonus if dev sold |
| Freshness | 20 | <10min = full, <30min = 85%, <60min = 60% |
| Buy/Sell Ratio | 15 | Buy pressure percentage |
| Volume Momentum | 10 | Volume/mcap ratio + price momentum |
| Liquidity Floor | 10 | Scales to $20K |

**Auto-reject**: Mint authority active + dev wallet >30% = score capped at 20, flagged "HIGH RUG RISK"

## Rug Risk Score

| Flag | Points |
|------|--------|
| Mint authority active | +30 |
| Freeze authority active | +20 |
| Top 10 holders > 80% | +15 |
| Holder count < 10 | +15 |
| Dev holds > 20% | +10 |
| Metadata mutable | +10 |

Risk indicator: Green (<25), Yellow (25-50), Red (>50)

## License

MIT
