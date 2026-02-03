"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TradingLinks } from "@/components/trading-links";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import {
  Coins,
  ArrowUpCircle,
  Eye,
  ArrowDownCircle,
  Printer,
  Users,
} from "lucide-react";
import type { Callout } from "@/lib/types";

interface TokenItem {
  address: string;
  symbol: string;
  price: number;
  market_cap: number;
  volume_24h: number;
  smart_money_count: number;
  price_change_1h: number;
  price_change_24h: number;
  token_type: string;
  unique_wallets_24h: number;
}

export default function DashboardOverview() {
  const [callouts, setCallouts] = useState<Callout[]>([]);
  const [tokens, setTokens] = useState<TokenItem[]>([]);
  const [topMovers, setTopMovers] = useState<TokenItem[]>([]);
  const [totalTokens, setTotalTokens] = useState(0);
  const [loading, setLoading] = useState(true);
  const [lastScan, setLastScan] = useState<Date | null>(null);

  async function loadData() {
    try {
      const [calloutData, tokenData, moverData] = await Promise.all([
        apiFetch<{ callouts: Callout[]; total: number }>("/api/callouts?limit=10"),
        apiFetch<{ tokens: TokenItem[]; total: number }>("/api/tokens?limit=5&sort_by=smart_money_count"),
        apiFetch<{ tokens: TokenItem[]; total: number }>("/api/tokens?limit=5&sort_by=price_change_1h"),
      ]);
      setCallouts(calloutData.callouts);
      setTokens(tokenData.tokens);
      setTotalTokens(tokenData.total);
      setTopMovers(moverData.tokens);
      setLastScan(new Date());
    } catch {
      // silently handle
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <p className="text-muted-foreground">Loading dashboard...</p>;
  }

  const buySignals = callouts.filter((c) => c.signal === "buy").length;
  const watchSignals = callouts.filter((c) => c.signal === "watch").length;
  const sellSignals = callouts.filter((c) => c.signal === "sell").length;
  const printScanAlerts = callouts.filter((c) => c.scan_source === "print_scan").length;
  const smartWalletCount = tokens.reduce((sum, t) => sum + t.smart_money_count, 0);

  // Current prices and market caps for callout performance
  const priceMap: Record<string, number> = {};
  const mcapMap: Record<string, number> = {};
  for (const t of [...tokens, ...topMovers]) {
    priceMap[t.address] = t.price;
    if (t.market_cap) {
      mcapMap[t.address] = t.market_cap;
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Active signals */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        <Card className="glass-card card-hover group">
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              Tokens Tracked
            </CardTitle>
            <Coins className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{totalTokens}</p>
          </CardContent>
        </Card>
        <Card className="glass-card card-hover group">
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              BUY Signals
            </CardTitle>
            <ArrowUpCircle className="h-4 w-4 text-green-500/60 group-hover:text-green-500 transition-colors" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-green-500">{buySignals}</p>
          </CardContent>
        </Card>
        <Card className="glass-card card-hover group">
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              WATCH Signals
            </CardTitle>
            <Eye className="h-4 w-4 text-yellow-500/60 group-hover:text-yellow-500 transition-colors" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-yellow-500">{watchSignals}</p>
          </CardContent>
        </Card>
        <Card className="glass-card card-hover group">
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              SELL Signals
            </CardTitle>
            <ArrowDownCircle className="h-4 w-4 text-red-500/60 group-hover:text-red-500 transition-colors" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-red-500">{sellSignals}</p>
          </CardContent>
        </Card>
        <Card className="glass-card card-hover group">
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              PrintScan Alerts
            </CardTitle>
            <Printer className="h-4 w-4 text-purple-400/60 group-hover:text-purple-400 transition-colors" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-purple-400">{printScanAlerts}</p>
          </CardContent>
        </Card>
        <Card className="glass-card card-hover group">
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              Smart Wallets
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-primary">{smartWalletCount}</p>
          </CardContent>
        </Card>
      </div>

      {/* Scanner health */}
      {lastScan && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-primary animate-blink" />
          <span>
            Last scan: {lastScan.toLocaleTimeString()} &mdash; {totalTokens} tokens tracked &mdash; {smartWalletCount} smart wallets identified
          </span>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Top movers (1h) */}
        <Card className="glass-card card-hover">
          <CardHeader>
            <CardTitle>Top Movers (1h)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {topMovers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data yet</p>
            ) : (
              topMovers.map((t) => (
                <div
                  key={t.address}
                  className="flex items-center justify-between border-b border-border/30 pb-2 last:border-0"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{t.symbol}</span>
                    {t.token_type === "memecoin" && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">meme</Badge>
                    )}
                    <TradingLinks tokenAddress={t.address} variant="icon-only" />
                  </div>
                  <div className="text-right text-sm">
                    <p>{formatCurrency(t.price)}</p>
                    <p className={t.price_change_1h >= 0 ? "text-green-500 font-medium" : "text-red-500 font-medium"}>
                      {formatPercent(t.price_change_1h)}
                    </p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Recent callouts with live price delta */}
        <Card className="glass-card card-hover">
          <CardHeader>
            <CardTitle>Recent Callouts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {callouts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No callouts yet</p>
            ) : (
              callouts.slice(0, 10).map((c) => {
                const currentMcap = mcapMap[c.token_address];
                const calloutMcap = c.market_cap;
                let multiplier: number | null = null;
                if (currentMcap && currentMcap > 0 && calloutMcap && calloutMcap > 0) {
                  multiplier = currentMcap / calloutMcap;
                }
                let athMultiplier: number | null = null;
                if (calloutMcap && calloutMcap > 0 && c.peak_market_cap && c.peak_market_cap > 0) {
                  athMultiplier = c.peak_market_cap / calloutMcap;
                }

                return (
                  <div
                    key={c.id}
                    className="flex items-center justify-between border-b border-border/30 pb-2 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{c.token_symbol}</span>
                      <Badge
                        className={
                          c.signal === "buy"
                            ? "bg-green-500/10 text-green-500 border-green-500/20"
                            : c.signal === "sell"
                              ? "bg-red-500/10 text-red-500 border-red-500/20"
                              : "bg-yellow-500/10 text-yellow-500 border-yellow-500/20"
                        }
                      >
                        {c.signal.toUpperCase()}
                      </Badge>
                      {c.scan_source === "print_scan" && (
                        <Badge className="text-[10px] px-1 py-0 bg-purple-500/10 text-purple-400 border-purple-500/20">
                          PRINT
                        </Badge>
                      )}
                      <TradingLinks tokenAddress={c.token_address} variant="icon-only" />
                    </div>
                    <div className="text-right text-sm">
                      <p>{formatCurrency(c.price_at_callout)}</p>
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">Score: {c.score}</span>
                        {multiplier !== null && (
                          <span
                            className={`font-bold ${
                              multiplier >= 1 ? "text-green-500" : "text-red-500"
                            }`}
                          >
                            {multiplier.toFixed(1)}x
                          </span>
                        )}
                        {athMultiplier !== null && athMultiplier > 1 && (
                          <span className="font-bold text-amber-400">
                            ATH {athMultiplier.toFixed(1)}x
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top smart money tokens */}
      <Card className="glass-card card-hover">
        <CardHeader>
          <CardTitle>Top Smart Money Tokens</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3">
            {tokens.length === 0 ? (
              <p className="text-sm text-muted-foreground">No tokens scanned yet</p>
            ) : (
              tokens.map((t) => (
                <div
                  key={t.address}
                  className="flex items-center justify-between border-b border-border/30 pb-2 last:border-0"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{t.symbol}</span>
                    <span className="text-sm text-muted-foreground">
                      {t.smart_money_count} wallets
                    </span>
                    {t.token_type === "memecoin" && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">meme</Badge>
                    )}
                  </div>
                  <div className="text-right text-sm">
                    <p>{formatCurrency(t.price)}</p>
                    <p className={t.price_change_24h >= 0 ? "text-green-500" : "text-red-500"}>
                      {formatPercent(t.price_change_24h)}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
