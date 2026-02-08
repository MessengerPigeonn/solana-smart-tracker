"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PredictionCard } from "@/components/prediction-card";
import { PredictionStatsBanner } from "@/components/prediction-stats-banner";
import { apiFetch, getSSEUrl } from "@/lib/api";
import { getMe, type User } from "@/lib/auth";
import { CalendarClock, Flame, CheckCircle, Lock } from "lucide-react";
import type { Prediction, PredictionStats, LiveScoreData } from "@/lib/types";

type TabFilter = "upcoming" | "live" | "settled";
type SportFilter = "all" | "NBA" | "NFL" | "MLB" | "NHL" | "UFC" | "Soccer";

function tabEndpoint(tab: TabFilter): string {
  switch (tab) {
    case "upcoming":
      return "/api/predictions/upcoming";
    case "live":
      return "/api/predictions/live";
    case "settled":
      return "/api/predictions/settled?limit=50";
  }
}

export default function PredictionsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<PredictionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabFilter>("upcoming");
  const [sportFilter, setSportFilter] = useState<SportFilter>("all");
  const [total, setTotal] = useState(0);
  const [liveScores, setLiveScores] = useState<Record<number, LiveScoreData>>({});

  useEffect(() => {
    async function load() {
      try {
        const userData = await getMe();
        setUser(userData);

        if (userData.tier !== "legend") {
          setLoading(false);
          return;
        }

        const [predData, statsData] = await Promise.all([
          apiFetch<{ predictions: Prediction[]; total: number }>(tabEndpoint("upcoming")),
          apiFetch<PredictionStats>("/api/predictions/stats"),
        ]);

        setPredictions(predData.predictions);
        setTotal(predData.total);
        setStats(statsData);
      } catch {
        // silently handle
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Auto-refresh: 15s for live tab, 60s for others
  useEffect(() => {
    if (user?.tier !== "legend") return;

    const refreshMs = tab === "live" ? 15000 : 60000;
    const interval = setInterval(async () => {
      try {
        const data = await apiFetch<{ predictions: Prediction[]; total: number }>(tabEndpoint(tab));
        setPredictions(data.predictions);
        setTotal(data.total);
      } catch {
        // ignore
      }
    }, refreshMs);
    return () => clearInterval(interval);
  }, [user, tab]);

  // SSE stream for live scores when on "live" tab
  const eventSourceRef = useRef<EventSource | null>(null);
  useEffect(() => {
    if (user?.tier !== "legend") return;
    if (tab !== "live") return;

    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token) return;

    const url = getSSEUrl(`/api/predictions/live-scores/stream?token=${encodeURIComponent(token)}`);
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const scores = JSON.parse(event.data) as Record<string, LiveScoreData>;
        // EventSource keys are strings, convert to number keys
        const mapped: Record<number, LiveScoreData> = {};
        for (const [k, v] of Object.entries(scores)) {
          mapped[Number(k)] = v;
        }
        setLiveScores(mapped);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; nothing to do here
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [user, tab]);

  const handleTabChange = async (newTab: TabFilter) => {
    setTab(newTab);
    setLoading(true);
    setLiveScores({});
    try {
      const data = await apiFetch<{ predictions: Prediction[]; total: number }>(tabEndpoint(newTab));
      setPredictions(data.predictions);
      setTotal(data.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  // Filter by sport only — sorting is handled server-side per tab
  const filtered = sportFilter === "all"
    ? predictions
    : predictions.filter((p) => p.sport === sportFilter);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">Loading predictions...</p>
      </div>
    );
  }

  // Gate for non-legend users
  if (user?.tier !== "legend") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center space-y-4 max-w-md">
          <Lock className="h-12 w-12 text-muted-foreground mx-auto" />
          <h2 className="text-xl font-bold">Legend Tier Feature</h2>
          <p className="text-muted-foreground">
            Sports predictions powered by AI are available exclusively for Legend tier members.
            Upgrade to access expert picks across NBA, NFL, MLB, NHL, UFC, and Soccer.
          </p>
          <Button onClick={() => router.push("/dashboard/billing")}>
            Upgrade to Legend
          </Button>
        </div>
      </div>
    );
  }

  const sports: SportFilter[] = ["all", "NBA", "NFL", "MLB", "NHL", "UFC", "Soccer"];

  const tabLabel = tab === "upcoming" ? "upcoming" : tab === "live" ? "live" : "settled";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Predictions</h1>
          <Badge variant="teal" className="text-[10px]">LEGEND</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{total} {tabLabel} picks</p>
      </div>

      {/* Stats Banner */}
      <PredictionStatsBanner stats={stats} />

      {/* Tab + Sport Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="flex gap-1">
          {([
            { key: "upcoming" as TabFilter, label: "Upcoming", icon: CalendarClock },
            { key: "live" as TabFilter, label: "Live", icon: Flame },
            { key: "settled" as TabFilter, label: "Settled", icon: CheckCircle },
          ]).map((t) => (
            <Button
              key={t.key}
              variant={tab === t.key ? "default" : "ghost"}
              size="sm"
              onClick={() => handleTabChange(t.key)}
              className="gap-1.5"
            >
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </Button>
          ))}
        </div>

        <div className="flex gap-1 flex-wrap">
          {sports.map((s) => (
            <Button
              key={s}
              variant={sportFilter === s ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setSportFilter(s)}
              className="text-xs h-7 px-2"
            >
              {s === "all" ? "All Sports" : s}
            </Button>
          ))}
        </div>
      </div>

      {/* Prediction Cards Grid */}
      {filtered.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p>
            {tab === "upcoming"
              ? "No upcoming predictions. New picks are generated every 15 minutes."
              : tab === "live"
                ? "No live games right now."
                : "No settled predictions yet."}
          </p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((prediction) => (
            <PredictionCard key={prediction.id} prediction={prediction} liveScore={liveScores[prediction.id]} />
          ))}
        </div>
      )}
    </div>
  );
}
