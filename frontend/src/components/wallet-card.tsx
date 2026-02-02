import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatAddress } from "@/lib/utils";

interface WalletCardProps {
  id: number;
  walletAddress: string;
  label: string;
  onRemove: (id: number) => void;
  onViewAnalytics: (address: string) => void;
}

export function WalletCard({
  id,
  walletAddress,
  label,
  onRemove,
  onViewAnalytics,
}: WalletCardProps) {
  return (
    <Card className="glass-card">
      <CardContent className="pt-4 flex items-center justify-between">
        <div>
          <p className="font-medium">{label}</p>
          <p className="text-sm text-muted-foreground font-mono">
            {formatAddress(walletAddress, 8)}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="hover:border-primary/50"
            onClick={() => onViewAnalytics(walletAddress)}
          >
            Analytics
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive"
            onClick={() => onRemove(id)}
          >
            Remove
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
