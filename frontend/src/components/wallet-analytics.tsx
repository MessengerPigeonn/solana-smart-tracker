"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency, formatAddress } from "@/lib/utils";

interface Trade {
  token_address: string;
  token_symbol: string;
  volume_buy: number;
  volume_sell: number;
  estimated_pnl: number;
  scanned_at: string;
}

interface WalletAnalyticsData {
  wallet_address: string;
  total_pnl: number;
  trade_count: number;
  win_rate: number;
  recent_trades: Trade[];
  tokens_traded: number;
}

interface WalletAnalyticsProps {
  data: WalletAnalyticsData;
}

export function WalletAnalyticsView({ data }: WalletAnalyticsProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold font-mono">
          {formatAddress(data.wallet_address, 8)}
        </h2>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="glass-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Total PnL
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p
              className={`text-xl font-bold ${
                data.total_pnl >= 0 ? "text-green-500" : "text-red-500"
              }`}
            >
              {formatCurrency(Math.abs(data.total_pnl))}
              {data.total_pnl < 0 ? " loss" : ""}
            </p>
          </CardContent>
        </Card>
        <Card className="glass-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Win Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold">{data.win_rate}%</p>
          </CardContent>
        </Card>
        <Card className="glass-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Trades
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold">{data.trade_count}</p>
          </CardContent>
        </Card>
        <Card className="glass-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl font-bold">{data.tokens_traded}</p>
          </CardContent>
        </Card>
      </div>

      {/* Recent trades */}
      <Card className="glass-card">
        <CardHeader>
          <CardTitle>Recent Trades</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border border-border/50 overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Token</TableHead>
                  <TableHead>Buy Vol</TableHead>
                  <TableHead>Sell Vol</TableHead>
                  <TableHead>PnL</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recent_trades.map((trade, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">
                      {trade.token_symbol}
                    </TableCell>
                    <TableCell>{formatCurrency(trade.volume_buy)}</TableCell>
                    <TableCell>{formatCurrency(trade.volume_sell)}</TableCell>
                    <TableCell>
                      <span
                        className={
                          trade.estimated_pnl >= 0
                            ? "text-green-500"
                            : "text-red-500"
                        }
                      >
                        {formatCurrency(Math.abs(trade.estimated_pnl))}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(trade.scanned_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
