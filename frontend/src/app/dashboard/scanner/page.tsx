"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { TokenTable, type Token } from "@/components/token-table";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import {
  Radar,
  RefreshCw,
  Search,
  TrendingUp,
  Sparkles,
  Brain,
  Printer,
  Layers,
  BarChart3,
  Droplets,
  Users,
  ShieldAlert,
} from "lucide-react";

type FilterTab = "all" | "trending" | "new" | "smart" | "print_scan";
type McapFilter = "all" | "micro" | "small" | "medium";

const MCAP_RANGES: Record<McapFilter, { min?: number; max?: number; label: string }> = {
  all: { label: "All Caps" },
  micro: { min: 0, max: 100_000, label: "Micro <$100K" },
  small: { min: 100_000, max: 500_000, label: "Small $100K-$500K" },
  medium: { min: 500_000, max: 50_000_000, label: "Mid $500K-$50M" },
};

const TABS: {
  key: FilterTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}[] = [
  { key: "all", label: "All", icon: Layers, color: "" },
  { key: "trending", label: "Trending", icon: TrendingUp, color: "text-green-500" },
  { key: "new", label: "New", icon: Sparkles, color: "text-yellow-500" },
  { key: "smart", label: "Smart Money", icon: Brain, color: "text-primary" },
  { key: "print_scan", label: "PrintScan", icon: Printer, color: "text-purple-400" },
];

export default function ScannerPage() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("volume_24h");
  const [sortOrder, setSortOrder] = useState("desc");
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filterTab, setFilterTab] = useState<FilterTab>("all");
  const [mcapFilter, setMcapFilter] = useState<McapFilter>("all");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const limit = 20;
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const buildUrl = useCallback(() => {
    if (search) {
      return `/api/tokens/search?q=${encodeURIComponent(search)}`;
    }

    const params = new URLSearchParams({
      sort_by: sortBy,
      order: sortOrder,
      offset: offset.toString(),
      limit: limit.toString(),
    });

    if (filterTab === "trending") {
      params.set("sort_by", "volume_24h");
      params.set("order", "desc");
    } else if (filterTab === "new") {
      params.set("sort_by", "last_scanned");
      params.set("order", "desc");
    } else if (filterTab === "smart") {
      params.set("sort_by", "smart_money_count");
      params.set("order", "desc");
    } else if (filterTab === "print_scan") {
      params.set("scan_source", "print_scan");
      params.set("sort_by", "last_scanned");
      params.set("order", "desc");
      if (mcapFilter === "all") {
        params.set("mcap_min", "0");
        params.set("mcap_max", "500000");
      }
    }

    const range = MCAP_RANGES[mcapFilter];
    if (range.min !== undefined) params.set("mcap_min", range.min.toString());
    if (range.max !== undefined) params.set("mcap_max", range.max.toString());

    if (filterTab !== "print_scan") {
      params.set("token_type", "memecoin");
    }

    return `/api/tokens?${params.toString()}`;
  }, [search, sortBy, sortOrder, offset, filterTab, mcapFilter]);

  const fetchTokens = useCallback(async () => {
    try {
      const url = buildUrl();
      const data = await apiFetch<{ tokens: Token[]; total: number }>(url);
      setTokens(data.tokens);
      setTotal(data.total);
      setLastUpdated(new Date());
    } catch {
      // silently handle
    } finally {
      setLoading(false);
    }
  }, [buildUrl]);

  useEffect(() => {
    setLoading(true);
    fetchTokens();
  }, [fetchTokens]);

  // Auto-refresh: 10s for PrintScan, 15s for others
  useEffect(() => {
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    const interval = filterTab === "print_scan" ? 10000 : 15000;
    refreshTimerRef.current = setInterval(fetchTokens, interval);
    return () => {
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    };
  }, [fetchTokens, filterTab]);

  function handleSort(column: string) {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
    setOffset(0);
  }

  function handleTabChange(tab: FilterTab) {
    setFilterTab(tab);
    setOffset(0);
    setSearch("");
  }

  // Derived stats
  const avgVolume =
    tokens.length > 0
      ? tokens.reduce((sum, t) => sum + t.volume_24h, 0) / tokens.length
      : 0;
  const avgLiquidity =
    tokens.length > 0
      ? tokens.reduce((sum, t) => sum + t.liquidity, 0) / tokens.length
      : 0;
  const totalSmartMoney = tokens.reduce((sum, t) => sum + t.smart_money_count, 0);
  const riskyCount = tokens.filter(
    (t) => t.rug_risk_score && t.rug_risk_score > 50
  ).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Radar className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Token Scanner</h1>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-primary animate-blink" />
            <span className="text-xs text-primary font-medium">
              {filterTab === "print_scan" ? "10s" : "15s"} refresh
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-muted-foreground">
              {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            className="hover:border-primary/50 gap-1.5"
            onClick={fetchTokens}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats banner */}
      <Card className="glass-card border-primary/20 bg-gradient-to-r from-primary/5 to-transparent">
        <CardContent className="py-3 px-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              <div>
                <p className="text-[10px] text-muted-foreground uppercase">
                  Tokens
                </p>
                <p className="text-sm font-bold">{total}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-green-500" />
              <div>
                <p className="text-[10px] text-muted-foreground uppercase">
                  Avg Volume
                </p>
                <p className="text-sm font-bold text-green-500">
                  {avgVolume > 0 ? formatCurrency(avgVolume) : "—"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Droplets className="h-4 w-4 text-blue-400" />
              <div>
                <p className="text-[10px] text-muted-foreground uppercase">
                  Avg Liquidity
                </p>
                <p className="text-sm font-bold text-blue-400">
                  {avgLiquidity > 0 ? formatCurrency(avgLiquidity) : "—"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-primary" />
              <div>
                <p className="text-[10px] text-muted-foreground uppercase">
                  Smart Wallets
                </p>
                <p className="text-sm font-bold text-primary">
                  {totalSmartMoney}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-red-500" />
              <div>
                <p className="text-[10px] text-muted-foreground uppercase">
                  High Risk
                </p>
                <p className="text-sm font-bold text-red-500">{riskyCount}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Filter tabs with icons */}
      <div className="flex gap-1 border-b border-border/30 pb-2">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = filterTab === tab.key;
          return (
            <Button
              key={tab.key}
              variant={active ? "default" : "ghost"}
              size="sm"
              onClick={() => handleTabChange(tab.key)}
              className={`gap-1.5 ${!active && tab.color}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </Button>
          );
        })}
      </div>

      {/* Market cap filter + search row */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="flex items-center gap-1.5">
          {(Object.entries(MCAP_RANGES) as [McapFilter, { label: string }][]).map(
            ([key, { label }]) => (
              <Button
                key={key}
                variant={mcapFilter === key ? "default" : "outline"}
                size="sm"
                className={`h-7 text-xs ${
                  mcapFilter === key
                    ? ""
                    : "hover:border-primary/50 hover:text-primary"
                }`}
                onClick={() => {
                  setMcapFilter(key);
                  setOffset(0);
                }}
              >
                {label}
              </Button>
            )
          )}
        </div>
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by ticker or address..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
            className="pl-9"
          />
        </div>
      </div>

      {/* Token table */}
      {loading ? (
        <Card className="glass-card">
          <CardContent className="py-12 text-center">
            <Radar className="h-8 w-8 text-primary animate-spin mx-auto mb-3" />
            <p className="text-muted-foreground">Scanning tokens...</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <TokenTable
            tokens={tokens}
            onSort={handleSort}
            sortBy={sortBy}
            sortOrder={sortOrder}
          />

          {/* Pagination */}
          {!search && total > limit && (
            <Card className="glass-card">
              <CardContent className="py-2 px-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    Showing {offset + 1}–{Math.min(offset + limit, total)} of{" "}
                    {total} tokens
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - limit))}
                      className="hover:border-primary/50"
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={offset + limit >= total}
                      onClick={() => setOffset(offset + limit)}
                      className="hover:border-primary/50"
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
