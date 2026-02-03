"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TradingLinks } from "@/components/trading-links";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatAddress } from "@/lib/utils";
import { Trophy, ExternalLink, Copy, Check, Pin } from "lucide-react";
import type { TopCallout as TopCalloutType } from "@/lib/types";

export function TopCallout() {
  const [data, setData] = useState<TopCalloutType | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const res = await apiFetch<TopCalloutType | null>("/api/callouts/top");
        setData(res);
      } catch {
        // ignore
      }
    }
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  if (!data) return null;

  const { callout: c, ath_multiplier, current_multiplier } = data;
  const dexUrl = c.dexscreener_url || `https://dexscreener.com/solana/${c.token_address}`;

  function handleCopy() {
    navigator.clipboard.writeText(c.token_address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const signalColor =
    c.signal === "buy"
      ? "bg-green-500/10 text-green-500 border-green-500/20"
      : "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";

  return (
    <Card className="glass-card border-amber-500/30 bg-gradient-to-r from-amber-500/5 via-transparent to-amber-500/5 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-500" />
      <CardContent className="pt-4">
        <div className="flex items-center gap-2 mb-3">
          <Pin className="h-4 w-4 text-amber-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-amber-400">
            Top Call — Last 3 Days
          </span>
        </div>

        <div className="flex items-start justify-between">
          <div className="flex-1">
            {/* Token info */}
            <div className="flex items-center gap-2 mb-1">
              <span className="font-bold text-xl">{c.token_symbol}</span>
              {c.token_name && (
                <span className="text-sm text-muted-foreground">{c.token_name}</span>
              )}
              <Badge className={signalColor}>{c.signal.toUpperCase()}</Badge>
              {c.scan_source === "print_scan" && (
                <Badge className="text-[10px] px-1 py-0 bg-purple-500/10 text-purple-400 border-purple-500/20">
                  PRINT
                </Badge>
              )}
            </div>

            {/* Address */}
            <div className="flex items-center gap-2 mb-2">
              <code className="text-xs text-muted-foreground font-mono">
                {formatAddress(c.token_address, 6)}
              </code>
              <button
                onClick={handleCopy}
                className="text-muted-foreground hover:text-foreground transition-colors"
                title="Copy address"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-green-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
              <a
                href={dexUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>

            {/* Stats row */}
            <div className="flex items-center gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Entry MCap: </span>
                <span className="font-medium">{c.market_cap ? formatCurrency(c.market_cap) : "—"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Entry: </span>
                <span className="font-mono">{formatCurrency(c.price_at_callout)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Score: </span>
                <span className="font-medium">{c.score}</span>
              </div>
            </div>

            {/* Action row */}
            <div className="mt-2 flex items-center gap-3">
              <TradingLinks tokenAddress={c.token_address} variant="compact" />
              <a
                href={dexUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
              >
                DexScreener <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>

          {/* Multiplier display */}
          <div className="text-right flex flex-col items-end gap-1">
            <div className="flex items-center gap-1.5">
              <Trophy className="h-5 w-5 text-amber-400" />
              <span className="text-2xl font-bold text-amber-400">
                {ath_multiplier.toFixed(1)}x
              </span>
            </div>
            <span className="text-xs text-muted-foreground">ATH return</span>
            {current_multiplier !== null && current_multiplier !== undefined && (
              <div className="mt-1">
                <span
                  className={`text-sm font-bold ${
                    current_multiplier >= 1 ? "text-green-500" : "text-red-500"
                  }`}
                >
                  {current_multiplier.toFixed(1)}x
                </span>
                <span className="text-xs text-muted-foreground ml-1">now</span>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
