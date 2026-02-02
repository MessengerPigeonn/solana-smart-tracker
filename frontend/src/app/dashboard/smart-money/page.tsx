"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { OverlapTable } from "@/components/overlap-table";
import { apiFetch } from "@/lib/api";

interface OverlapEntry {
  wallet: string;
  tokens: string[];
  total_pnl: number;
  overlap_count: number;
}

interface TopWallet {
  wallet: string;
  total_pnl: number;
  trade_count: number;
  tokens_traded: number;
  win_rate: number;
}

export default function SmartMoneyPage() {
  const [tokenAddresses, setTokenAddresses] = useState("");
  const [threshold, setThreshold] = useState("2");
  const [overlaps, setOverlaps] = useState<OverlapEntry[]>([]);
  const [topWallets, setTopWallets] = useState<TopWallet[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleFindOverlaps(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await apiFetch<{ overlaps: OverlapEntry[] }>(
        `/api/smart-money/overlaps?tokens=${encodeURIComponent(tokenAddresses)}&threshold=${threshold}`,
        { requireAuth: true }
      );
      setOverlaps(data.overlaps);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to find overlaps");
    } finally {
      setLoading(false);
    }
  }

  async function loadTopWallets() {
    setError("");
    try {
      const data = await apiFetch<TopWallet[]>("/api/smart-money/top", {
        requireAuth: true,
      });
      setTopWallets(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load top wallets"
      );
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Smart Money Analysis</h1>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {/* Overlap finder */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Overlap Detection</CardTitle>
          <p className="text-sm text-muted-foreground">
            Find wallets that trade across multiple tokens. Paste token addresses
            separated by commas.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleFindOverlaps} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="tokens">Token Addresses</Label>
              <Input
                id="tokens"
                placeholder="addr1, addr2, addr3..."
                value={tokenAddresses}
                onChange={(e) => setTokenAddresses(e.target.value)}
                required
              />
            </div>
            <div className="flex gap-3 items-end">
              <div className="space-y-2">
                <Label htmlFor="threshold">Min Overlap</Label>
                <Input
                  id="threshold"
                  type="number"
                  min={2}
                  max={10}
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  className="w-24"
                />
              </div>
              <Button type="submit" disabled={loading}>
                {loading ? "Searching..." : "Find Overlaps"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {overlaps.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">
            Found {overlaps.length} overlapping wallets
          </h2>
          <OverlapTable overlaps={overlaps} />
        </div>
      )}

      {/* Top smart wallets */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-lg">Top Smart Wallets</CardTitle>
            <p className="text-sm text-muted-foreground">
              Most profitable wallets across all scanned tokens (Legend tier)
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={loadTopWallets}>
            Load
          </Button>
        </CardHeader>
        {topWallets.length > 0 && (
          <CardContent>
            <div className="space-y-2">
              {topWallets.map((w) => (
                <div
                  key={w.wallet}
                  className="flex items-center justify-between border-b pb-2 last:border-0"
                >
                  <div>
                    <p className="font-mono text-sm">{w.wallet.slice(0, 12)}...</p>
                    <p className="text-xs text-muted-foreground">
                      {w.trade_count} trades / {w.tokens_traded} tokens / {w.win_rate}% WR
                    </p>
                  </div>
                  <span
                    className={`font-medium ${
                      w.total_pnl >= 0 ? "text-green-500" : "text-red-500"
                    }`}
                  >
                    ${Math.abs(w.total_pnl).toLocaleString(undefined, {
                      maximumFractionDigits: 2,
                    })}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
