import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { TradingLinks } from "@/components/trading-links";
import { formatCurrency, formatAddress, formatPercent } from "@/lib/utils";

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
}: CalloutCardProps) {
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

  // Confidence score bar width
  const scoreWidth = Math.min(Math.max(score, 0), 100);

  // Gradient score bar color
  const scoreBarClass =
    score >= 65
      ? "bg-gradient-to-r from-teal to-green-500"
      : score >= 45
        ? "bg-gradient-to-r from-yellow-500 to-amber-500"
        : "bg-gradient-to-r from-red-500 to-red-400";

  return (
    <Card className="glass-card card-hover">
      <CardContent className="pt-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="font-bold text-lg" title={tokenAddress}>{tokenSymbol}</span>
            <Badge className={signalColor}>{signal.toUpperCase()}</Badge>
            {scanSource === "print_scan" && (
              <Badge className="text-[10px] px-1 py-0 bg-purple-500/10 text-purple-400 border-purple-500/20">
                PRINT
              </Badge>
            )}
          </div>
          <span className="text-xs text-muted-foreground">{timeAgo}</span>
        </div>

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

        <p className="text-sm text-muted-foreground mb-2">{reason}</p>

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

        {/* Quick Trade */}
        <div className="mt-2 pt-2 border-t border-border/30 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Quick Trade</span>
          <TradingLinks tokenAddress={tokenAddress} variant="compact" />
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
