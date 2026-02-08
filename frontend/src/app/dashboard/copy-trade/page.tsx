"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { getMe, type User } from "@/lib/auth";
import { formatAddress, formatCurrency } from "@/lib/utils";
import type {
  CopyTradeConfig, CopyTradeRecord, TradingWallet, OpenPosition, TakeProfitTier,
} from "@/lib/types";

export default function CopyTradePage() {
  const router = useRouter();
  const [, setUser] = useState<User | null>(null);
  const [config, setConfig] = useState<CopyTradeConfig | null>(null);
  const [wallet, setWallet] = useState<TradingWallet | null>(null);
  const [trades, setTrades] = useState<CopyTradeRecord[]>([]);
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [totalTrades, setTotalTrades] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generatingWallet, setGeneratingWallet] = useState(false);
  const [refreshingBalance, setRefreshingBalance] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [oneTimePrivateKey, setOneTimePrivateKey] = useState<string | null>(null);
  const [privateKeyCopied, setPrivateKeyCopied] = useState(false);

  const [formMaxTradeSol, setFormMaxTradeSol] = useState("0.5");
  const [formMaxDailySol, setFormMaxDailySol] = useState("5.0");
  const [formSlippageBps, setFormSlippageBps] = useState("500");
  const [formMinScore, setFormMinScore] = useState("75");
  const [formMinLiquidity, setFormMinLiquidity] = useState("5000");
  const [formMinMarketCap, setFormMinMarketCap] = useState("10000");
  const [formCooldownSeconds, setFormCooldownSeconds] = useState("60");
  const [formTakeProfitPct, setFormTakeProfitPct] = useState("");
  const [formTakeProfitTiers, setFormTakeProfitTiers] = useState<TakeProfitTier[]>([]);
  const [formStopLossPct, setFormStopLossPct] = useState("");
  const [formMaxRugRisk, setFormMaxRugRisk] = useState("");
  const [formSkipPrintScan, setFormSkipPrintScan] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [configData, walletData, tradesData, positionsData] = await Promise.allSettled([
        apiFetch<CopyTradeConfig>("/api/copy-trade/config"),
        apiFetch<TradingWallet | null>("/api/copy-trade/wallet"),
        apiFetch<{ trades: CopyTradeRecord[]; total: number }>("/api/copy-trade/trades?limit=50"),
        apiFetch<OpenPosition[]>("/api/copy-trade/positions"),
      ]);
      if (configData.status === "fulfilled") {
        const c = configData.value;
        setConfig(c);
        setFormMaxTradeSol(String(c.max_trade_sol));
        setFormMaxDailySol(String(c.max_daily_sol));
        setFormSlippageBps(String(c.slippage_bps));
        setFormMinScore(String(c.min_score));
        setFormMinLiquidity(String(c.min_liquidity));
        setFormMinMarketCap(String(c.min_market_cap));
        setFormCooldownSeconds(String(c.cooldown_seconds));
        setFormTakeProfitPct(c.take_profit_pct ? String(c.take_profit_pct) : "");
        setFormTakeProfitTiers(c.take_profit_tiers ?? []);
        setFormStopLossPct(c.stop_loss_pct ? String(c.stop_loss_pct) : "");
        setFormMaxRugRisk(c.max_rug_risk ? String(c.max_rug_risk) : "");
        setFormSkipPrintScan(c.skip_print_scan);
      }
      if (walletData.status === "fulfilled") setWallet(walletData.value);
      if (tradesData.status === "fulfilled") {
        setTrades(tradesData.value.trades);
        setTotalTrades(tradesData.value.total);
      }
      if (positionsData.status === "fulfilled") setPositions(positionsData.value);
    } catch { /* handled by allSettled */ } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    getMe()
      .then((u) => {
        setUser(u);
        if (u.tier !== "legend") { setError("Copy Trade requires Legend tier"); setLoading(false); return; }
        fetchData();
      })
      .catch(() => router.push("/login"));
  }, [router, fetchData]);

  const handleToggleBot = async () => {
    if (!config) return;
    try {
      const endpoint = config.enabled ? "/api/copy-trade/config/disable" : "/api/copy-trade/config/enable";
      const updated = await apiFetch<CopyTradeConfig>(endpoint, { method: "POST" });
      setConfig(updated);
    } catch (err: unknown) { alert(err instanceof Error ? err.message : "Failed to toggle bot"); }
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        max_trade_sol: parseFloat(formMaxTradeSol), max_daily_sol: parseFloat(formMaxDailySol),
        slippage_bps: parseInt(formSlippageBps), min_score: parseFloat(formMinScore),
        min_liquidity: parseFloat(formMinLiquidity), min_market_cap: parseFloat(formMinMarketCap),
        cooldown_seconds: parseInt(formCooldownSeconds), skip_print_scan: formSkipPrintScan,
        take_profit_pct: formTakeProfitPct ? parseFloat(formTakeProfitPct) : null,
        stop_loss_pct: formStopLossPct ? parseFloat(formStopLossPct) : null,
        max_rug_risk: formMaxRugRisk ? parseFloat(formMaxRugRisk) : null,
        take_profit_tiers: formTakeProfitTiers.length > 0 ? formTakeProfitTiers : null,
      };
      const updated = await apiFetch<CopyTradeConfig>("/api/copy-trade/config", {
        method: "PUT", body: JSON.stringify(body),
      });
      setConfig(updated);
    } catch (err: unknown) { alert(err instanceof Error ? err.message : "Failed to save"); } finally { setSaving(false); }
  };

  const handleGenerateWallet = async () => {
    setGeneratingWallet(true);
    try {
      const w = await apiFetch<TradingWallet & { private_key: string }>("/api/copy-trade/wallet/generate", { method: "POST" });
      setWallet(w);
      setOneTimePrivateKey(w.private_key);
      setPrivateKeyCopied(false);
      const c = await apiFetch<CopyTradeConfig>("/api/copy-trade/config");
      setConfig(c);
    } catch (err: unknown) { alert(err instanceof Error ? err.message : "Failed to generate wallet"); } finally { setGeneratingWallet(false); }
  };

  const handleDismissPrivateKey = () => {
    if (!privateKeyCopied) {
      if (!confirm("You have NOT copied your private key yet. Once dismissed, it can NEVER be shown again. Are you sure?")) return;
    }
    setOneTimePrivateKey(null);
  };

  const handleCopyPrivateKey = () => {
    if (oneTimePrivateKey) {
      navigator.clipboard.writeText(oneTimePrivateKey);
      setPrivateKeyCopied(true);
    }
  };

  const handleRefreshBalance = async () => {
    setRefreshingBalance(true);
    try {
      const w = await apiFetch<TradingWallet>("/api/copy-trade/wallet/refresh-balance", { method: "POST" });
      setWallet(w);
    } catch (err: unknown) { alert(err instanceof Error ? err.message : "Failed"); } finally { setRefreshingBalance(false); }
  };

  const handleManualSell = async (tradeId: number) => {
    if (!confirm("Sell 100% of this position?")) return;
    try {
      await apiFetch(`/api/copy-trade/positions/${tradeId}/sell`, {
        method: "POST", body: JSON.stringify({ sell_pct: 100 }),
      });
      fetchData();
    } catch (err: unknown) { alert(err instanceof Error ? err.message : "Sell failed"); }
  };

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><p className="text-muted-foreground">Loading copy trade...</p></div>;

  if (error) return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Copy Trade</h1>
      <Card className="glass-card border-destructive/30">
        <CardContent className="pt-6">
          <p className="text-destructive">{error}</p>
          <Button variant="outline" className="mt-4" onClick={() => router.push("/dashboard/billing")}>Upgrade to Legend</Button>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Copy Trade</h1>
        <div className="flex items-center gap-3">
          <Badge variant={config?.enabled ? "teal" : "secondary"}>{config?.enabled ? "Active" : "Inactive"}</Badge>
          <Button variant={config?.enabled ? "destructive" : "default"} size="sm" onClick={handleToggleBot} disabled={!config}>
            {config?.enabled ? "Disable Bot" : "Enable Bot"}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="dashboard">
        <TabsList className="w-full">
          <TabsTrigger value="dashboard" className="flex-1">Dashboard</TabsTrigger>
          <TabsTrigger value="settings" className="flex-1">Settings</TabsTrigger>
          <TabsTrigger value="history" className="flex-1">Trade History</TabsTrigger>
          <TabsTrigger value="wallet" className="flex-1">Wallet</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card className="glass-card"><CardContent className="pt-4 pb-4"><p className="text-xs text-muted-foreground">Total Trades</p><p className="text-2xl font-bold">{totalTrades}</p></CardContent></Card>
              <Card className="glass-card"><CardContent className="pt-4 pb-4"><p className="text-xs text-muted-foreground">Open Positions</p><p className="text-2xl font-bold">{positions.length}</p></CardContent></Card>
              <Card className="glass-card"><CardContent className="pt-4 pb-4"><p className="text-xs text-muted-foreground">Wallet Balance</p><p className="text-2xl font-bold">{wallet ? `${wallet.balance_sol.toFixed(4)} SOL` : "--"}</p></CardContent></Card>
              <Card className="glass-card"><CardContent className="pt-4 pb-4"><p className="text-xs text-muted-foreground">Bot Status</p><p className={`text-2xl font-bold ${config?.enabled ? "text-green-400" : "text-muted-foreground"}`}>{config?.enabled ? "Running" : "Stopped"}</p></CardContent></Card>
            </div>

            <Card className="glass-card">
              <CardHeader><CardTitle className="text-lg">Open Positions</CardTitle></CardHeader>
              <CardContent>
                {positions.length === 0 ? <p className="text-sm text-muted-foreground">No open positions</p> : (
                  <Table>
                    <TableHeader><TableRow><TableHead>Token</TableHead><TableHead>Entry SOL</TableHead><TableHead>Tokens</TableHead><TableHead>Entry Price</TableHead><TableHead></TableHead></TableRow></TableHeader>
                    <TableBody>
                      {positions.map((pos) => (
                        <TableRow key={pos.trade_id}>
                          <TableCell className="font-medium">{pos.token_symbol}</TableCell>
                          <TableCell>{pos.entry_sol.toFixed(4)}</TableCell>
                          <TableCell>{pos.token_amount.toLocaleString()}</TableCell>
                          <TableCell>{formatCurrency(pos.entry_price)}</TableCell>
                          <TableCell><Button variant="destructive" size="sm" onClick={() => handleManualSell(pos.trade_id)}>Sell</Button></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card className="glass-card">
              <CardHeader><CardTitle className="text-lg">Recent Trades</CardTitle></CardHeader>
              <CardContent>
                {trades.length === 0 ? <p className="text-sm text-muted-foreground">No trades yet. Enable the bot and wait for callouts.</p> : (
                  <Table>
                    <TableHeader><TableRow><TableHead>Token</TableHead><TableHead>Side</TableHead><TableHead>SOL</TableHead><TableHead>Status</TableHead><TableHead>Time</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {trades.slice(0, 10).map((trade) => (
                        <TableRow key={trade.id}>
                          <TableCell className="font-medium">{trade.token_symbol}</TableCell>
                          <TableCell><Badge variant={trade.side === "buy" ? "teal" : "destructive"}>{trade.side.toUpperCase()}</Badge></TableCell>
                          <TableCell>{trade.sol_amount.toFixed(4)}</TableCell>
                          <TableCell><Badge variant={trade.tx_status === "confirmed" ? "teal" : trade.tx_status === "failed" ? "destructive" : "secondary"}>{trade.tx_status}</Badge></TableCell>
                          <TableCell className="text-xs text-muted-foreground">{new Date(trade.created_at).toLocaleString()}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="settings">
          <Card className="glass-card">
            <CardHeader><CardTitle className="text-lg">Bot Configuration</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wider">Trade Limits</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div><Label htmlFor="maxTradeSol">Max SOL per Trade</Label><Input id="maxTradeSol" type="number" step="0.1" min="0.01" max="10" value={formMaxTradeSol} onChange={(e) => setFormMaxTradeSol(e.target.value)} /></div>
                  <div><Label htmlFor="maxDailySol">Max Daily SOL</Label><Input id="maxDailySol" type="number" step="0.5" min="0.1" max="100" value={formMaxDailySol} onChange={(e) => setFormMaxDailySol(e.target.value)} /></div>
                  <div><Label htmlFor="slippageBps">Slippage (bps)</Label><Input id="slippageBps" type="number" step="50" min="50" max="5000" value={formSlippageBps} onChange={(e) => setFormSlippageBps(e.target.value)} /><p className="text-xs text-muted-foreground mt-1">500 bps = 5%</p></div>
                  <div><Label htmlFor="cooldown">Cooldown (seconds)</Label><Input id="cooldown" type="number" step="10" min="0" max="3600" value={formCooldownSeconds} onChange={(e) => setFormCooldownSeconds(e.target.value)} /></div>
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wider">Safety Filters</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div><Label htmlFor="minScore">Min Score</Label><Input id="minScore" type="number" step="5" min="0" max="100" value={formMinScore} onChange={(e) => setFormMinScore(e.target.value)} /></div>
                  <div><Label htmlFor="maxRugRisk">Max Rug Risk</Label><Input id="maxRugRisk" type="number" step="5" min="0" max="100" value={formMaxRugRisk} onChange={(e) => setFormMaxRugRisk(e.target.value)} placeholder="No limit" /></div>
                  <div><Label htmlFor="minLiquidity">Min Liquidity ($)</Label><Input id="minLiquidity" type="number" step="1000" min="0" value={formMinLiquidity} onChange={(e) => setFormMinLiquidity(e.target.value)} /></div>
                  <div><Label htmlFor="minMarketCap">Min Market Cap ($)</Label><Input id="minMarketCap" type="number" step="5000" min="0" value={formMinMarketCap} onChange={(e) => setFormMinMarketCap(e.target.value)} /></div>
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wider">Auto Exit (Optional)</h3>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="stopLoss">Stop Loss (%)</Label>
                    <Input id="stopLoss" type="number" step="5" min="1" max="100" value={formStopLossPct} onChange={(e) => setFormStopLossPct(e.target.value)} placeholder="Not set" className="max-w-[200px]" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Trailing Take Profit Tiers</Label>
                      <Button
                        type="button" variant="outline" size="sm" className="text-xs h-7"
                        onClick={() => setFormTakeProfitTiers([...formTakeProfitTiers, { gain_pct: 50, sell_pct: 25 }])}
                      >
                        + Add Tier
                      </Button>
                    </div>
                    {formTakeProfitTiers.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No tiers set. Add tiers to automatically sell portions of your position at different profit levels.</p>
                    ) : (
                      <div className="space-y-2">
                        {formTakeProfitTiers.map((tier, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-1">
                                <span className="text-xs text-muted-foreground w-16 shrink-0">Sell</span>
                                <Input
                                  type="number" step="5" min="1" max="100"
                                  value={tier.sell_pct}
                                  onChange={(e) => {
                                    const updated = [...formTakeProfitTiers];
                                    updated[i] = { ...tier, sell_pct: parseFloat(e.target.value) || 0 };
                                    setFormTakeProfitTiers(updated);
                                  }}
                                  className="h-8 w-20 text-xs"
                                />
                                <span className="text-xs text-muted-foreground">% at</span>
                                <Input
                                  type="number" step="10" min="1"
                                  value={tier.gain_pct}
                                  onChange={(e) => {
                                    const updated = [...formTakeProfitTiers];
                                    updated[i] = { ...tier, gain_pct: parseFloat(e.target.value) || 0 };
                                    setFormTakeProfitTiers(updated);
                                  }}
                                  className="h-8 w-24 text-xs"
                                />
                                <span className="text-xs text-muted-foreground">% gain</span>
                              </div>
                            </div>
                            <Button
                              type="button" variant="ghost" size="sm"
                              className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                              onClick={() => setFormTakeProfitTiers(formTakeProfitTiers.filter((_, j) => j !== i))}
                            >
                              x
                            </Button>
                          </div>
                        ))}
                        <p className="text-xs text-muted-foreground">
                          Example: Sell 10% at 20% gain, sell 50% at 100% gain. Percentages are of remaining position.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button type="button" role="switch" aria-checked={formSkipPrintScan} onClick={() => setFormSkipPrintScan(!formSkipPrintScan)}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${formSkipPrintScan ? "bg-primary" : "bg-muted"}`}>
                  <span className={`pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg transition-transform ${formSkipPrintScan ? "translate-x-4" : "translate-x-0"}`} />
                </button>
                <Label>Skip Print Scan tokens</Label>
              </div>
              <Button variant="default" className="w-full" onClick={handleSaveSettings} disabled={saving}>{saving ? "Saving..." : "Save Settings"}</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card className="glass-card">
            <CardHeader><CardTitle className="text-lg">Trade History ({totalTrades} total)</CardTitle></CardHeader>
            <CardContent>
              {trades.length === 0 ? <p className="text-sm text-muted-foreground">No trades yet</p> : (
                <Table>
                  <TableHeader><TableRow><TableHead>Token</TableHead><TableHead>Side</TableHead><TableHead>SOL</TableHead><TableHead>Tokens</TableHead><TableHead>Status</TableHead><TableHead>PnL</TableHead><TableHead>TX</TableHead><TableHead>Time</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {trades.map((trade) => (
                      <TableRow key={trade.id}>
                        <TableCell className="font-medium">{trade.token_symbol}</TableCell>
                        <TableCell><Badge variant={trade.side === "buy" ? "teal" : "destructive"}>{trade.side.toUpperCase()}</Badge></TableCell>
                        <TableCell>{trade.sol_amount.toFixed(4)}</TableCell>
                        <TableCell>{trade.token_amount.toLocaleString()}</TableCell>
                        <TableCell><Badge variant={trade.tx_status === "confirmed" ? "teal" : trade.tx_status === "failed" ? "destructive" : "secondary"}>{trade.tx_status}</Badge></TableCell>
                        <TableCell>{trade.pnl_sol !== null ? <span className={trade.pnl_sol >= 0 ? "text-green-400" : "text-red-400"}>{trade.pnl_sol >= 0 ? "+" : ""}{trade.pnl_sol.toFixed(4)} SOL</span> : "--"}</TableCell>
                        <TableCell>{trade.tx_signature ? <a href={`https://solscan.io/tx/${trade.tx_signature}`} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-xs">{formatAddress(trade.tx_signature, 4)}</a> : "--"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{new Date(trade.created_at).toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="wallet">
          <div className="space-y-4">
            {!wallet ? (
              <Card className="glass-card">
                <CardHeader><CardTitle className="text-lg">Trading Wallet</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">Generate a dedicated trading wallet for the copy trade bot. This wallet is separate from your personal wallet.</p>
                  <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4">
                    <p className="text-sm text-yellow-400">After generating, fund this wallet with SOL to start trading. The private key is encrypted and stored securely.</p>
                  </div>
                  <Button variant="default" className="w-full" onClick={handleGenerateWallet} disabled={generatingWallet}>{generatingWallet ? "Generating..." : "Generate Trading Wallet"}</Button>
                </CardContent>
              </Card>
            ) : (
              <Card className="glass-card">
                <CardHeader><CardTitle className="text-lg">Trading Wallet</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><p className="text-xs text-muted-foreground">Public Key</p><p className="text-sm font-mono break-all">{wallet.public_key}</p></div>
                    <div>
                      <p className="text-xs text-muted-foreground">Balance</p>
                      <p className="text-2xl font-bold">{wallet.balance_sol.toFixed(4)} SOL</p>
                      {wallet.balance_updated_at && <p className="text-xs text-muted-foreground">Updated: {new Date(wallet.balance_updated_at).toLocaleString()}</p>}
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <Button variant="outline" onClick={handleRefreshBalance} disabled={refreshingBalance}>{refreshingBalance ? "Refreshing..." : "Refresh Balance"}</Button>
                    <Button variant="outline" onClick={() => navigator.clipboard.writeText(wallet.public_key)}>Copy Address</Button>
                    <a href={`https://solscan.io/account/${wallet.public_key}`} target="_blank" rel="noopener noreferrer"><Button variant="outline">View on Solscan</Button></a>
                  </div>
                  <div className="rounded-lg border border-border/50 bg-card/50 p-4">
                    <p className="text-sm text-muted-foreground">Send SOL to the address above to fund your trading wallet.</p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* One-time private key modal */}
      {oneTimePrivateKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-lg rounded-xl border border-red-500/40 bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-red-500/20 flex items-center justify-center shrink-0">
                <span className="text-red-400 text-lg font-bold">!</span>
              </div>
              <h2 className="text-lg font-bold text-red-400">Export Your Private Key Now</h2>
            </div>

            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 space-y-2">
              <p className="text-sm font-semibold text-red-400">This is the ONLY time your private key will be shown.</p>
              <p className="text-sm text-red-300/80">Copy and store it safely immediately. Import it into Phantom, Solflare, or another Solana wallet as a backup. Once you close this dialog, the private key cannot be retrieved again.</p>
            </div>

            <div className="space-y-2">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Private Key</p>
              <div className="relative">
                <code className="block w-full rounded-lg border border-border/50 bg-background/80 p-3 text-xs font-mono break-all select-all leading-relaxed">
                  {oneTimePrivateKey}
                </code>
              </div>
            </div>

            <div className="flex gap-3">
              <Button
                variant="default"
                className="flex-1"
                onClick={handleCopyPrivateKey}
              >
                {privateKeyCopied ? "Copied!" : "Copy Private Key"}
              </Button>
              <Button
                variant={privateKeyCopied ? "outline" : "destructive"}
                className="flex-1"
                onClick={handleDismissPrivateKey}
              >
                {privateKeyCopied ? "Done" : "Close Without Copying"}
              </Button>
            </div>

            {privateKeyCopied && (
              <p className="text-xs text-green-400 text-center">Private key copied to clipboard. Store it somewhere safe before closing.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
