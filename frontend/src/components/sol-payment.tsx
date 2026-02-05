"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { useConnection } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import {
  PublicKey,
  SystemProgram,
  Transaction,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { formatAddress } from "@/lib/utils";

const TREASURY_ADDRESS = process.env.NEXT_PUBLIC_SOL_TREASURY_WALLET || "";

interface SolPricing {
  sol_usd: number;
  discount_pct: number;
  tiers: Record<string, { usd: number; sol: number }>;
}

interface SolPaymentProps {
  tier: "pro" | "legend";
  onSuccess: () => void;
}

export function SolPayment({ tier, onSuccess }: SolPaymentProps) {
  const { publicKey, sendTransaction, connected } = useWallet();
  const { connection } = useConnection();
  const [status, setStatus] = useState<
    "idle" | "sending" | "confirming" | "verifying" | "success" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pricing, setPricing] = useState<SolPricing | null>(null);

  useEffect(() => {
    async function fetchPricing() {
      try {
        const data = await apiFetch<SolPricing>("/api/payments/sol/pricing");
        setPricing(data);
      } catch {
        // ignore — will show loading state
      }
    }
    fetchPricing();
    const interval = setInterval(fetchPricing, 60000);
    return () => clearInterval(interval);
  }, []);

  const treasuryPubkey = useMemo(() => {
    if (!TREASURY_ADDRESS) return null;
    try {
      return new PublicKey(TREASURY_ADDRESS);
    } catch {
      return null;
    }
  }, []);

  const tierPricing = pricing?.tiers[tier];
  const amount = tierPricing?.sol ?? 0;
  const treasuryDisplay = TREASURY_ADDRESS;

  const copyAddress = useCallback(() => {
    navigator.clipboard.writeText(treasuryDisplay);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [treasuryDisplay]);

  const handlePay = useCallback(async () => {
    if (!publicKey || !sendTransaction || !treasuryPubkey || !amount) return;

    setStatus("sending");
    setError(null);

    try {
      const instruction = SystemProgram.transfer({
        fromPubkey: publicKey,
        toPubkey: treasuryPubkey,
        lamports: Math.round(amount * LAMPORTS_PER_SOL),
      });

      const transaction = new Transaction().add(instruction);
      const { blockhash } = await connection.getLatestBlockhash();
      transaction.recentBlockhash = blockhash;
      transaction.feePayer = publicKey;

      setStatus("confirming");
      const signature = await sendTransaction(transaction, connection);

      await connection.confirmTransaction(signature, "confirmed");

      setStatus("verifying");
      await apiFetch("/api/payments/sol/verify", {
        method: "POST",
        requireAuth: true,
        body: JSON.stringify({ tx_signature: signature, tier }),
      });

      setStatus("success");
      onSuccess();
    } catch (err: unknown) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Payment failed");
    }
  }, [publicKey, sendTransaction, connection, amount, tier, onSuccess, treasuryPubkey]);

  if (!treasuryPubkey) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-muted-foreground">
          SOL payments are not configured yet.
        </p>
      </div>
    );
  }

  if (!connected) {
    return (
      <div className="flex flex-col items-center gap-4 py-6">
        <p className="text-sm text-muted-foreground">
          Connect your Solana wallet to pay with SOL
        </p>
        <WalletMultiButton />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 py-4">
      <div className="rounded-lg border border-border/50 bg-card/50 p-4 space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Treasury</span>
          <button
            onClick={copyAddress}
            className="font-mono text-xs hover:text-primary transition-colors"
          >
            {formatAddress(treasuryDisplay, 6)}
            <span className="ml-1 text-muted-foreground">
              {copied ? "(copied)" : "(copy)"}
            </span>
          </button>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Amount</span>
          {amount > 0 ? (
            <span className="font-bold text-lg">{amount} SOL</span>
          ) : (
            <span className="text-muted-foreground text-sm">Loading...</span>
          )}
        </div>
        {pricing && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">SOL Price</span>
            <span className="text-xs text-muted-foreground">
              ${pricing.sol_usd} &middot; {pricing.discount_pct}% discount
            </span>
          </div>
        )}
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Plan</span>
          <span className="capitalize font-medium">{tier}</span>
        </div>
      </div>

      {status === "success" ? (
        <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-4 text-center">
          <p className="text-green-400 font-medium">Payment confirmed!</p>
          <p className="text-sm text-muted-foreground mt-1">
            Your {tier} subscription is now active.
          </p>
        </div>
      ) : (
        <Button
          variant="gradient"
          className="w-full"
          disabled={(status !== "idle" && status !== "error") || !amount}
          onClick={handlePay}
        >
          {status === "idle" && (amount ? `Pay ${amount} SOL` : "Loading price...")}
          {status === "sending" && "Sending transaction..."}
          {status === "confirming" && "Confirming on-chain..."}
          {status === "verifying" && "Verifying payment..."}
          {status === "error" && `Retry — Pay ${amount} SOL`}
        </Button>
      )}

      {error && (
        <p className="text-sm text-destructive text-center">{error}</p>
      )}
    </div>
  );
}
