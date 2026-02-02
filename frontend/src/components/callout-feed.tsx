"use client";

import { useEffect, useRef, useState } from "react";
import { CalloutCard } from "./callout-card";
import { getSSEUrl, apiFetch } from "@/lib/api";

interface Callout {
  id: number;
  token_symbol: string;
  token_address: string;
  signal: string;
  score: number;
  reason: string;
  smart_wallets: string[];
  price_at_callout: number;
  scan_source?: string;
  created_at: string;
}

interface CalloutFeedProps {
  initialCallouts: Callout[];
  enableSSE: boolean;
  signalFilter?: string | null;
}

export function CalloutFeed({ initialCallouts, enableSSE, signalFilter }: CalloutFeedProps) {
  const [callouts, setCallouts] = useState<Callout[]>(initialCallouts);
  const [connected, setConnected] = useState(false);
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({});
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setCallouts(initialCallouts);
  }, [initialCallouts]);

  // Fetch current prices for tokens that have callouts older than 5 min
  useEffect(() => {
    async function fetchPrices() {
      const addresses = Array.from(new Set(callouts.map((c) => c.token_address)));
      if (addresses.length === 0) return;

      try {
        const data = await apiFetch<{ tokens: { address: string; price: number }[] }>(
          `/api/tokens?limit=100`
        );
        const prices: Record<string, number> = {};
        for (const t of data.tokens) {
          prices[t.address] = t.price;
        }
        setCurrentPrices(prices);
      } catch {
        // ignore
      }
    }

    fetchPrices();
    const interval = setInterval(fetchPrices, 30000);
    return () => clearInterval(interval);
  }, [callouts]);

  useEffect(() => {
    if (!enableSSE) return;

    const token = localStorage.getItem("access_token");
    if (!token) return;

    const url = `${getSSEUrl("/api/callouts/stream")}`;
    const es = new EventSource(url);

    eventSourceRef.current = es;

    es.addEventListener("callout", (event) => {
      const newCallout: Callout = JSON.parse(event.data);
      setCallouts((prev) => [newCallout, ...prev].slice(0, 50));
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [enableSSE]);

  const filtered = signalFilter
    ? callouts.filter((c) => c.signal === signalFilter)
    : callouts;

  return (
    <div className="space-y-3">
      {enableSSE && (
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? "bg-primary animate-blink" : "bg-red-500"
            }`}
          />
          <span className={connected ? "text-primary" : "text-muted-foreground"}>
            {connected ? "Live" : "Disconnected"}
          </span>
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-muted-foreground text-center py-8">
          No callouts yet. The scanner is analyzing tokens...
        </p>
      ) : (
        filtered.map((c) => (
          <CalloutCard
            key={c.id}
            tokenSymbol={c.token_symbol}
            tokenAddress={c.token_address}
            signal={c.signal}
            score={c.score}
            reason={c.reason}
            smartWallets={c.smart_wallets}
            priceAtCallout={c.price_at_callout}
            currentPrice={currentPrices[c.token_address]}
            scanSource={c.scan_source}
            createdAt={c.created_at}
          />
        ))
      )}
    </div>
  );
}
