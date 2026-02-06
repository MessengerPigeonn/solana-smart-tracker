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

/* ─── Soccer Pitch Mini-Map ─── */

function SoccerPitch({ play, homeTeam, awayTeam }: { play: PlayByPlayEntry; homeTeam: string; awayTeam: string }) {
  const extras = play.extras;
  const fx = (extras?.fieldX as number) || 0;
  const fy = (extras?.fieldY as number) || 0;
  const fx2 = (extras?.fieldX2 as number) || 0;
  const fy2 = (extras?.fieldY2 as number) || 0;

  if (!fx && !fy) return null;

  // Convert ESPN coords (0-1) to SVG coords
  // ESPN: x=0 is left goal line, x=1 is right goal line
  //        y=0 is top touchline, y=1 is bottom touchline
  const pitchW = 200;
  const pitchH = 130;
  const bx = fx * pitchW;
  const by = fy * pitchH;
  const hasDest = (fx2 || fy2) && (fx2 !== fx || fy2 !== fy);
  const bx2 = fx2 * pitchW;
  const by2 = fy2 * pitchH;

  const isGoal = play.scoring_play;
  const eventType = extras?.eventType as string | undefined;

  return (
    <div className="relative w-full mt-1.5 mb-0.5">
      <svg
        viewBox={`-4 -4 ${pitchW + 8} ${pitchH + 8}`}
        className="w-full rounded-md overflow-hidden"
        style={{ maxHeight: 90 }}
      >
        {/* Pitch background */}
        <rect x={0} y={0} width={pitchW} height={pitchH} rx={2} fill="#1a472a" />

        {/* Pitch markings */}
        <g stroke="#2d6b3f" strokeWidth={0.6} fill="none" opacity={0.7}>
          {/* Outline */}
          <rect x={0} y={0} width={pitchW} height={pitchH} rx={1} />
          {/* Center line */}
          <line x1={pitchW / 2} y1={0} x2={pitchW / 2} y2={pitchH} />
          {/* Center circle */}
          <circle cx={pitchW / 2} cy={pitchH / 2} r={16} />
          {/* Center dot */}
          <circle cx={pitchW / 2} cy={pitchH / 2} r={1.2} fill="#2d6b3f" />

          {/* Left penalty area */}
          <rect x={0} y={pitchH / 2 - 30} width={26} height={60} />
          {/* Left goal area */}
          <rect x={0} y={pitchH / 2 - 14} width={10} height={28} />
          {/* Left goal */}
          <rect x={-3} y={pitchH / 2 - 6} width={3} height={12} strokeWidth={1} stroke="#3d8b5a" />
          {/* Left penalty spot */}
          <circle cx={18} cy={pitchH / 2} r={1} fill="#2d6b3f" />

          {/* Right penalty area */}
          <rect x={pitchW - 26} y={pitchH / 2 - 30} width={26} height={60} />
          {/* Right goal area */}
          <rect x={pitchW - 10} y={pitchH / 2 - 14} width={10} height={28} />
          {/* Right goal */}
          <rect x={pitchW} y={pitchH / 2 - 6} width={3} height={12} strokeWidth={1} stroke="#3d8b5a" />
          {/* Right penalty spot */}
          <circle cx={pitchW - 18} cy={pitchH / 2} r={1} fill="#2d6b3f" />

          {/* Corner arcs */}
          <path d={`M 4 0 A 4 4 0 0 1 0 4`} />
          <path d={`M ${pitchW - 4} 0 A 4 4 0 0 0 ${pitchW} 4`} />
          <path d={`M 0 ${pitchH - 4} A 4 4 0 0 1 4 ${pitchH}`} />
          <path d={`M ${pitchW} ${pitchH - 4} A 4 4 0 0 0 ${pitchW - 4} ${pitchH}`} />
        </g>

        {/* Grass stripes */}
        <g opacity={0.04}>
          {Array.from({ length: 10 }).map((_, i) => (
            <rect
              key={i}
              x={i * (pitchW / 10)}
              y={0}
              width={pitchW / 10}
              height={pitchH}
              fill={i % 2 === 0 ? "#fff" : "transparent"}
            />
          ))}
        </g>

        {/* Direction arrow (ball movement) */}
        {hasDest && (
          <g>
            <defs>
              <marker
                id="arrowhead"
                markerWidth={5}
                markerHeight={4}
                refX={4}
                refY={2}
                orient="auto"
              >
                <polygon points="0 0, 5 2, 0 4" fill={isGoal ? "#fbbf24" : "rgba(255,255,255,0.5)"} />
              </marker>
            </defs>
            <line
              x1={bx} y1={by}
              x2={bx2} y2={by2}
              stroke={isGoal ? "#fbbf24" : "rgba(255,255,255,0.25)"}
              strokeWidth={isGoal ? 1.2 : 0.8}
              strokeDasharray={isGoal ? "none" : "3 2"}
              markerEnd="url(#arrowhead)"
            />
          </g>
        )}

        {/* Ball position */}
        <g>
          {/* Glow for goals */}
          {isGoal && (
            <circle cx={bx} cy={by} r={6} fill="#fbbf24" opacity={0.25}>
              <animate attributeName="r" values="4;8;4" dur="1.5s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.3;0.1;0.3" dur="1.5s" repeatCount="indefinite" />
            </circle>
          )}
          {/* Ball */}
          <circle
            cx={bx} cy={by} r={3}
            fill={isGoal ? "#fbbf24" : "#fff"}
            stroke={isGoal ? "#f59e0b" : "rgba(0,0,0,0.3)"}
            strokeWidth={0.5}
          />
          {/* Ball inner pattern */}
          <circle
            cx={bx} cy={by} r={1.5}
            fill="none"
            stroke={isGoal ? "#f59e0b" : "rgba(0,0,0,0.15)"}
            strokeWidth={0.3}
          />
        </g>

        {/* Team labels */}
        <text x={4} y={pitchH + 7} fontSize={5} fill="rgba(255,255,255,0.35)" fontFamily="system-ui">
          {homeTeam.split(" ").pop()}
        </text>
        <text x={pitchW - 4} y={pitchH + 7} fontSize={5} fill="rgba(255,255,255,0.35)" fontFamily="system-ui" textAnchor="end">
          {awayTeam.split(" ").pop()}
        </text>

        {/* Event icon overlay */}
        {eventType === "goal" && (
          <text x={bx + 5} y={by - 4} fontSize={7} fill="#fbbf24" fontWeight="bold">GOAL</text>
        )}
        {(extras?.redCard as boolean) && (
          <rect x={bx + 5} y={by - 8} width={4} height={6} rx={0.5} fill="#ef4444" />
        )}
        {(extras?.yellowCard as boolean) && (
          <rect x={bx + 5} y={by - 8} width={4} height={6} rx={0.5} fill="#eab308" />
        )}
      </svg>
    </div>
  );
}

/* ─── Soccer Play Row ─── */

function SoccerPlayRow({ play, homeTeam, awayTeam }: { play: PlayByPlayEntry; homeTeam: string; awayTeam: string }) {
  const eventType = play.extras?.eventType as string | undefined;
  const isGoal = play.scoring_play;
  const isCard = !!(play.extras?.redCard || play.extras?.yellowCard);
  const isKey = isGoal || isCard || eventType === "substitution" || eventType === "penalty-kick";

  return (
    <div
      className={`px-3 py-2 text-xs ${
        isGoal
          ? "bg-amber-500/10 border-l-2 border-l-amber-500"
          : play.extras?.redCard
            ? "bg-red-500/5 border-l-2 border-l-red-500"
            : play.extras?.yellowCard
              ? "bg-yellow-500/5 border-l-2 border-l-yellow-500"
              : "border-l-2 border-l-transparent"
      }`}
    >
      {/* Top: clock + event type badge */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-muted-foreground font-medium">
            {play.clock || ""}
          </span>
          {eventType && (
            <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${
              isGoal
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                : isCard
                  ? play.extras?.redCard
                    ? "bg-red-500/20 text-red-400 border border-red-500/30"
                    : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                  : "bg-muted/60 text-muted-foreground border border-border/30"
            }`}>
              {isGoal ? "\u26BD " : null}
              {play.extras?.redCard ? "\uD83D\uDFE5 " : null}
              {play.extras?.yellowCard ? "\uD83D\uDFE8 " : null}
              {eventType.replace(/-/g, " ")}
            </span>
          )}
        </div>
        {isGoal && (
          <span className="text-[10px] font-bold text-amber-400">
            {play.home_score} - {play.away_score}
          </span>
        )}
      </div>

      {/* Play description */}
      <p className={`text-xs leading-snug ${isGoal ? "text-amber-300 font-medium" : "text-foreground/90"}`}>
        {play.text}
      </p>

      {/* Pitch mini-map for key events */}
      {isKey && <SoccerPitch play={play} homeTeam={homeTeam} awayTeam={awayTeam} />}
    </div>
  );
}

/* ─── Sport-Specific Extras (non-soccer) ─── */

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

/* ─── Generic (non-soccer) Play Row ─── */

function GenericPlayRow({ play, sport }: { play: PlayByPlayEntry; sport: string }) {
  return (
    <div
      className={`flex items-start gap-2 px-3 py-1.5 text-xs ${
        play.scoring_play
          ? "border-l-2 border-l-amber-500 bg-amber-500/5"
          : "border-l-2 border-l-transparent"
      }`}
    >
      <span className="font-mono text-[11px] text-muted-foreground w-12 shrink-0 pt-0.5">
        {play.clock || ""}
      </span>
      <div className="flex-1 min-w-0">
        <p className={`text-xs leading-snug ${play.scoring_play ? "text-amber-300" : "text-foreground/90"}`}>
          {play.text}
        </p>
        <SportExtras play={play} sport={sport} />
      </div>
      {play.scoring_play && play.score_value > 0 && (
        <span className="shrink-0 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
          +{play.score_value}
        </span>
      )}
    </div>
  );
}

/* ─── Main Feed Component ─── */

export function PlayByPlayFeed({ predictionId, sport, isLive }: PlayByPlayFeedProps) {
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState<PlayByPlayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlay, setSelectedPlay] = useState<PlayByPlayEntry | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchPlays = useCallback(async () => {
    try {
      setError(null);
      const result = await apiFetch<PlayByPlayData>(
        `/api/predictions/${predictionId}/plays`,
        { requireAuth: true }
      );
      setData(result);
      // Auto-select most recent play with field data for soccer
      if (sport === "Soccer" && result.plays.length > 0 && !selectedPlay) {
        const withField = result.plays.find(p => p.extras?.fieldX);
        if (withField) setSelectedPlay(withField);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plays");
    } finally {
      setLoading(false);
    }
  }, [predictionId, sport, selectedPlay]);

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
  const isSoccer = sport === "Soccer";

  // For soccer: show the "hero" pitch at top with the selected/latest play
  const heroPlay = isSoccer
    ? (selectedPlay || data?.plays.find(p => p.extras?.fieldX) || null)
    : null;

  return (
    <div className="mb-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors py-1"
      >
        <Zap className="h-3 w-3" />
        {isSoccer ? "Live Tracker" : "Play-by-Play"}
        {expanded ? " \u25B4" : " \u25BE"}
      </button>

      {expanded && (
        <div className={`mt-1 rounded-lg border overflow-hidden ${
          isSoccer ? "border-emerald-500/20 bg-[#0d1f15]" : "border-border/40 bg-muted/20"
        }`}>
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
            <>
              {/* Soccer: Hero pitch at top showing selected play */}
              {isSoccer && heroPlay && (
                <div className="px-3 pt-3 pb-1">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400/70">
                      {heroPlay.clock || ""} {heroPlay.scoring_play ? "- GOAL!" : ""}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {data.home_team.split(" ").pop()} {data.home_score} - {data.away_score} {data.away_team.split(" ").pop()}
                    </span>
                  </div>
                  <SoccerPitch play={heroPlay} homeTeam={data.home_team} awayTeam={data.away_team} />
                  <p className="text-[11px] text-foreground/80 mt-1 leading-snug">{heroPlay.text}</p>
                </div>
              )}

              {/* Play list */}
              <div className="play-feed-scroll max-h-[300px] overflow-y-auto">
                {Array.from(grouped.entries()).map(([period, plays]: [string, PlayByPlayEntry[]]) => (
                  <div key={period}>
                    <div className={`sticky top-0 z-10 backdrop-blur-sm px-3 py-1 border-b ${
                      isSoccer
                        ? "bg-[#0d1f15]/90 border-emerald-500/15"
                        : "bg-muted/80 border-border/30"
                    }`}>
                      <span className={`text-[10px] font-semibold uppercase tracking-wider ${
                        isSoccer ? "text-emerald-400/60" : "text-muted-foreground"
                      }`}>
                        {period}
                      </span>
                    </div>
                    <div className={`divide-y ${isSoccer ? "divide-emerald-500/10" : "divide-border/20"}`}>
                      {plays.map((play) => (
                        <div
                          key={play.id}
                          onClick={() => isSoccer && play.extras?.fieldX ? setSelectedPlay(play) : null}
                          className={isSoccer && play.extras?.fieldX ? "cursor-pointer hover:bg-emerald-500/5 transition-colors" : ""}
                        >
                          {isSoccer ? (
                            <SoccerPlayRow play={play} homeTeam={data.home_team} awayTeam={data.away_team} />
                          ) : (
                            <GenericPlayRow play={play} sport={sport} />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
