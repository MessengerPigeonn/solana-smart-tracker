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

interface PricingCardProps {
  name: string;
  price: string;
  period: string;
  features: string[];
  cta: string;
  href: string;
  highlighted?: boolean;
}

export function PricingCard({
  name,
  price,
  period,
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
      </CardHeader>
      <CardContent className="flex-1">
        <ul className="space-y-2 text-sm">
          {features.map((feature) => (
            <li key={feature} className="flex items-start gap-2">
              <span className="text-primary mt-0.5">&#10003;</span>
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
