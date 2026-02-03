"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { CalloutFeed } from "@/components/callout-feed";
import { apiFetch } from "@/lib/api";
import { getMe, type User } from "@/lib/auth";
import { Bell, ArrowUpCircle, ArrowDownCircle, Eye } from "lucide-react";
import type { Callout } from "@/lib/types";

type SignalFilter = "all" | "buy" | "sell" | "watch";

export default function CalloutsPage() {
  const [callouts, setCallouts] = useState<Callout[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("all");

  useEffect(() => {
    async function load() {
      try {
        const [userData, calloutData] = await Promise.all([
          getMe(),
          apiFetch<{ callouts: Callout[] }>("/api/callouts?limit=50"),
        ]);
        setUser(userData);
        setCallouts(calloutData.callouts);
      } catch {
        // silently handle
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Auto-refresh callouts every 30s
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const data = await apiFetch<{ callouts: Callout[] }>("/api/callouts?limit=50");
        setCallouts(data.callouts);
      } catch {
        // ignore
      }
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const isPro = user?.tier === "pro" || user?.tier === "legend";

  const filterButtons: { key: SignalFilter; label: string; color: string }[] = [
    { key: "all", label: "All", color: "" },
    { key: "buy", label: "BUY", color: "text-green-500" },
    { key: "sell", label: "SELL", color: "text-red-500" },
    { key: "watch", label: "WATCH", color: "text-yellow-500" },
  ];

  // Signal counts
  const buys = callouts.filter((c) => c.signal === "buy").length;
  const sells = callouts.filter((c) => c.signal === "sell").length;
  const watches = callouts.filter((c) => c.signal === "watch").length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Callout Feed</h1>
        </div>
        {!isPro && (
          <p className="text-sm text-muted-foreground">
            Free tier: showing last 5 callouts with 5min delay.
            Upgrade for real-time SSE feed.
          </p>
        )}
      </div>

      {/* Signal counts */}
      <div className="flex gap-4 text-sm">
        <span className="flex items-center gap-1 text-green-500 font-medium">
          <ArrowUpCircle className="h-3.5 w-3.5" /> {buys} BUY
        </span>
        <span className="flex items-center gap-1 text-red-500 font-medium">
          <ArrowDownCircle className="h-3.5 w-3.5" /> {sells} SELL
        </span>
        <span className="flex items-center gap-1 text-yellow-500 font-medium">
          <Eye className="h-3.5 w-3.5" /> {watches} WATCH
        </span>
      </div>

      {/* Signal type filter */}
      <div className="flex gap-1 border-b border-border/30 pb-2">
        {filterButtons.map((btn) => (
          <Button
            key={btn.key}
            variant={signalFilter === btn.key ? "default" : "ghost"}
            size="sm"
            onClick={() => setSignalFilter(btn.key)}
            className={signalFilter !== btn.key ? btn.color : ""}
          >
            {btn.label}
          </Button>
        ))}
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading callouts...</p>
      ) : (
        <CalloutFeed
          initialCallouts={callouts}
          enableSSE={isPro}
          signalFilter={signalFilter === "all" ? null : signalFilter}
        />
      )}
    </div>
  );
}
