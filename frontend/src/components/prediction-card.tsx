"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ChevronDown, ChevronUp } from "lucide-react";
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

function formatCommenceTime(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function getTimeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
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

  const resultVariant =
    prediction.result === "win"
      ? ("teal" as const)
      : prediction.result === "loss"
        ? ("destructive" as const)
        : prediction.result === "push"
          ? ("secondary" as const)
          : ("outline" as const);

  return (
    <Card className="glass-card card-hover">
      <CardContent className="pt-4">
        {/* Header: sport badge + bet type badge + confidence + time */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className={`inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold ${sportColor}`}>
              {prediction.sport}
            </div>
            <Badge variant="secondary">{BET_TYPE_LABELS[prediction.bet_type] || prediction.bet_type}</Badge>
            <span className="text-xs font-medium text-muted-foreground">{prediction.confidence}% conf</span>
          </div>
          <span className="text-xs text-muted-foreground">{getTimeAgo(prediction.created_at)}</span>
        </div>

        {/* Teams row */}
        <div className="mb-2">
          <p className="text-sm font-medium">{prediction.away_team} @ {prediction.home_team}</p>
          <p className="text-xs text-muted-foreground">
            {formatCommenceTime(prediction.commence_time)}
            {prediction.league && ` \u2022 ${prediction.league}`}
          </p>
        </div>

        {/* Pick row */}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-bold">{prediction.pick} {formatOdds(prediction.best_odds)}</span>
          <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded bg-muted">{prediction.best_bookmaker}</span>
        </div>

        {/* Confidence bar */}
        <div className="mb-2">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-muted-foreground">Confidence</span>
            <span className="font-medium">{prediction.confidence}/100</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${confidenceBarClass}`}
              style={{ width: `${confidenceWidth}%` }}
            />
          </div>
        </div>

        {/* Edge display */}
        <div className="flex items-center gap-4 mb-2 text-sm">
          <span className={prediction.edge >= 0 ? "text-green-400 font-medium" : "text-red-400 font-medium"}>
            Edge: {prediction.edge >= 0 ? "+" : ""}{(prediction.edge * 100).toFixed(1)}%
          </span>
          <span className="text-muted-foreground text-xs">
            Implied: {(prediction.implied_probability * 100).toFixed(1)}%
          </span>
        </div>

        {/* Result + PnL row */}
        {prediction.result && prediction.result !== "pending" && (
          <div className="flex items-center gap-3 mb-2">
            <Badge variant={resultVariant}>{prediction.result.toUpperCase()}</Badge>
            {prediction.pnl_units !== null && (
              <span className={`text-sm font-medium ${prediction.pnl_units >= 0 ? "text-green-400" : "text-red-400"}`}>
                {prediction.pnl_units >= 0 ? "+" : ""}{prediction.pnl_units.toFixed(2)} units
              </span>
            )}
            {prediction.actual_score && (
              <span className="text-xs text-muted-foreground">Final: {prediction.actual_score}</span>
            )}
          </div>
        )}

        {/* Parlay legs */}
        {prediction.bet_type === "parlay" && prediction.parlay_legs && prediction.parlay_legs.length > 0 && (
          <div className="mb-2 rounded-lg border border-border/30 bg-muted/30 p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Parlay Legs ({prediction.parlay_legs.length})
            </p>
            <div className="space-y-1.5">
              {prediction.parlay_legs.map((leg, idx) => (
                <div key={idx} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
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
        <div className="mt-2 pt-2 border-t border-border/30">
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
