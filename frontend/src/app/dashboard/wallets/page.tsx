"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WalletCard } from "@/components/wallet-card";
import { WalletAnalyticsView } from "@/components/wallet-analytics";
import { apiFetch } from "@/lib/api";

interface TrackedWallet {
  id: number;
  wallet_address: string;
  label: string;
  created_at: string;
}

interface WalletAnalyticsData {
  wallet_address: string;
  total_pnl: number;
  trade_count: number;
  win_rate: number;
  recent_trades: Array<{
    token_address: string;
    token_symbol: string;
    volume_buy: number;
    volume_sell: number;
    estimated_pnl: number;
    scanned_at: string;
  }>;
  tokens_traded: number;
}

export default function WalletsPage() {
  const [wallets, setWallets] = useState<TrackedWallet[]>([]);
  const [analytics, setAnalytics] = useState<WalletAnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newAddress, setNewAddress] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [adding, setAdding] = useState(false);

  async function loadWallets() {
    try {
      const data = await apiFetch<TrackedWallet[]>("/api/wallets", {
        requireAuth: true,
      });
      setWallets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load wallets");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWallets();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setAdding(true);

    try {
      await apiFetch("/api/wallets", {
        method: "POST",
        requireAuth: true,
        body: JSON.stringify({
          wallet_address: newAddress,
          label: newLabel || undefined,
        }),
      });
      setNewAddress("");
      setNewLabel("");
      await loadWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add wallet");
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(id: number) {
    try {
      await apiFetch(`/api/wallets/${id}`, {
        method: "DELETE",
        requireAuth: true,
      });
      setWallets((prev) => prev.filter((w) => w.id !== id));
      if (analytics) setAnalytics(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove wallet");
    }
  }

  async function handleViewAnalytics(address: string) {
    try {
      const data = await apiFetch<WalletAnalyticsData>(
        `/api/wallets/${address}/analytics`,
        { requireAuth: true }
      );
      setAnalytics(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load analytics"
      );
    }
  }

  if (loading) {
    return <p className="text-muted-foreground">Loading wallets...</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Tracked Wallets</h1>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {/* Add wallet form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Add Wallet</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAdd} className="flex gap-3 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <Label htmlFor="address" className="sr-only">
                Wallet Address
              </Label>
              <Input
                id="address"
                placeholder="Solana wallet address"
                value={newAddress}
                onChange={(e) => setNewAddress(e.target.value)}
                required
              />
            </div>
            <div className="w-40">
              <Label htmlFor="label" className="sr-only">
                Label
              </Label>
              <Input
                id="label"
                placeholder="Label (optional)"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={adding}>
              {adding ? "Adding..." : "Add"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Wallet list */}
      <div className="space-y-3">
        {wallets.length === 0 ? (
          <p className="text-muted-foreground text-center py-8">
            No wallets tracked yet. Add a whale wallet above to get started.
          </p>
        ) : (
          wallets.map((w) => (
            <WalletCard
              key={w.id}
              id={w.id}
              walletAddress={w.wallet_address}
              label={w.label}
              onRemove={handleRemove}
              onViewAnalytics={handleViewAnalytics}
            />
          ))
        )}
      </div>

      {/* Analytics panel */}
      {analytics && (
        <div className="mt-6">
          <WalletAnalyticsView data={analytics} />
        </div>
      )}
    </div>
  );
}
