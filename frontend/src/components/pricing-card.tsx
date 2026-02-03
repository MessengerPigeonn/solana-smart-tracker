import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface PricingCardProps {
  name: string;
  price: string;
  period: string;
  subtitle?: string;
  features: string[];
  cta: string;
  href: string;
  highlighted?: boolean;
}

export function PricingCard({
  name,
  price,
  period,
  subtitle,
  features,
  cta,
  href,
  highlighted = false,
}: PricingCardProps) {
  return (
    <Card
      className={cn(
        "flex flex-col glass-card",
        highlighted && "border-primary/50 glow-primary-sm"
      )}
    >
      <CardHeader>
        <CardTitle>{name}</CardTitle>
        <div className="mt-2">
          <span className="text-3xl font-bold">{price}</span>
          {period && (
            <span className="text-muted-foreground text-sm">{period}</span>
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
        )}
      </CardHeader>
      <CardContent className="flex-1">
        <ul className="space-y-2 text-sm">
          {features.map((feature) => (
            <li key={feature} className="flex items-start gap-2">
              <Check className="h-4 w-4 text-primary mt-0.5 shrink-0" />
              <span>{feature}</span>
            </li>
          ))}
        </ul>
      </CardContent>
      <CardFooter>
        <Button
          className="w-full"
          variant={highlighted ? "gradient" : "outline"}
          asChild
        >
          <Link href={href}>{cta}</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
