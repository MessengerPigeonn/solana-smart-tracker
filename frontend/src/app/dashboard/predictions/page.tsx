"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PredictionCard } from "@/components/prediction-card";
import { PredictionStatsBanner } from "@/components/prediction-stats-banner";
import { apiFetch } from "@/lib/api";
import { getMe, type User } from "@/lib/auth";
import { Trophy, Flame, Clock, Lock } from "lucide-react";
import type { Prediction, PredictionStats, LiveScoreData } from "@/lib/types";

type TabFilter = "all" | "live" | "settled";
type SportFilter = "all" | "NBA" | "NFL" | "MLB" | "NHL" | "UFC" | "Soccer";

export default function PredictionsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<PredictionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabFilter>("all");
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
          apiFetch<{ predictions: Prediction[]; total: number }>("/api/predictions?limit=50"),
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

  // Auto-refresh every 60s
  useEffect(() => {
    if (user?.tier !== "legend") return;

    const interval = setInterval(async () => {
      try {
        const params = tab === "live" ? "/api/predictions/live" : "/api/predictions?limit=50";
        const data = await apiFetch<{ predictions: Prediction[]; total: number }>(params);
        setPredictions(data.predictions);
        setTotal(data.total);
      } catch {
        // ignore
      }
    }, 60000);
    return () => clearInterval(interval);
  }, [user, tab]);

  // Poll live scores every 30s when on "live" or "all" tab
  useEffect(() => {
    if (user?.tier !== "legend") return;
    if (tab === "settled") return;

    let cancelled = false;
    const fetchLiveScores = async () => {
      try {
        const data = await apiFetch<{ scores: Record<number, LiveScoreData> }>(
          "/api/predictions/live-scores"
        );
        if (!cancelled) {
          setLiveScores(data.scores);
        }
      } catch {
        // ignore
      }
    };

    // Fetch immediately then poll
    fetchLiveScores();
    const interval = setInterval(fetchLiveScores, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [user, tab]);

  const handleTabChange = async (newTab: TabFilter) => {
    setTab(newTab);
    setLoading(true);
    try {
      let data: { predictions: Prediction[]; total: number };
      if (newTab === "live") {
        data = await apiFetch<{ predictions: Prediction[]; total: number }>("/api/predictions/live");
      } else if (newTab === "settled") {
        // Fetch wins, losses, and pushes in parallel
        const [wins, losses, pushes] = await Promise.all([
          apiFetch<{ predictions: Prediction[] }>("/api/predictions?result=win&limit=50"),
          apiFetch<{ predictions: Prediction[] }>("/api/predictions?result=loss&limit=50"),
          apiFetch<{ predictions: Prediction[] }>("/api/predictions?result=push&limit=50"),
        ]);
        const all = [...wins.predictions, ...losses.predictions, ...pushes.predictions]
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 50);
        data = { predictions: all, total: all.length };
      } else {
        data = await apiFetch<{ predictions: Prediction[]; total: number }>("/api/predictions?limit=50");
      }
      setPredictions(data.predictions);
      setTotal(data.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  // Filter by sport, then sort: upcoming by soonest commence_time, then by confidence desc
  const filtered = (sportFilter === "all"
    ? predictions
    : predictions.filter((p) => p.sport === sportFilter)
  ).sort((a, b) => {
    const now = Date.now();
    const aUpcoming = new Date(a.commence_time).getTime() > now;
    const bUpcoming = new Date(b.commence_time).getTime() > now;

    // Upcoming events first
    if (aUpcoming && !bUpcoming) return -1;
    if (!aUpcoming && bUpcoming) return 1;

    if (aUpcoming && bUpcoming) {
      // Both upcoming: soonest first, then highest confidence
      const timeDiff = new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime();
      if (timeDiff !== 0) return timeDiff;
      return b.confidence - a.confidence;
    }

    // Both past: highest confidence first
    return b.confidence - a.confidence;
  });

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

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Trophy className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Predictions</h1>
          <Badge variant="teal" className="text-[10px]">LEGEND</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{total} total picks</p>
      </div>

      {/* Stats Banner */}
      <PredictionStatsBanner stats={stats} />

      {/* Tab + Sport Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="flex gap-1">
          {([
            { key: "all" as TabFilter, label: "All Picks", icon: Trophy },
            { key: "live" as TabFilter, label: "Live", icon: Flame },
            { key: "settled" as TabFilter, label: "Settled", icon: Clock },
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
          <p>No predictions match your filters.</p>
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
