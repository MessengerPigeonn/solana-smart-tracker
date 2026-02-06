"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { PredictionStats } from "@/lib/types";

interface PredictionStatsBannerProps {
  stats: PredictionStats | null;
}

export function PredictionStatsBanner({ stats }: PredictionStatsBannerProps) {
  if (!stats || stats.total_predictions === 0) {
    return (
      <Card className="glass-card">
        <CardContent className="py-4">
          <p className="text-sm text-muted-foreground text-center">
            No predictions yet. The engine will generate picks when games are available.
          </p>
        </CardContent>
      </Card>
    );
  }

  const streakText =
    stats.current_streak > 0
      ? `${stats.current_streak}W`
      : stats.current_streak < 0
        ? `${Math.abs(stats.current_streak)}L`
        : "0";
  const streakColor =
    stats.current_streak > 0
      ? "text-green-400"
      : stats.current_streak < 0
        ? "text-red-400"
        : "text-muted-foreground";

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <Card className="glass-card">
        <CardContent className="py-3 px-4 text-center">
          <p className="text-xs text-muted-foreground">Total Picks</p>
          <p className="text-2xl font-bold">{stats.total_predictions}</p>
        </CardContent>
      </Card>

      <Card className="glass-card">
        <CardContent className="py-3 px-4 text-center">
          <p className="text-xs text-muted-foreground">Win Rate</p>
          <p className="text-2xl font-bold text-green-400">
            {stats.win_rate !== null ? `${stats.win_rate}%` : "--"}
          </p>
        </CardContent>
      </Card>

      <Card className="glass-card">
        <CardContent className="py-3 px-4 text-center">
          <p className="text-xs text-muted-foreground">ROI</p>
          <p className={`text-2xl font-bold ${stats.roi_pct !== null && stats.roi_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
            {stats.roi_pct !== null ? `${stats.roi_pct > 0 ? "+" : ""}${stats.roi_pct}%` : "--"}
          </p>
        </CardContent>
      </Card>

      <Card className="glass-card">
        <CardContent className="py-3 px-4 text-center">
          <p className="text-xs text-muted-foreground">Streak</p>
          <p className={`text-2xl font-bold ${streakColor}`}>{streakText}</p>
        </CardContent>
      </Card>

      <Card className="glass-card">
        <CardContent className="py-3 px-4 text-center">
          <p className="text-xs text-muted-foreground">Best Sport</p>
          <p className="text-2xl font-bold">{stats.best_sport || "--"}</p>
        </CardContent>
      </Card>
    </div>
  );
}
