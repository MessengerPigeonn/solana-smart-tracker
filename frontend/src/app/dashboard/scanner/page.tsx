"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TokenTable, type Token } from "@/components/token-table";
import { apiFetch } from "@/lib/api";
import { Radar, RefreshCw, Search } from "lucide-react";

type FilterTab = "all" | "trending" | "new" | "smart" | "print_scan";
type McapFilter = "all" | "micro" | "small" | "medium";

const MCAP_RANGES: Record<McapFilter, { min?: number; max?: number; label: string }> = {
  all: { label: "All" },
  micro: { min: 0, max: 100_000, label: "Micro (<$100K)" },
  small: { min: 100_000, max: 500_000, label: "Small ($100K-$500K)" },
  medium: { min: 500_000, max: 50_000_000, label: "Medium ($500K-$50M)" },
};

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

    // Filter tab logic
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
      // Default to micro range for PrintScan
      if (mcapFilter === "all") {
        params.set("mcap_min", "0");
        params.set("mcap_max", "500000");
      }
    }

    // Market cap filter
    const range = MCAP_RANGES[mcapFilter];
    if (range.min !== undefined) params.set("mcap_min", range.min.toString());
    if (range.max !== undefined) params.set("mcap_max", range.max.toString());

    // Default to memecoins only (except print_scan which may include unknowns)
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

  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "trending", label: "Trending" },
    { key: "new", label: "New" },
    { key: "smart", label: "Smart Money" },
    { key: "print_scan", label: "PrintScan" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radar className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Token Scanner</h1>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-muted-foreground">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button variant="outline" size="sm" className="hover:border-primary/50 gap-1.5" onClick={fetchTokens}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 border-b border-border/30 pb-2">
        {tabs.map((tab) => (
          <Button
            key={tab.key}
            variant={filterTab === tab.key ? "default" : "ghost"}
            size="sm"
            onClick={() => handleTabChange(tab.key)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {/* Market cap filter chips */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-muted-foreground">MCap:</span>
        {(Object.entries(MCAP_RANGES) as [McapFilter, { label: string }][]).map(([key, { label }]) => (
          <Badge
            key={key}
            variant={mcapFilter === key ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => {
              setMcapFilter(key);
              setOffset(0);
            }}
          >
            {label}
          </Badge>
        ))}
      </div>

      <div className="relative max-w-md">
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

      {loading ? (
        <p className="text-muted-foreground">Loading tokens...</p>
      ) : (
        <>
          <TokenTable
            tokens={tokens}
            onSort={handleSort}
            sortBy={sortBy}
            sortOrder={sortOrder}
          />
          {!search && total > limit && (
            <div className="flex justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground self-center">
                {offset + 1}-{Math.min(offset + limit, total)} of {total}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + limit >= total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
