"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Zap, Loader2, AlertCircle } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { PlayByPlayData, PlayByPlayEntry } from "@/lib/types";

interface PlayByPlayFeedProps {
  predictionId: number;
  sport: string;
  isLive: boolean;
}

function groupByPeriod(plays: PlayByPlayEntry[]): Map<string, PlayByPlayEntry[]> {
  const groups = new Map<string, PlayByPlayEntry[]>();
  for (const play of plays) {
    const key = play.period || `Period ${play.period_number}`;
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(play);
  }
  return groups;
}

function SportExtras({ play, sport }: { play: PlayByPlayEntry; sport: string }) {
  const extras = play.extras;
  if (!extras || Object.keys(extras).length === 0) return null;

  const badges: string[] = [];

  if (sport === "NFL") {
    if (extras.down && extras.distance) {
      const ordinal = { 1: "1st", 2: "2nd", 3: "3rd", 4: "4th" }[extras.down as number] || `${extras.down}th`;
      badges.push(`${ordinal} & ${extras.distance}`);
    }
    if (extras.yards !== undefined) {
      const yds = extras.yards as number;
      badges.push(`${yds > 0 ? "+" : ""}${yds} yds`);
    }
  } else if (sport === "MLB") {
    if (extras.outs !== undefined) {
      badges.push(`${extras.outs} out${extras.outs !== 1 ? "s" : ""}`);
    }
    if (extras.pitchCount !== undefined) {
      badges.push(`${extras.pitchCount} pitches`);
    }
  } else if (sport === "NHL") {
    if (extras.strength) {
      badges.push(extras.strength as string);
    }
  }

  if (badges.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 mt-0.5">
      {badges.map((badge, i) => (
        <span
          key={i}
          className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-muted/60 text-muted-foreground border border-border/30"
        >
          {badge}
        </span>
      ))}
    </div>
  );
}

export function PlayByPlayFeed({ predictionId, sport, isLive }: PlayByPlayFeedProps) {
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState<PlayByPlayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchPlays = useCallback(async () => {
    try {
      setError(null);
      const result = await apiFetch<PlayByPlayData>(
        `/api/predictions/${predictionId}/plays`,
        { requireAuth: true }
      );
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plays");
    } finally {
      setLoading(false);
    }
  }, [predictionId]);

  useEffect(() => {
    if (!expanded) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    setLoading(true);
    fetchPlays();

    if (isLive) {
      intervalRef.current = setInterval(fetchPlays, 30000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [expanded, isLive, fetchPlays]);

  const grouped = data ? groupByPeriod(data.plays) : new Map();

  return (
    <div className="mb-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors py-1"
      >
        <Zap className="h-3 w-3" />
        Play-by-Play
        {expanded ? " \u25B4" : " \u25BE"}
      </button>

      {expanded && (
        <div className="mt-1 rounded-lg border border-border/40 bg-muted/20 overflow-hidden">
          {loading && !data && (
            <div className="flex items-center justify-center py-6 gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading plays...
            </div>
          )}

          {error && !data && (
            <div className="flex items-center justify-center py-6 gap-2 text-xs text-red-400">
              <AlertCircle className="h-3.5 w-3.5" />
              {error}
            </div>
          )}

          {data && data.plays.length === 0 && (
            <div className="flex items-center justify-center py-6 text-xs text-muted-foreground">
              No plays available yet
            </div>
          )}

          {data && data.plays.length > 0 && (
            <div className="play-feed-scroll max-h-[300px] overflow-y-auto">
              {Array.from(grouped.entries()).map(([period, plays]: [string, PlayByPlayEntry[]]) => (
                <div key={period}>
                  <div className="sticky top-0 z-10 bg-muted/80 backdrop-blur-sm px-3 py-1 border-b border-border/30">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {period}
                    </span>
                  </div>
                  <div className="divide-y divide-border/20">
                    {plays.map((play) => (
                      <div
                        key={play.id}
                        className={`flex items-start gap-2 px-3 py-1.5 text-xs ${
                          play.scoring_play
                            ? "border-l-2 border-l-amber-500 bg-amber-500/5"
                            : "border-l-2 border-l-transparent"
                        }`}
                      >
                        {/* Clock */}
                        <span className="font-mono text-[11px] text-muted-foreground w-12 shrink-0 pt-0.5">
                          {play.clock || ""}
                        </span>

                        {/* Description */}
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs leading-snug ${play.scoring_play ? "text-amber-300" : "text-foreground/90"}`}>
                            {play.text}
                          </p>
                          <SportExtras play={play} sport={sport} />
                        </div>

                        {/* Scoring badge */}
                        {play.scoring_play && play.score_value > 0 && (
                          <span className="shrink-0 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                            +{play.score_value}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
