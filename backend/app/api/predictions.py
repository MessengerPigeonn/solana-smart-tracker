from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, Tier
from app.models.prediction import Prediction
from app.schemas.prediction import PredictionResponse, PredictionListResponse, PredictionStatsResponse
from app.middleware.auth import require_tier

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("", response_model=PredictionListResponse)
async def list_predictions(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sport: Optional[str] = Query(None),
    bet_type: Optional[str] = Query(None, pattern="^(moneyline|spread|total|player_prop|parlay)$"),
    result: Optional[str] = Query(None, pattern="^(win|loss|push|pending)$"),
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    query = select(Prediction)
    count_query = select(func.count()).select_from(Prediction)

    if sport:
        query = query.where(Prediction.sport == sport)
        count_query = count_query.where(Prediction.sport == sport)
    if bet_type:
        query = query.where(Prediction.bet_type == bet_type)
        count_query = count_query.where(Prediction.bet_type == bet_type)
    if result:
        query = query.where(Prediction.result == result)
        count_query = count_query.where(Prediction.result == result)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    rows = await db.execute(
        query.order_by(Prediction.commence_time.asc()).offset(offset).limit(limit)
    )
    predictions = rows.scalars().all()

    return PredictionListResponse(
        predictions=[PredictionResponse.model_validate(p) for p in predictions],
        total=total,
    )


@router.get("/stats", response_model=PredictionStatsResponse)
async def prediction_stats(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated prediction stats — win rate, ROI, streak, sport breakdown."""
    result = await db.execute(
        select(Prediction).order_by(Prediction.created_at.desc()).limit(500)
    )
    predictions = result.scalars().all()
    total_predictions = len(predictions)

    if total_predictions == 0:
        return PredictionStatsResponse(total_predictions=0)

    settled = [p for p in predictions if p.result in ("win", "loss", "push")]
    wins = sum(1 for p in settled if p.result == "win")
    win_rate = round(wins / len(settled) * 100, 1) if settled else None

    settled_with_pnl = [p for p in settled if p.pnl_units is not None]
    total_wagered = len(settled_with_pnl)
    total_pnl = sum(p.pnl_units for p in settled_with_pnl)
    roi_pct = round(total_pnl / total_wagered * 100, 2) if total_wagered > 0 else None

    current_streak = 0
    streak_type = None
    for p in sorted(settled, key=lambda x: x.created_at, reverse=True):
        if p.result == "push":
            continue
        if streak_type is None:
            streak_type = p.result
            current_streak = 1
        elif p.result == streak_type:
            current_streak += 1
        else:
            break
    if streak_type == "loss":
        current_streak = -current_streak

    sport_breakdown = {}
    for p in settled:
        s = p.sport
        if s not in sport_breakdown:
            sport_breakdown[s] = {"total": 0, "wins": 0, "losses": 0, "pushes": 0, "pnl_units": 0.0}
        sport_breakdown[s]["total"] += 1
        if p.result == "win":
            sport_breakdown[s]["wins"] += 1
        elif p.result == "loss":
            sport_breakdown[s]["losses"] += 1
        else:
            sport_breakdown[s]["pushes"] += 1
        if p.pnl_units is not None:
            sport_breakdown[s]["pnl_units"] += p.pnl_units

    for sport_data in sport_breakdown.values():
        non_push = sport_data["wins"] + sport_data["losses"]
        sport_data["win_rate"] = round(sport_data["wins"] / non_push * 100, 1) if non_push > 0 else 0.0

    best_sport = None
    best_roi = -999.0
    for s, data in sport_breakdown.items():
        if data["total"] >= 5 and data["pnl_units"] > best_roi:
            best_roi = data["pnl_units"]
            best_sport = s

    return PredictionStatsResponse(
        total_predictions=total_predictions,
        win_rate=win_rate,
        roi_pct=roi_pct,
        current_streak=current_streak,
        best_sport=best_sport,
        sport_breakdown=sport_breakdown,
    )


@router.get("/live", response_model=PredictionListResponse)
async def live_predictions(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    """Pending predictions for today's games."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    query = (
        select(Prediction)
        .where(
            Prediction.result == "pending",
            Prediction.commence_time >= start_of_day,
            Prediction.commence_time < end_of_day,
        )
        .order_by(Prediction.commence_time.asc())
    )

    count_query = (
        select(func.count())
        .select_from(Prediction)
        .where(
            Prediction.result == "pending",
            Prediction.commence_time >= start_of_day,
            Prediction.commence_time < end_of_day,
        )
    )
    total = (await db.execute(count_query)).scalar() or 0
    rows = await db.execute(query)
    predictions = rows.scalars().all()

    return PredictionListResponse(
        predictions=[PredictionResponse.model_validate(p) for p in predictions],
        total=total,
    )
