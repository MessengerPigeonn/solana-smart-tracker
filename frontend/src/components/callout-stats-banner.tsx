"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { TrendingUp, Target, Trophy, BarChart3, Flame } from "lucide-react";
import type { CalloutStats } from "@/lib/types";

export function CalloutStatsBanner() {
  const [stats, setStats] = useState<CalloutStats | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await apiFetch<CalloutStats>("/api/callouts/stats");
        setStats(data);
      } catch {
        // ignore
      }
    }
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  if (!stats || stats.total_calls === 0) return null;

  return (
    <Card className="glass-card border-primary/20 bg-gradient-to-r from-primary/5 to-transparent">
      <CardContent className="py-3 px-4">
        <div className="flex items-center gap-2 mb-2">
          <BarChart3 className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold text-primary">
            Last {stats.total_calls} Calls Performance
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Avg current multiplier */}
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Avg Return</p>
              <p className={`text-sm font-bold ${
                stats.avg_multiplier && stats.avg_multiplier >= 1
                  ? "text-green-500"
                  : "text-red-500"
              }`}>
                {stats.avg_multiplier ? `${stats.avg_multiplier.toFixed(2)}x` : "—"}
              </p>
            </div>
          </div>

          {/* ATH avg multiplier */}
          <div className="flex items-center gap-2">
            <Trophy className="h-4 w-4 text-amber-400" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Avg ATH</p>
              <p className="text-sm font-bold text-amber-400">
                {stats.avg_ath_multiplier ? `${stats.avg_ath_multiplier.toFixed(2)}x` : "—"}
              </p>
            </div>
          </div>

          {/* Win rate */}
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Win Rate</p>
              <p className={`text-sm font-bold ${
                stats.win_rate && stats.win_rate >= 50
                  ? "text-green-500"
                  : "text-muted-foreground"
              }`}>
                {stats.win_rate !== null && stats.win_rate !== undefined
                  ? `${stats.win_rate.toFixed(0)}%`
                  : "—"}
              </p>
            </div>
          </div>

          {/* Best call */}
          <div className="flex items-center gap-2">
            <Trophy className="h-4 w-4 text-green-500" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Best Call</p>
              <p className="text-sm font-bold text-green-500">
                {stats.best_call_symbol && stats.best_call_ath_multiplier
                  ? `${stats.best_call_symbol} ${stats.best_call_ath_multiplier.toFixed(1)}x`
                  : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Milestone counts */}
        {stats.milestones && (
          <div className="mt-3 pt-3 border-t border-border/30">
            <div className="flex items-center gap-2 mb-2">
              <Flame className="h-3.5 w-3.5 text-amber-400" />
              <span className="text-xs font-semibold text-muted-foreground uppercase">
                Milestone Hits
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {([
                { label: "+20%", value: stats.milestones.pct_20, color: "text-green-400 border-green-500/20 bg-green-500/5" },
                { label: "+40%", value: stats.milestones.pct_40, color: "text-green-400 border-green-500/20 bg-green-500/5" },
                { label: "+60%", value: stats.milestones.pct_60, color: "text-green-500 border-green-500/20 bg-green-500/5" },
                { label: "+80%", value: stats.milestones.pct_80, color: "text-green-500 border-green-500/20 bg-green-500/5" },
                { label: "2x", value: stats.milestones.x2, color: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5" },
                { label: "5x", value: stats.milestones.x5, color: "text-amber-400 border-amber-500/20 bg-amber-500/5" },
                { label: "10x", value: stats.milestones.x10, color: "text-amber-500 border-amber-500/20 bg-amber-500/5" },
                { label: "50x", value: stats.milestones.x50, color: "text-orange-500 border-orange-500/20 bg-orange-500/5" },
                { label: "100x", value: stats.milestones.x100, color: "text-red-500 border-red-500/20 bg-red-500/5" },
              ] as const).map((m) => (
                <div
                  key={m.label}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium ${m.color}`}
                >
                  <span className="opacity-70">{m.label}</span>
                  <span className="font-bold">{m.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
