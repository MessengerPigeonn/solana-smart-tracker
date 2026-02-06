"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ChevronDown, ChevronUp, Clock } from "lucide-react";
import type { Prediction } from "@/lib/types";

const SPORT_COLORS: Record<string, string> = {
  NBA: "bg-orange-500/10 text-orange-400 border-orange-500/30",
  NFL: "bg-green-500/10 text-green-400 border-green-500/30",
  MLB: "bg-red-500/10 text-red-400 border-red-500/30",
  NHL: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  UFC: "bg-red-500/10 text-red-400 border-red-500/30",
  Soccer: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  Multi: "bg-purple-500/10 text-purple-400 border-purple-500/30",
};

const BET_TYPE_LABELS: Record<string, string> = {
  moneyline: "ML",
  spread: "Spread",
  total: "Total",
  player_prop: "Prop",
  parlay: "Parlay",
};

function formatOdds(odds: number): string {
  return odds >= 0 ? `+${Math.round(odds)}` : `${Math.round(odds)}`;
}

function formatGameTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();

  // If game is in the past, show the date
  if (diffMs < 0) {
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  // Show countdown for upcoming games
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `in ${diffMin}m`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `in ${diffHrs}h ${diffMin % 60}m`;
  const diffDays = Math.floor(diffHrs / 24);
  return `in ${diffDays}d ${diffHrs % 24}h`;
}

function formatFullDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function isUpcoming(dateStr: string): boolean {
  return new Date(dateStr).getTime() > Date.now();
}

interface PredictionCardProps {
  prediction: Prediction;
}

export function PredictionCard({ prediction }: PredictionCardProps) {
  const [expanded, setExpanded] = useState(false);

  const sportColor = SPORT_COLORS[prediction.sport] || "bg-gray-500/10 text-gray-400 border-gray-500/30";
  const confidenceWidth = Math.min(Math.max(prediction.confidence, 0), 100);
  const confidenceBarClass =
    prediction.confidence >= 75
      ? "bg-gradient-to-r from-teal-500 to-green-500"
      : prediction.confidence >= 55
        ? "bg-gradient-to-r from-yellow-500 to-amber-500"
        : "bg-gradient-to-r from-red-500 to-red-400";

  const upcoming = isUpcoming(prediction.commence_time);
  const isPending = prediction.result === "pending" || !prediction.result;

  const resultVariant =
    prediction.result === "win"
      ? ("teal" as const)
      : prediction.result === "loss"
        ? ("destructive" as const)
        : prediction.result === "push"
          ? ("secondary" as const)
          : ("outline" as const);

  return (
    <Card className={`glass-card card-hover ${upcoming && isPending ? "border-primary/20" : ""}`}>
      <CardContent className="pt-4 pb-3">
        {/* Row 1: Sport + Bet Type + Game Time */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <div className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${sportColor}`}>
              {prediction.sport}
            </div>
            <Badge variant="secondary" className="text-[11px]">{BET_TYPE_LABELS[prediction.bet_type] || prediction.bet_type}</Badge>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span className={upcoming && isPending ? "text-primary font-medium" : ""}>
              {formatGameTime(prediction.commence_time)}
            </span>
          </div>
        </div>

        {/* Row 2: Matchup */}
        <div className="mb-2">
          <p className="text-sm font-medium">{prediction.away_team} @ {prediction.home_team}</p>
          <p className="text-[11px] text-muted-foreground">
            {formatFullDate(prediction.commence_time)}
            {prediction.league && ` \u2022 ${prediction.league}`}
          </p>
        </div>

        {/* Row 3: Pick + Odds (prominent) */}
        <div className="flex items-center justify-between mb-3 p-2 rounded-lg bg-muted/40 border border-border/20">
          <div>
            <p className="text-sm font-bold">{prediction.pick}</p>
            <span className="text-[10px] text-muted-foreground">{prediction.best_bookmaker}</span>
          </div>
          <div className="text-right">
            <p className={`text-lg font-bold font-mono ${prediction.best_odds > 0 ? "text-green-400" : "text-foreground"}`}>
              {formatOdds(prediction.best_odds)}
            </p>
          </div>
        </div>

        {/* Row 4: Confidence + Edge side by side */}
        <div className="grid grid-cols-2 gap-3 mb-2">
          <div>
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-muted-foreground">Confidence</span>
              <span className="font-semibold">{prediction.confidence}%</span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${confidenceBarClass}`}
                style={{ width: `${confidenceWidth}%` }}
              />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-muted-foreground">Edge</span>
              <span className={`font-semibold ${prediction.edge > 0 ? "text-green-400" : "text-red-400"}`}>
                {prediction.edge > 0 ? "+" : ""}{(prediction.edge * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                style={{ width: `${Math.min(prediction.edge * 100 * 5, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Implied probability */}
        <p className="text-[11px] text-muted-foreground mb-2">
          Implied: {(prediction.implied_probability * 100).toFixed(1)}%
        </p>

        {/* Result + PnL row */}
        {prediction.result && prediction.result !== "pending" && (
          <div className="flex items-center gap-3 mb-2">
            <Badge variant={resultVariant}>{prediction.result.toUpperCase()}</Badge>
            {prediction.pnl_units !== null && (
              <span className={`text-sm font-medium ${prediction.pnl_units >= 0 ? "text-green-400" : "text-red-400"}`}>
                {prediction.pnl_units >= 0 ? "+" : ""}{prediction.pnl_units.toFixed(2)}u
              </span>
            )}
            {prediction.actual_score && (
              <span className="text-xs text-muted-foreground">Final: {prediction.actual_score}</span>
            )}
          </div>
        )}

        {/* Parlay legs */}
        {prediction.bet_type === "parlay" && prediction.parlay_legs && prediction.parlay_legs.length > 0 && (
          <div className="mb-2 rounded-lg border border-border/30 bg-muted/30 p-2.5">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
              Parlay Legs ({prediction.parlay_legs.length})
            </p>
            <div className="space-y-1">
              {prediction.parlay_legs.map((leg, idx) => (
                <div key={idx} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted-foreground">{leg.sport}</span>
                    <span className="font-medium">{leg.pick}</span>
                  </div>
                  <span className="font-mono text-muted-foreground">{formatOdds(leg.odds)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Reasoning (expandable) */}
        <div className="pt-2 border-t border-border/30">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            AI Reasoning
          </button>
          {expanded && (
            <p className="text-sm text-muted-foreground mt-2">{prediction.reasoning}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
