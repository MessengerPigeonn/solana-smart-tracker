"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SolPayment } from "@/components/sol-payment";
import { apiFetch } from "@/lib/api";

interface Subscription {
  tier: "free" | "pro" | "legend";
  expires: string | null;
  stripe_subscription_id: string | null;
  has_stripe: boolean;
}

export default function BillingPage() {
  const searchParams = useSearchParams();
  const planParam = searchParams.get("plan");
  const paymentSuccess = searchParams.get("payment") === "success";

  const paymentCancelled = searchParams.get("payment") === "cancelled";

  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTier, setSelectedTier] = useState<"pro" | "legend">(
    planParam === "legend" ? "legend" : "pro"
  );
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  const fetchSubscription = useCallback(async () => {
    try {
      const data = await apiFetch<Subscription>("/api/payments/subscription", {
        requireAuth: true,
      });
      setSub(data);
    } catch {
      // user will see loading state then empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

  const handleStripeCheckout = async (tierOverride?: "pro" | "legend") => {
    const tier = tierOverride ?? selectedTier;
    setCheckoutLoading(true);
    try {
      const data = await apiFetch<{ checkout_url: string }>(
        "/api/payments/stripe/checkout",
        {
          method: "POST",
          requireAuth: true,
          body: JSON.stringify({ tier }),
        }
      );
      window.location.href = data.checkout_url;
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Checkout failed");
      setCheckoutLoading(false);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const data = await apiFetch<{ portal_url: string }>(
        "/api/payments/stripe/portal",
        {
          method: "POST",
          requireAuth: true,
        }
      );
      window.open(data.portal_url, "_blank");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to open portal");
    } finally {
      setPortalLoading(false);
    }
  };

  const handleSolSuccess = () => {
    fetchSubscription();
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">Loading billing...</p>
      </div>
    );
  }

  const isActive = sub && sub.tier !== "free" && sub.expires;
  const isLegend = sub?.tier === "legend";
  const expiryDate = sub?.expires ? new Date(sub.expires) : null;
  const daysLeft = expiryDate
    ? Math.ceil(
        (expiryDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
      )
    : 0;
  const nearExpiry = daysLeft > 0 && daysLeft <= 7;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Billing</h1>

      {paymentSuccess && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-4">
          <p className="text-green-400 font-medium">
            Payment successful! Your subscription is now active.
          </p>
        </div>
      )}

      {paymentCancelled && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4">
          <p className="text-yellow-400 font-medium">
            Payment cancelled. You can try again when you&apos;re ready.
          </p>
        </div>
      )}

      {isActive ? (
        /* ── Active Subscriber View ── */
        <div className="space-y-6">
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                Subscription
                <Badge variant="teal" className="capitalize">
                  {sub.tier}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Status</p>
                  <p className="font-medium text-green-400">Active</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Expires</p>
                  <p className="font-medium">
                    {expiryDate?.toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                </div>
                {sub.stripe_subscription_id && (
                  <div>
                    <p className="text-muted-foreground">Renewal</p>
                    <p className="font-medium text-primary">Auto-renewing</p>
                  </div>
                )}
                {!sub.stripe_subscription_id && nearExpiry && (
                  <div className="col-span-2">
                    <p className="text-sm text-yellow-400">
                      Your subscription expires in {daysLeft} day
                      {daysLeft !== 1 ? "s" : ""}. Renew below.
                    </p>
                  </div>
                )}
              </div>

              <div className="flex gap-3 pt-2">
                {sub.has_stripe && sub.stripe_subscription_id && (
                  <Button
                    variant="outline"
                    onClick={handlePortal}
                    disabled={portalLoading}
                  >
                    {portalLoading ? "Opening..." : "Manage Subscription"}
                  </Button>
                )}
              </div>

              {!sub.stripe_subscription_id && nearExpiry && (
                <div className="pt-4 border-t border-border/30">
                  <p className="text-sm font-medium mb-3">Renew with SOL</p>
                  <SolPayment tier={sub.tier as "pro" | "legend"} onSuccess={handleSolSuccess} />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Upgrade option for Pro users */}
          {sub.tier === "pro" && (
            <Card className="glass-card border-primary/30">
              <CardHeader>
                <CardTitle className="text-lg">Upgrade to Legend</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-border/50 bg-card/50 p-4 space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Price</span>
                    <span className="font-bold">$999/mo <span className="font-normal text-muted-foreground">10% off with SOL</span></span>
                  </div>
                  <ul className="text-xs text-muted-foreground space-y-1 pt-1">
                    <li>Track 50 wallets (up from 10)</li>
                    <li>Full trade history + patterns</li>
                    <li>Top smart wallets list</li>
                    <li>Priority support</li>
                  </ul>
                </div>
                <Tabs defaultValue="card">
                  <TabsList className="w-full">
                    <TabsTrigger value="card" className="flex-1">Card</TabsTrigger>
                    <TabsTrigger value="sol" className="flex-1">SOL</TabsTrigger>
                  </TabsList>
                  <TabsContent value="card">
                    <Button
                      variant="gradient"
                      className="w-full"
                      onClick={() => handleStripeCheckout("legend")}
                      disabled={checkoutLoading}
                    >
                      {checkoutLoading ? "Redirecting to Stripe..." : "Upgrade to Legend — $999/mo"}
                    </Button>
                  </TabsContent>
                  <TabsContent value="sol">
                    <SolPayment tier="legend" onSuccess={handleSolSuccess} />
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}

          {isLegend && (
            <div className="text-center py-4">
              <p className="text-sm text-muted-foreground">
                You&apos;re on the highest tier. You have access to all features.
              </p>
            </div>
          )}
        </div>
      ) : (
        /* ── Free Tier / New Checkout View ── */
        <div className="space-y-6">
          {/* Plan Selection */}
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => setSelectedTier("pro")}
              className={`rounded-lg border p-4 text-left transition-colors ${
                selectedTier === "pro"
                  ? "border-primary bg-primary/10"
                  : "border-border/50 bg-card/50 hover:border-border"
              }`}
            >
              <p className="font-bold text-lg">Pro</p>
              <p className="text-2xl font-bold mt-1">
                $199
                <span className="text-sm font-normal text-muted-foreground">
                  /month
                </span>
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                10% off with SOL
              </p>
              <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                <li>Unlimited scanner</li>
                <li>Real-time callouts</li>
                <li>Track 10 wallets</li>
              </ul>
            </button>
            <button
              onClick={() => setSelectedTier("legend")}
              className={`rounded-lg border p-4 text-left transition-colors ${
                selectedTier === "legend"
                  ? "border-primary bg-primary/10"
                  : "border-border/50 bg-card/50 hover:border-border"
              }`}
            >
              <p className="font-bold text-lg">Legend</p>
              <p className="text-2xl font-bold mt-1">
                $999
                <span className="text-sm font-normal text-muted-foreground">
                  /month
                </span>
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                10% off with SOL
              </p>
              <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                <li>Everything in Pro</li>
                <li>Track 50 wallets</li>
                <li>Full trade history</li>
              </ul>
            </button>
          </div>

          {/* Payment Method Tabs */}
          <Tabs defaultValue="card">
            <TabsList className="w-full">
              <TabsTrigger value="card" className="flex-1">
                Card
              </TabsTrigger>
              <TabsTrigger value="sol" className="flex-1">
                SOL
              </TabsTrigger>
            </TabsList>

            <TabsContent value="card">
              <Card className="glass-card">
                <CardContent className="pt-6 space-y-4">
                  <div className="rounded-lg border border-border/50 bg-card/50 p-4 space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Plan</span>
                      <span className="capitalize font-medium">
                        {selectedTier}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Price</span>
                      <span className="font-bold text-lg">
                        ${selectedTier === "pro" ? "199" : "999"}/mo
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Billing</span>
                      <span className="text-primary font-medium">
                        Auto-renewing monthly
                      </span>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground text-center">
                    Secure checkout via Stripe. Cancel anytime from your billing
                    portal.
                  </p>
                  <Button
                    variant="gradient"
                    className="w-full"
                    onClick={() => handleStripeCheckout()}
                    disabled={checkoutLoading}
                  >
                    {checkoutLoading
                      ? "Redirecting to Stripe..."
                      : `Subscribe to ${selectedTier === "pro" ? "Pro" : "Legend"} — $${selectedTier === "pro" ? "199" : "999"}/mo`}
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="sol">
              <Card className="glass-card">
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground mb-2">
                    Pay with SOL from your Solana wallet. Manual renewal each
                    month.
                  </p>
                  <SolPayment
                    tier={selectedTier}
                    onSuccess={handleSolSuccess}
                  />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}
