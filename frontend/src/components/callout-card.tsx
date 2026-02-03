"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { TradingLinks } from "@/components/trading-links";
import { formatCurrency, formatAddress, formatPercent, formatNumber } from "@/lib/utils";
import { Copy, Check, ExternalLink, AlertTriangle } from "lucide-react";

interface CalloutCardProps {
  tokenSymbol: string;
  tokenAddress: string;
  signal: string;
  score: number;
  reason: string;
  smartWallets: string[];
  priceAtCallout: number;
  currentPrice?: number;
  scanSource?: string;
  createdAt: string;
  tokenName?: string | null;
  marketCap?: number | null;
  volume24h?: number | null;
  liquidity?: number | null;
  holderCount?: number | null;
  rugRiskScore?: number | null;
  dexscreenerUrl?: string;
  currentMarketCap?: number;
  peakMarketCap?: number | null;
}

export function CalloutCard({
  tokenSymbol,
  tokenAddress,
  signal,
  score,
  reason,
  smartWallets,
  priceAtCallout,
  currentPrice,
  scanSource,
  createdAt,
  tokenName,
  marketCap,
  volume24h,
  liquidity,
  holderCount,
  rugRiskScore,
  dexscreenerUrl,
  currentMarketCap,
  peakMarketCap,
}: CalloutCardProps) {
  const [copied, setCopied] = useState(false);

  const signalColor =
    signal === "buy"
      ? "bg-green-500/10 text-green-500 border-green-500/20"
      : signal === "sell"
        ? "bg-red-500/10 text-red-500 border-red-500/20"
        : "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";

  const timeAgo = getTimeAgo(createdAt);
  const isOldEnough = getMinutesSince(createdAt) >= 5;

  // Performance tracking: price change since callout
  let priceDeltaPct: number | null = null;
  if (currentPrice && priceAtCallout > 0 && isOldEnough) {
    priceDeltaPct = ((currentPrice - priceAtCallout) / priceAtCallout) * 100;
  }

  // Multiplier: current mcap / mcap at callout
  let multiplier: number | null = null;
  if (isOldEnough && marketCap && marketCap > 0 && currentMarketCap && currentMarketCap > 0) {
    multiplier = currentMarketCap / marketCap;
  }

  // ATH multiplier: peak mcap / mcap at callout
  let athMultiplier: number | null = null;
  if (marketCap && marketCap > 0 && peakMarketCap && peakMarketCap > 0) {
    athMultiplier = peakMarketCap / marketCap;
  }

  // Confidence score bar width
  const scoreWidth = Math.min(Math.max(score, 0), 100);

  // Gradient score bar color (updated thresholds: 75/55)
  const scoreBarClass =
    score >= 75
      ? "bg-gradient-to-r from-teal to-green-500"
      : score >= 55
        ? "bg-gradient-to-r from-yellow-500 to-amber-500"
        : "bg-gradient-to-r from-red-500 to-red-400";

  const dexUrl = dexscreenerUrl || `https://dexscreener.com/solana/${tokenAddress}`;

  function handleCopy() {
    navigator.clipboard.writeText(tokenAddress);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card className="glass-card card-hover">
      <CardContent className="pt-4">
        {/* Header: symbol + name, signal badge, PRINT badge, time */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="font-bold text-lg">{tokenSymbol}</span>
            {tokenName && (
              <span className="text-sm text-muted-foreground truncate max-w-[120px]">
                {tokenName}
              </span>
            )}
            <Badge className={signalColor}>{signal.toUpperCase()}</Badge>
            {scanSource === "print_scan" && (
              <Badge className="text-[10px] px-1 py-0 bg-purple-500/10 text-purple-400 border-purple-500/20">
                PRINT
              </Badge>
            )}
          </div>
          <span className="text-xs text-muted-foreground">{timeAgo}</span>
        </div>

        {/* Contract address row */}
        <div className="flex items-center gap-2 mb-2">
          <code className="text-xs text-muted-foreground font-mono">
            {formatAddress(tokenAddress, 6)}
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
            title="View on DexScreener"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>

        {/* Multiplier badges */}
        {(multiplier !== null || athMultiplier !== null) && (
          <div className="flex items-center gap-3 mb-2">
            {multiplier !== null && (
              <div>
                <span
                  className={`inline-block text-sm font-bold px-2 py-0.5 rounded ${
                    multiplier >= 1
                      ? "bg-green-500/10 text-green-500"
                      : "bg-red-500/10 text-red-500"
                  }`}
                >
                  {multiplier.toFixed(1)}x
                </span>
                <span className="text-xs text-muted-foreground ml-1">now</span>
              </div>
            )}
            {athMultiplier !== null && athMultiplier > 1 && (
              <div>
                <span className="inline-block text-sm font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400">
                  {athMultiplier.toFixed(1)}x
                </span>
                <span className="text-xs text-muted-foreground ml-1">ATH</span>
              </div>
            )}
          </div>
        )}

        {/* Stats row: MCap, Vol 24h, Liquidity, Holders */}
        {(marketCap || volume24h || liquidity || holderCount) && (
          <div className="grid grid-cols-4 gap-2 mb-2 text-center">
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">MCap</p>
              <p className="text-xs font-medium">
                {marketCap ? formatCurrency(marketCap) : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Vol 24h</p>
              <p className="text-xs font-medium">
                {volume24h ? formatCurrency(volume24h) : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Liquidity</p>
              <p className="text-xs font-medium">
                {liquidity ? formatCurrency(liquidity) : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground uppercase">Holders</p>
              <p className="text-xs font-medium">
                {holderCount ? formatNumber(holderCount) : "—"}
              </p>
            </div>
          </div>
        )}

        {/* Confidence score bar */}
        <div className="mb-2">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-muted-foreground">Confidence</span>
            <span className="font-medium">{score}/100</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${scoreBarClass}`}
              style={{ width: `${scoreWidth}%` }}
            />
          </div>
        </div>

        {/* Reason text */}
        <p className="text-sm text-muted-foreground mb-2">{reason}</p>

        {/* Rug risk indicator (print_scan tokens with rugRiskScore > 30) */}
        {scanSource === "print_scan" && rugRiskScore != null && rugRiskScore > 30 && (
          <div className="flex items-center gap-1.5 mb-2">
            <AlertTriangle
              className={`h-4 w-4 ${
                rugRiskScore > 70
                  ? "text-red-500"
                  : rugRiskScore > 50
                    ? "text-yellow-500"
                    : "text-yellow-400"
              }`}
            />
            <span
              className={`text-xs font-medium ${
                rugRiskScore > 70
                  ? "text-red-500"
                  : rugRiskScore > 50
                    ? "text-yellow-500"
                    : "text-yellow-400"
              }`}
            >
              Rug Risk: {rugRiskScore.toFixed(0)}%
            </span>
          </div>
        )}

        {/* Price row */}
        <div className="flex items-center justify-between text-sm">
          <span>
            Entry: <span className="font-mono">{formatCurrency(priceAtCallout)}</span>
          </span>
          {priceDeltaPct !== null && (
            <span className={priceDeltaPct >= 0 ? "text-green-500 font-medium" : "text-red-500 font-medium"}>
              {formatPercent(priceDeltaPct)} since callout
            </span>
          )}
        </div>

        {currentPrice && isOldEnough && (
          <div className="text-sm mt-1">
            <span className="text-muted-foreground">Now: </span>
            <span className="font-mono">{formatCurrency(currentPrice)}</span>
          </div>
        )}

        {/* Action row: Quick Trade + DexScreener link */}
        <div className="mt-2 pt-2 border-t border-border/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">Quick Trade</span>
            <TradingLinks tokenAddress={tokenAddress} variant="compact" />
          </div>
          <a
            href={dexUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
          >
            DexScreener
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        {/* Smart wallet badges */}
        {smartWallets.length > 0 && (
          <div className="mt-2">
            <p className="text-xs text-muted-foreground mb-1">
              {smartWallets.length} smart wallet{smartWallets.length !== 1 ? "s" : ""} triggered this signal
            </p>
            <div className="flex flex-wrap gap-1">
              {smartWallets.slice(0, 3).map((w) => (
                <Badge key={w} variant="outline" className="text-xs font-mono">
                  {formatAddress(w)}
                </Badge>
              ))}
              {smartWallets.length > 3 && (
                <Badge variant="outline" className="text-xs">
                  +{smartWallets.length - 3} more
                </Badge>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function getTimeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function getMinutesSince(dateStr: string): number {
  const now = new Date();
  const date = new Date(dateStr);
  return (now.getTime() - date.getTime()) / (1000 * 60);
}
