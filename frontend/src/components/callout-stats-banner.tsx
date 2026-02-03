"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { TrendingUp, Target, Trophy, BarChart3 } from "lucide-react";
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
      </CardContent>
    </Card>
  );
}
