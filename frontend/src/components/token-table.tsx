"use client";

import { Fragment, useState, useCallback } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { TradingLinks } from "@/components/trading-links";
import { formatCurrency, formatAddress, formatPercent } from "@/lib/utils";
import { Copy, Check, ExternalLink } from "lucide-react";

export interface Token {
  address: string;
  symbol: string;
  name: string;
  price: number;
  volume_24h: number;
  liquidity: number;
  market_cap: number;
  price_change_5m: number;
  price_change_1h: number;
  price_change_24h: number;
  smart_money_count: number;
  token_type?: string;
  created_at_chain?: string | null;
  buy_count_24h?: number;
  sell_count_24h?: number;
  unique_wallets_24h?: number;
  top_buyer_concentration?: number;
  has_buy_signal?: boolean;
  has_mint_authority?: boolean | null;
  has_freeze_authority?: boolean | null;
  is_mutable?: boolean | null;
  holder_count?: number;
  top10_holder_pct?: number;
  dev_wallet_pct?: number;
  dev_sold?: boolean | null;
  scan_source?: string;
  rug_risk_score?: number;
}

interface TokenTableProps {
  tokens: Token[];
  onSort: (column: string) => void;
  sortBy: string;
  sortOrder: string;
}

function PriceChange({ value }: { value: number }) {
  if (value === 0) {
    return <span className="text-muted-foreground">0.00%</span>;
  }
  return (
    <span className={value > 0 ? "text-green-500 font-medium" : "text-red-500 font-medium"}>
      {formatPercent(value)}
    </span>
  );
}

function RiskDot({ score }: { score?: number }) {
  if (score === undefined || score === 0) return <span className="text-muted-foreground">-</span>;
  const color = score < 25 ? "bg-green-500" : score <= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
      <span className="text-xs">{score.toFixed(0)}</span>
    </div>
  );
}

function TokenAge({ createdAt }: { createdAt?: string | null }) {
  if (!createdAt) return <span className="text-muted-foreground">-</span>;
  const now = new Date();
  const created = new Date(createdAt);
  const hours = Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60));
  if (hours < 1) return <span className="text-green-400 font-medium">&lt;1h</span>;
  if (hours < 6) return <span className="text-green-500">{hours}h</span>;
  if (hours < 24) return <span className="text-yellow-500">{hours}h</span>;
  const days = Math.floor(hours / 24);
  return <span className="text-muted-foreground">{days}d</span>;
}

function TokenRow({ token, isExpanded, onToggle }: {
  token: Token;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const buys = token.buy_count_24h || 0;
  const sells = token.sell_count_24h || 0;
  const dexUrl = `https://dexscreener.com/solana/${token.address}`;

  const handleCopy = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(token.address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [token.address]);

  return (
    <TableRow
      className={`cursor-pointer hover:bg-primary/5 transition-colors ${
        token.has_buy_signal ? "bg-green-500/5 border-l-2 border-l-green-500" : ""
      } ${isExpanded ? "bg-accent/20" : ""}`}
      onClick={onToggle}
    >
      <TableCell>
        <div>
          <div className="flex items-center gap-1.5">
            <p className="font-medium">{token.symbol}</p>
            {token.token_type === "memecoin" && (
              <Badge variant="outline" className="text-[10px] px-1 py-0">
                meme
              </Badge>
            )}
            {token.scan_source === "print_scan" && (
              <Badge className="text-[10px] px-1 py-0 bg-purple-500/10 text-purple-400 border-purple-500/20">
                PRINT
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <code className="text-xs text-muted-foreground font-mono" title={token.address}>
              {formatAddress(token.address, 4)}
            </code>
            <button
              onClick={handleCopy}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={`Copy ${token.address}`}
            >
              {copied ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <Copy className="h-3 w-3" />
              )}
            </button>
            <a
              href={dexUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={`DexScreener: ${token.address}`}
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      </TableCell>
      <TableCell className="font-mono">
        {formatCurrency(token.price)}
      </TableCell>
      <TableCell>
        <PriceChange value={token.price_change_5m} />
      </TableCell>
      <TableCell>
        <PriceChange value={token.price_change_1h} />
      </TableCell>
      <TableCell>
        <PriceChange value={token.price_change_24h} />
      </TableCell>
      <TableCell>{formatCurrency(token.volume_24h)}</TableCell>
      <TableCell>{formatCurrency(token.liquidity)}</TableCell>
      <TableCell>{formatCurrency(token.market_cap)}</TableCell>
      <TableCell>
        <span className="text-green-500">{buys}</span>
        <span className="text-muted-foreground">/</span>
        <span className="text-red-500">{sells}</span>
      </TableCell>
      <TableCell>
        <span className="font-medium text-primary">
          {token.smart_money_count}
        </span>
      </TableCell>
      <TableCell>
        <RiskDot score={token.rug_risk_score} />
      </TableCell>
      <TableCell>
        <TokenAge createdAt={token.created_at_chain} />
      </TableCell>
      <TableCell>
        <TradingLinks tokenAddress={token.address} variant="icon-only" />
      </TableCell>
    </TableRow>
  );
}

function ExpandedRow({ token }: { token: Token }) {
  const [copied, setCopied] = useState(false);
  const buys = token.buy_count_24h || 0;
  const sells = token.sell_count_24h || 0;
  const total = buys + sells;
  const buyPct = total > 0 ? ((buys / total) * 100).toFixed(0) : "0";
  const isPrintScan = token.scan_source === "print_scan";
  const dexUrl = `https://dexscreener.com/solana/${token.address}`;

  const handleCopy = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(token.address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [token.address]);

  return (
    <TableRow className="bg-accent/30">
      <TableCell colSpan={14} className="py-3">
        {/* Token name + address row */}
        <div className="flex items-center gap-3 mb-3 pb-3 border-b border-border/50">
          <div>
            <span className="font-medium">{token.symbol}</span>
            {token.name && token.name !== token.symbol && (
              <span className="text-sm text-muted-foreground ml-2">{token.name}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <code className="text-xs text-muted-foreground font-mono" title={token.address}>
              {formatAddress(token.address, 6)}
            </code>
            <button
              onClick={handleCopy}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={`Copy ${token.address}`}
            >
              {copied ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <Copy className="h-3 w-3" />
              )}
            </button>
            <a
              href={dexUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={`DexScreener: ${token.address}`}
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Type</p>
            <p className="font-medium capitalize">{token.token_type || "unknown"}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Buy/Sell Ratio</p>
            <p className="font-medium">
              <span className="text-green-500">{buys}</span>
              {" / "}
              <span className="text-red-500">{sells}</span>
              <span className="text-muted-foreground ml-1">({buyPct}% buy)</span>
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Top 5 Buyer Concentration</p>
            <p className="font-medium">{(token.top_buyer_concentration || 0).toFixed(1)}%</p>
          </div>
          <div>
            <p className="text-muted-foreground">Unique Wallets (24h)</p>
            <p className="font-medium">{token.unique_wallets_24h || 0}</p>
          </div>
        </div>
        {isPrintScan && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-3 pt-3 border-t border-border/50">
            <div>
              <p className="text-muted-foreground">Rug Risk Score</p>
              <p className="font-medium">{(token.rug_risk_score || 0).toFixed(0)}/100</p>
            </div>
            <div>
              <p className="text-muted-foreground">Top 10 Holders</p>
              <p className="font-medium">{(token.top10_holder_pct || 0).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-muted-foreground">Dev Wallet</p>
              <p className="font-medium">
                {(token.dev_wallet_pct || 0).toFixed(1)}%
                {token.dev_sold === true && <span className="text-green-500 ml-1">(sold)</span>}
                {token.dev_sold === false && <span className="text-yellow-500 ml-1">(holding)</span>}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Authority</p>
              <p className="font-medium">
                {token.has_mint_authority && <span className="text-red-500 mr-2">Mint</span>}
                {token.has_freeze_authority && <span className="text-red-500 mr-2">Freeze</span>}
                {token.is_mutable && <span className="text-yellow-500">Mutable</span>}
                {!token.has_mint_authority && !token.has_freeze_authority && !token.is_mutable && (
                  <span className="text-green-500">Safe</span>
                )}
              </p>
            </div>
          </div>
        )}
        <div className="mt-3 pt-3 border-t border-border/50 flex items-center justify-between">
          <TradingLinks tokenAddress={token.address} variant="expanded" />
          <a
            href={dexUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            DexScreener
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </TableCell>
    </TableRow>
  );
}

export function TokenTable({ tokens, onSort, sortBy, sortOrder }: TokenTableProps) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  function SortableHeader({ column, children }: { column: string; children: React.ReactNode }) {
    const isActive = sortBy === column;
    return (
      <TableHead
        className="cursor-pointer hover:text-foreground select-none whitespace-nowrap"
        onClick={() => onSort(column)}
      >
        {children}{" "}
        {isActive ? (
          <span className="text-primary">{sortOrder === "desc" ? "↓" : "↑"}</span>
        ) : (
          ""
        )}
      </TableHead>
    );
  }

  return (
    <Card className="glass-card overflow-hidden">
      <div className="overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Token</TableHead>
              <TableHead>Price</TableHead>
              <SortableHeader column="price_change_5m">5m</SortableHeader>
              <SortableHeader column="price_change_1h">1h</SortableHeader>
              <SortableHeader column="price_change_24h">24h</SortableHeader>
              <SortableHeader column="volume_24h">Volume</SortableHeader>
              <SortableHeader column="liquidity">Liq</SortableHeader>
              <SortableHeader column="market_cap">MCap</SortableHeader>
              <TableHead>Buys/Sells</TableHead>
              <SortableHeader column="smart_money_count">Smart $</SortableHeader>
              <SortableHeader column="rug_risk_score">Risk</SortableHeader>
              <TableHead>Age</TableHead>
              <TableHead>Trade</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tokens.length === 0 ? (
              <TableRow>
                <TableCell colSpan={14} className="text-center text-muted-foreground py-8">
                  No tokens found
                </TableCell>
              </TableRow>
            ) : (
              tokens.map((token) => (
                <Fragment key={token.address}>
                  <TokenRow
                    token={token}
                    isExpanded={expandedRow === token.address}
                    onToggle={() => setExpandedRow(
                      expandedRow === token.address ? null : token.address
                    )}
                  />
                  {expandedRow === token.address && (
                    <ExpandedRow token={token} />
                  )}
                </Fragment>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
