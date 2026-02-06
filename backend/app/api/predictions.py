from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, Tier
from app.models.prediction import Prediction
from app.schemas.prediction import (
    PredictionResponse,
    PredictionListResponse,
    PredictionStatsResponse,
    LiveScoreData,
    LiveScoresResponse,
    PlayByPlayEntryResponse,
    PlayByPlayResponse,
)
from app.middleware.auth import require_tier
from app.services.espn_scores import espn_provider

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


@router.get("/live-scores", response_model=LiveScoresResponse)
async def live_scores(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    """Live scores for in-progress predictions."""
    now = datetime.now(timezone.utc)

    # Fetch pending predictions where the game has started
    query = (
        select(Prediction)
        .where(
            Prediction.result == "pending",
            Prediction.commence_time <= now,
        )
    )
    rows = await db.execute(query)
    predictions = rows.scalars().all()

    if not predictions:
        return LiveScoresResponse(scores={})

    # Group predictions by sport
    by_sport: dict[str, list] = {}
    for p in predictions:
        by_sport.setdefault(p.sport, []).append(p)

    # Fetch live scores for each sport with pending predictions
    scores: dict[int, LiveScoreData] = {}
    for sport, preds in by_sport.items():
        live_games = await espn_provider.get_live_scores(sport)

        for pred in preds:
            # Try to match this prediction to a live game
            matched = _match_prediction_to_game(pred, live_games)
            if not matched:
                continue

            bet_status = _compute_bet_status(pred, matched)
            score_display = f"{matched.away_team} {matched.away_score} - {matched.home_team} {matched.home_score}"

            scores[pred.id] = LiveScoreData(
                prediction_id=pred.id,
                home_score=matched.home_score,
                away_score=matched.away_score,
                clock=matched.clock,
                period=matched.period,
                status=matched.status,
                bet_status=bet_status,
                score_display=score_display,
                espn_event_id=matched.event_id,
            )

    return LiveScoresResponse(scores=scores)


@router.get("/{prediction_id}/plays", response_model=PlayByPlayResponse)
async def get_plays(
    prediction_id: int,
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    """Play-by-play feed for a prediction's game."""
    result = await db.execute(
        select(Prediction).where(Prediction.id == prediction_id)
    )
    pred = result.scalar_one_or_none()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")

    # Find matching live game to get event_id
    live_games = await espn_provider.get_live_scores(pred.sport)
    matched = _match_prediction_to_game(pred, live_games)
    if not matched or not matched.event_id:
        raise HTTPException(status_code=404, detail="No live game found for this prediction")

    if matched.status not in ("in_progress", "halftime", "final"):
        raise HTTPException(status_code=404, detail="Game has not started yet")

    plays, total_plays = await espn_provider.get_play_by_play(
        event_id=matched.event_id,
        sport=pred.sport,
        home_team=matched.home_team,
        away_team=matched.away_team,
    )

    return PlayByPlayResponse(
        event_id=matched.event_id,
        sport=pred.sport,
        total_plays=total_plays,
        plays=[
            PlayByPlayEntryResponse(
                id=p.id,
                sequence_number=p.sequence_number,
                text=p.text,
                short_text=p.short_text,
                clock=p.clock,
                period=p.period,
                period_number=p.period_number,
                home_score=p.home_score,
                away_score=p.away_score,
                scoring_play=p.scoring_play,
                score_value=p.score_value,
                play_type=p.play_type,
                team_id=p.team_id,
                wallclock=p.wallclock,
                extras=p.extras,
            )
            for p in plays
        ],
        home_team=matched.home_team,
        away_team=matched.away_team,
        home_score=matched.home_score,
        away_score=matched.away_score,
    )


def _match_prediction_to_game(pred, live_games) -> "LiveGameScore | None":
    """Match a prediction to a live ESPN game using team names."""
    from app.services.espn_scores import LiveGameScore

    for game in live_games:
        home_match = (
            espn_provider.match_team(game.home_team, pred.home_team)
            or espn_provider.match_team(game.home_team, pred.away_team)
        )
        away_match = (
            espn_provider.match_team(game.away_team, pred.away_team)
            or espn_provider.match_team(game.away_team, pred.home_team)
        )
        if home_match and away_match:
            return game
    return None


def _compute_bet_status(pred, game) -> str:
    """Compute whether the bet is currently winning, losing, or push."""
    if game.status == "scheduled":
        return "unknown"

    bet_type = pred.bet_type
    pick_text = pred.pick
    pick_detail = pred.pick_detail or {}

    if bet_type == "moneyline":
        # Determine which team was picked
        picked_is_home = espn_provider.match_team(game.home_team, pick_text.replace(" ML", ""))
        picked_is_away = espn_provider.match_team(game.away_team, pick_text.replace(" ML", ""))

        if picked_is_home:
            if game.home_score > game.away_score:
                return "winning"
            elif game.home_score < game.away_score:
                return "losing"
            return "push"
        elif picked_is_away:
            if game.away_score > game.home_score:
                return "winning"
            elif game.away_score < game.home_score:
                return "losing"
            return "push"
        return "unknown"

    elif bet_type == "spread":
        # Pick format: "Team Name +/-X.X"
        parts = pick_text.rsplit(" ", 1)
        if len(parts) != 2:
            return "unknown"
        team_name = parts[0].strip()
        spread_line = pick_detail.get("line")
        if spread_line is None:
            try:
                spread_line = float(parts[1])
            except ValueError:
                return "unknown"

        picked_is_home = espn_provider.match_team(game.home_team, team_name)
        if picked_is_home:
            adjusted = game.home_score + spread_line
            if adjusted > game.away_score:
                return "winning"
            elif adjusted < game.away_score:
                return "losing"
            return "push"
        else:
            adjusted = game.away_score + spread_line
            if adjusted > game.home_score:
                return "winning"
            elif adjusted < game.home_score:
                return "losing"
            return "push"

    elif bet_type == "total":
        total_line = pick_detail.get("line")
        if total_line is None:
            return "unknown"
        actual_total = game.home_score + game.away_score
        is_over = "Over" in pick_text

        if is_over:
            if actual_total > total_line:
                return "winning"
            elif actual_total < total_line:
                return "losing"
            return "push"
        else:
            if actual_total < total_line:
                return "winning"
            elif actual_total > total_line:
                return "losing"
            return "push"

    return "unknown"


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
