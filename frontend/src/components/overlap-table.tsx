"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatAddress } from "@/lib/utils";

interface OverlapEntry {
  wallet: string;
  tokens: string[];
  total_pnl: number;
  overlap_count: number;
}

interface OverlapTableProps {
  overlaps: OverlapEntry[];
}

export function OverlapTable({ overlaps }: OverlapTableProps) {
  return (
    <div className="rounded-md border overflow-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Wallet</TableHead>
            <TableHead>Overlap Count</TableHead>
            <TableHead>Tokens</TableHead>
            <TableHead>Total PnL</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {overlaps.length === 0 ? (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                No overlaps found. Try lowering the threshold or adding more tokens.
              </TableCell>
            </TableRow>
          ) : (
            overlaps.map((o) => (
              <TableRow key={o.wallet}>
                <TableCell className="font-mono">
                  {formatAddress(o.wallet, 6)}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{o.overlap_count}</Badge>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {o.tokens.slice(0, 5).map((t) => (
                      <Badge key={t} variant="outline" className="text-xs font-mono">
                        {formatAddress(t, 4)}
                      </Badge>
                    ))}
                    {o.tokens.length > 5 && (
                      <Badge variant="outline" className="text-xs">
                        +{o.tokens.length - 5}
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <span
                    className={
                      o.total_pnl >= 0 ? "text-green-500" : "text-red-500"
                    }
                  >
                    {formatCurrency(Math.abs(o.total_pnl))}
                  </span>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
