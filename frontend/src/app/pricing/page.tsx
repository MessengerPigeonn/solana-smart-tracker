import { PricingCard } from "@/components/pricing-card";

export default function PricingPage() {
  return (
    <div className="container mx-auto px-4 py-16">
      <h1 className="text-4xl font-bold text-center mb-4">
        <span className="text-gradient">Pricing</span>
      </h1>
      <p className="text-muted-foreground text-center mb-12 max-w-lg mx-auto">
        Choose the plan that fits your trading style. Pay with card or SOL.
        Upgrade or cancel anytime.
      </p>
      <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
        <PricingCard
          name="Free"
          price="$0"
          period=""
          features={[
            "10 tokens in scanner",
            "Last 5 callouts (5min delay)",
            "No wallet tracking",
            "No smart money overlaps",
          ]}
          cta="Get Started"
          href="/signup"
        />
        <PricingCard
          name="Pro"
          price="1 SOL"
          period="/month"
          features={[
            "Unlimited token scanner",
            "Real-time callout feed + SSE",
            "Track 10 wallets",
            "Basic PnL analytics",
            "Smart money overlaps",
          ]}
          cta="Subscribe"
          href="/dashboard/billing?plan=pro"
          highlighted
        />
        <PricingCard
          name="Legend"
          price="5 SOL"
          period="/month"
          features={[
            "Everything in Pro",
            "Track 50 wallets",
            "Full trade history + patterns",
            "Top smart wallets list",
            "Priority support",
          ]}
          cta="Subscribe"
          href="/dashboard/billing?plan=legend"
        />
      </div>
    </div>
  );
}
