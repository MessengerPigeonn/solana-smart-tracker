import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PricingCard } from "@/components/pricing-card";
import {
  Radar,
  Bell,
  Wallet,
  GitMerge,
  ArrowRight,
  ShieldCheck,
  Zap,
  BarChart3,
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border/30">
        <div className="absolute inset-0 pointer-events-none">
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse at 30% 0%, rgba(36,219,201,0.12) 0%, transparent 50%)",
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse at 70% 100%, rgba(61,214,245,0.08) 0%, transparent 50%)",
            }}
          />
        </div>
        <div className="container mx-auto px-4 py-28 md:py-36 text-center relative z-10">
          <Badge
            variant="outline"
            className="mb-6 px-4 py-1 text-xs animate-fade-in"
          >
            <Zap className="h-3 w-3 mr-1 text-primary" />
            Now tracking 500+ Solana memecoins in real-time
          </Badge>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight mb-6 animate-slide-up">
            Track <span className="text-gradient">Smart Money</span>
            <br />
            on Solana
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-3 animate-slide-up">
            Real-time whale wallet tracking, automated buy/sell callouts, and
            smart money overlap detection for Solana memecoins.
          </p>
          <p className="text-sm text-muted-foreground/70 mb-8 animate-fade-in">
            Built by a trader, for traders.
          </p>
          <div className="flex gap-4 justify-center animate-slide-up">
            <Button size="lg" variant="gradient" className="glow-primary gap-2" asChild>
              <Link href="/signup">
                Start Free
                <ArrowRight className="h-4 w-4" />
              </Link>
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
          {[
            {
              icon: Radar,
              title: "Token Scanner",
              desc: "Real-time scanning of trending Solana tokens with volume, liquidity, and smart money metrics.",
            },
            {
              icon: Bell,
              title: "Smart Callouts",
              desc: "Automated BUY/SELL/WATCH signals scored 0-100 based on whale wallet activity and volume spikes.",
            },
            {
              icon: Wallet,
              title: "Wallet Tracker",
              desc: "Track up to 50 whale wallets with full PnL analytics, trade history, and behavioral patterns.",
            },
            {
              icon: GitMerge,
              title: "Overlap Detection",
              desc: "Find wallets trading across multiple tokens — the strongest signal for coordinated smart money moves.",
            },
          ].map((feature) => (
            <Card key={feature.title} className="glass-card card-hover group">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3 group-hover:bg-primary/20 transition-colors">
                  <feature.icon className="h-5 w-5 text-primary" />
                </div>
                <CardTitle className="text-lg">{feature.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground">
                {feature.desc}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Why SolTracker */}
      <section className="container mx-auto px-4 py-16">
        <div className="grid md:grid-cols-3 gap-8 max-w-3xl mx-auto text-center">
          {[
            { icon: Zap, label: "Real-Time Data", sub: "10-15s scan intervals" },
            {
              icon: ShieldCheck,
              label: "Rug Detection",
              sub: "Automated risk scoring",
            },
            {
              icon: BarChart3,
              label: "Smart Analytics",
              sub: "PnL tracking & win rates",
            },
          ].map((item) => (
            <div key={item.label} className="flex flex-col items-center gap-2">
              <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                <item.icon className="h-6 w-6 text-primary" />
              </div>
              <p className="font-medium">{item.label}</p>
              <p className="text-sm text-muted-foreground">{item.sub}</p>
            </div>
          ))}
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
          SolTracker — Smart money analysis for Solana memecoins.
        </div>
      </footer>
    </div>
  );
}
