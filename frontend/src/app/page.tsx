import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PricingCard } from "@/components/pricing-card";

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border/30">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "radial-gradient(ellipse at 50% 0%, rgba(36,219,201,0.08) 0%, transparent 70%)",
          }}
        />
        <div className="container mx-auto px-4 py-24 md:py-32 text-center relative z-10">
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-6">
            Track <span className="text-gradient">Smart Money</span> on Solana
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-8">
            Real-time whale wallet tracking, automated buy/sell callouts, and
            smart money overlap detection for Solana memecoins.
          </p>
          <div className="flex gap-4 justify-center">
            <Button size="lg" variant="gradient" className="animate-pulse-glow" asChild>
              <Link href="/signup">Start Free</Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link href="/pricing">View Pricing</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="container mx-auto px-4 py-20">
        <h2 className="text-3xl font-bold text-center mb-12">
          Everything you need to follow the whales
        </h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-lg">Token Scanner</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground">
              Real-time scanning of trending Solana tokens with volume, liquidity,
              and smart money metrics.
            </CardContent>
          </Card>
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-lg">Smart Callouts</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground">
              Automated BUY/SELL/WATCH signals scored 0-100 based on whale wallet
              activity and volume spikes.
            </CardContent>
          </Card>
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-lg">Wallet Tracker</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground">
              Track up to 50 whale wallets with full PnL analytics, trade history,
              and behavioral patterns.
            </CardContent>
          </Card>
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-lg">Overlap Detection</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground">
              Find wallets trading across multiple tokens — the strongest signal
              for coordinated smart money moves.
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Pricing */}
      <section className="border-t border-border/30 bg-muted/30">
        <div className="container mx-auto px-4 py-20">
          <h2 className="text-3xl font-bold text-center mb-4">
            Simple pricing
          </h2>
          <p className="text-muted-foreground text-center mb-12">
            Pay with card or SOL. Cancel anytime.
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
              href="/signup"
              highlighted
            />
            <PricingCard
              name="Legend"
              price="5 SOL"
              period="/month"
              features={[
                "Everything in Pro",
                "Track 50 wallets",
                "Full history + patterns",
                "Top smart wallets list",
                "Priority support",
              ]}
              cta="Subscribe"
              href="/signup"
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/30 py-8">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          SolTracker &mdash; Smart money analysis for Solana memecoins.
        </div>
      </footer>
    </div>
  );
}
