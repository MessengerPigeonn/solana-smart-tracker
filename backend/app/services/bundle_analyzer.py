"""Bundle detection service for Solana token launches.

Detects coordinated buying patterns at token launch:
1. Same-slot buys (Jito bundles) — multiple wallets buying in the same ~0.4s block
2. Staggered buys — wallets buying within a 5-minute window with similar amounts
3. Funding source clustering — early buyers funded from a common source
4. Amount similarity — suspiciously similar buy sizes (coefficient of variation < 0.3)

Uses Helius Enhanced Transactions API for slot-level transaction data.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import defaultdict
from typing import Optional

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

HELIUS_API = "https://api.helius.xyz/v0"

# Detection thresholds
SAME_SLOT_MIN_WALLETS = 2       # 2+ buys in same slot = bundled
STAGGER_WINDOW_SECONDS = 300    # 5 minutes for staggered bundle detection
AMOUNT_CV_THRESHOLD = 0.35      # Coefficient of variation < 0.35 = suspiciously similar
FUNDING_TRACE_DEPTH = 3         # How many recent txs to check for common funding
MIN_BUNDLE_WALLETS = 2          # Minimum wallets to consider it a bundle
SUPPLY_DANGER_PCT = 30.0        # Bundle holding > 30% = danger


class BundleAnalysis:
    """Result of bundle analysis for a token."""

    __slots__ = (
        "is_bundled", "bundle_wallets", "bundle_wallet_count",
        "same_slot_groups", "has_consecutive_indices", "stagger_group_count",
        "amount_cv", "common_funder",
        "estimated_bundle_pct", "estimated_held_pct",
        "risk_level", "details", "warmup_detected",
    )

    def __init__(self):
        self.is_bundled: bool = False
        self.bundle_wallets: list[str] = []
        self.bundle_wallet_count: int = 0
        self.same_slot_groups: int = 0          # Number of slot clusters found
        self.has_consecutive_indices: bool = False  # Consecutive tx indices = confirmed Jito bundle
        self.stagger_group_count: int = 0       # Wallets in staggered window
        self.amount_cv: float = 1.0             # Coefficient of variation (lower = more suspicious)
        self.common_funder: Optional[str] = None  # Shared funding source if found
        self.estimated_bundle_pct: float = 0.0  # Estimated % of supply from bundle
        self.estimated_held_pct: float = 0.0    # Estimated % still held by bundle wallets
        self.risk_level: str = "none"           # none / low / medium / high
        self.details: list[str] = []
        self.warmup_detected: bool = False      # True if bundled wallets show warmup patterns

    def to_dict(self) -> dict:
        return {
            "is_bundled": self.is_bundled,
            "bundle_wallet_count": self.bundle_wallet_count,
            "same_slot_groups": self.same_slot_groups,
            "stagger_group_count": self.stagger_group_count,
            "amount_cv": round(self.amount_cv, 3),
            "common_funder": self.common_funder,
            "estimated_bundle_pct": round(self.estimated_bundle_pct, 1),
            "estimated_held_pct": round(self.estimated_held_pct, 1),
            "risk_level": self.risk_level,
            "details": self.details,
            "warmup_detected": self.warmup_detected,
        }


class BundleAnalyzer:
    """Analyzes token launch transactions for coordinated buying patterns."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)
        self._cache: dict[str, tuple[float, BundleAnalysis]] = {}
        self._cache_ttl = 300  # 5 minutes — bundle data doesn't change

    async def _helius_get(self, path: str, params: Optional[dict] = None) -> list | dict:
        """GET request to Helius API."""
        async with self._semaphore:
            all_params = {"api-key": settings.helius_api_key}
            if params:
                all_params.update(params)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{HELIUS_API}{path}",
                    params=all_params,
                )
                resp.raise_for_status()
                return resp.json()

    async def analyze_token(self, token_address: str) -> BundleAnalysis:
        """Full bundle analysis for a token.

        Fetches early transactions, groups by slot, checks for staggered
        patterns, analyzes amount similarity, and traces funding sources.
        """
        # Check cache
        if token_address in self._cache:
            ts, result = self._cache[token_address]
            if time.monotonic() - ts < self._cache_ttl:
                return result

        analysis = BundleAnalysis()

        try:
            # Get early transactions for this token
            txs = await self._helius_get(
                f"/addresses/{token_address}/transactions",
                params={"limit": 100, "type": "SWAP"},
            )
        except Exception as e:
            logger.debug(f"BundleAnalyzer: failed to fetch txs for {token_address}: {e}")
            self._cache[token_address] = (time.monotonic(), analysis)
            return analysis

        if not isinstance(txs, list) or len(txs) < 2:
            self._cache[token_address] = (time.monotonic(), analysis)
            return analysis

        # Parse buy transactions: extract wallet, slot, timestamp, amount
        buys = []
        for tx in reversed(txs):  # Chronological order (oldest first)
            if tx.get("type") != "SWAP":
                continue

            fee_payer = tx.get("feePayer", "")
            if not fee_payer:
                continue

            slot = tx.get("slot", 0)
            timestamp = tx.get("timestamp", 0)
            token_transfers = tx.get("tokenTransfers", [])

            is_buy = False
            sol_amount = 0.0

            for transfer in token_transfers:
                mint = transfer.get("mint", "")
                if mint == token_address:
                    if transfer.get("toUserAccount") == fee_payer:
                        is_buy = True
                else:
                    sol_amount = abs(transfer.get("tokenAmount", 0) or 0)

            if is_buy and sol_amount > 0:
                buys.append({
                    "wallet": fee_payer,
                    "slot": slot,
                    "timestamp": timestamp,
                    "amount": sol_amount,
                    "signature": tx.get("signature", ""),
                    "tx_index": tx.get("transactionIndex", -1),
                })

        if len(buys) < 2:
            self._cache[token_address] = (time.monotonic(), analysis)
            return analysis

        # ─── 1. Same-slot detection + consecutive transactionIndex ───
        slot_groups: dict[int, list[dict]] = defaultdict(list)
        for buy in buys:
            if buy["slot"] > 0:
                slot_groups[buy["slot"]].append(buy)

        bundled_wallets = set()
        same_slot_cluster_count = 0

        for slot, group in slot_groups.items():
            if len(group) >= SAME_SLOT_MIN_WALLETS:
                same_slot_cluster_count += 1
                for buy in group:
                    bundled_wallets.add(buy["wallet"])

                # Check for consecutive transactionIndex (strongest Jito signal)
                indices = sorted(b["tx_index"] for b in group if b["tx_index"] >= 0)
                consecutive = _count_consecutive(indices)
                if consecutive >= 2:
                    analysis.has_consecutive_indices = True
                    analysis.details.append(
                        f"slot {slot}: {len(group)} buys, {consecutive} consecutive "
                        f"tx indices (Jito bundle)"
                    )
                else:
                    analysis.details.append(
                        f"slot {slot}: {len(group)} buys in same block"
                    )

        analysis.same_slot_groups = same_slot_cluster_count

        # ─── 2. Staggered buy detection (5-min window) ───────────────
        if buys and buys[0]["timestamp"] > 0:
            launch_ts = buys[0]["timestamp"]
            stagger_window = [
                b for b in buys
                if 0 < (b["timestamp"] - launch_ts) <= STAGGER_WINDOW_SECONDS
                or b["timestamp"] == launch_ts
            ]

            # Unique wallets in the stagger window
            stagger_wallets = set(b["wallet"] for b in stagger_window)
            analysis.stagger_group_count = len(stagger_wallets)

            # If many wallets bought in first 5 min with similar amounts → suspicious
            if len(stagger_wallets) >= 3:
                stagger_amounts = [b["amount"] for b in stagger_window]
                cv = _coefficient_of_variation(stagger_amounts)
                if cv < AMOUNT_CV_THRESHOLD:
                    # Suspiciously similar amounts in stagger window
                    for w in stagger_wallets:
                        bundled_wallets.add(w)
                    analysis.details.append(
                        f"staggered buys: {len(stagger_wallets)} wallets in "
                        f"first 5min with similar amounts (CV={cv:.2f})"
                    )

        # ─── 3. Amount similarity (all early buys) ───────────────────
        amounts = [b["amount"] for b in buys[:30]]  # First 30 buys
        analysis.amount_cv = _coefficient_of_variation(amounts)

        if analysis.amount_cv < AMOUNT_CV_THRESHOLD and len(buys) >= 3:
            analysis.details.append(
                f"amount similarity: CV={analysis.amount_cv:.2f} across "
                f"first {min(len(buys), 30)} buys (< {AMOUNT_CV_THRESHOLD} threshold)"
            )

        # ─── 4. Funding source tracing ────────────────────────────────
        # Check if early buyers share a common funding source
        # by examining recent SOL transfers TO the buyer wallets
        early_wallet_addrs = list(set(b["wallet"] for b in buys[:20]))
        common_funder = await self._trace_common_funder(early_wallet_addrs[:10])
        if common_funder:
            bundled_wallets.update(early_wallet_addrs[:10])
            analysis.common_funder = common_funder
            analysis.details.append(
                f"common funder detected: {common_funder[:8]}... "
                f"funded {len(early_wallet_addrs[:10])} early buyers"
            )

        # ─── Aggregate results ────────────────────────────────────────
        analysis.bundle_wallets = list(bundled_wallets)
        analysis.bundle_wallet_count = len(bundled_wallets)

        if analysis.bundle_wallet_count >= MIN_BUNDLE_WALLETS:
            analysis.is_bundled = True

            # Estimate bundle supply % from buy amounts
            total_early_amount = sum(b["amount"] for b in buys[:50])
            bundle_amount = sum(
                b["amount"] for b in buys[:50]
                if b["wallet"] in bundled_wallets
            )
            if total_early_amount > 0:
                analysis.estimated_bundle_pct = (bundle_amount / total_early_amount) * 100

            # Estimate held %: check if bundled wallets also appear as sellers
            sell_wallets = set()
            for tx in txs:
                if tx.get("type") != "SWAP":
                    continue
                fee_payer = tx.get("feePayer", "")
                for transfer in tx.get("tokenTransfers", []):
                    if transfer.get("mint") == token_address:
                        if transfer.get("fromUserAccount") == fee_payer:
                            sell_wallets.add(fee_payer)

            # Wallets that bundled but haven't sold = still holding
            still_holding = bundled_wallets - sell_wallets
            if bundled_wallets:
                hold_ratio = len(still_holding) / len(bundled_wallets)
                analysis.estimated_held_pct = analysis.estimated_bundle_pct * hold_ratio

            # Determine risk level
            analysis.risk_level = _calculate_risk_level(analysis)

            # ─── 5. Warmup detection on bundle wallets ──────────────────
            try:
                from app.services.wallet_profiler import wallet_profiler
                profile_addrs = analysis.bundle_wallets[:5]
                if len(profile_addrs) >= 2:
                    profiles = await wallet_profiler.batch_profile_wallets(profile_addrs)
                    if profiles:
                        avg_warmup = sum(p.warmup_score for p in profiles) / len(profiles)
                        if avg_warmup > 0.5:
                            analysis.warmup_detected = True
                            # Bump risk level up one tier
                            if analysis.risk_level == "low":
                                analysis.risk_level = "medium"
                            elif analysis.risk_level == "medium":
                                analysis.risk_level = "high"
                            analysis.details.append(
                                f"warmup detected: avg score {avg_warmup:.2f} "
                                f"across {len(profiles)} bundled wallets"
                            )
            except Exception as e:
                logger.debug(f"BundleAnalyzer: warmup check failed: {e}")

        # Cache and return
        self._cache[token_address] = (time.monotonic(), analysis)
        logger.info(
            f"BundleAnalyzer: {token_address[:8]} — "
            f"bundled={analysis.is_bundled}, wallets={analysis.bundle_wallet_count}, "
            f"supply≈{analysis.estimated_bundle_pct:.0f}%, "
            f"held≈{analysis.estimated_held_pct:.0f}%, "
            f"risk={analysis.risk_level}"
        )
        return analysis

    async def _extract_funders(self, addr: str) -> list[str]:
        """Extract SOL funders for a single wallet address."""
        funders = []
        try:
            txs = await self._helius_get(
                f"/addresses/{addr}/transactions",
                params={"limit": 10},
            )
            if not isinstance(txs, list):
                return funders

            for tx in txs:
                native_transfers = tx.get("nativeTransfers", [])
                for nt in native_transfers:
                    if (
                        nt.get("toUserAccount") == addr
                        and nt.get("fromUserAccount")
                        and nt.get("amount", 0) > 0
                    ):
                        funder = nt["fromUserAccount"]
                        if not funder.startswith("1111") and len(funder) > 30:
                            funders.append(funder)
        except Exception as e:
            logger.debug(f"BundleAnalyzer: funding trace failed for {addr[:8]}: {e}")
        return funders

    async def _trace_common_funder(
        self, wallet_addresses: list[str], max_hops: int = 2
    ) -> Optional[str]:
        """Multi-hop funding trace. Check if wallets share a common SOL source.

        Hop 1: wallet → direct funder
        Hop 2: funder → funder's funder (only if hop 1 finds no match)
        If 3+ wallets share any node in the funding graph → common funder.
        """
        if len(wallet_addresses) < 3:
            return None

        # ── Hop 1: direct funders ──
        # wallet_address → list of direct funders
        wallet_funders: dict[str, list[str]] = {}
        funder_counts: dict[str, int] = defaultdict(int)
        checked = 0

        for addr in wallet_addresses[:8]:
            cache_key = f"funder_{addr}"
            if cache_key in self._cache:
                ts, cached_funders = self._cache[cache_key]
                if time.monotonic() - ts < self._cache_ttl:
                    wallet_funders[addr] = cached_funders
                    for f in cached_funders:
                        funder_counts[f] += 1
                    checked += 1
                    continue

            funders = await self._extract_funders(addr)
            wallet_funders[addr] = funders
            self._cache[cache_key] = (time.monotonic(), funders)
            for f in funders:
                funder_counts[f] += 1
            checked += 1
            await asyncio.sleep(0.3)

        if checked < 3:
            return None

        # Check hop 1 results
        for funder, count in sorted(funder_counts.items(), key=lambda x: -x[1]):
            if count >= 3:
                return funder

        # ── Hop 2: trace funders' funders (only if hop 1 found no match) ──
        if max_hops < 2:
            return None

        # Collect unique hop-1 funders to trace further
        hop1_funders = set()
        for funders in wallet_funders.values():
            hop1_funders.update(funders)

        # Map: hop2_funder → set of original wallets that connect to it
        hop2_graph: dict[str, set[str]] = defaultdict(set)

        for hop1_funder in list(hop1_funders)[:8]:
            cache_key = f"funder_{hop1_funder}"
            if cache_key in self._cache:
                ts, cached_funders = self._cache[cache_key]
                if time.monotonic() - ts < self._cache_ttl:
                    hop2_funders = cached_funders
                else:
                    hop2_funders = await self._extract_funders(hop1_funder)
                    self._cache[cache_key] = (time.monotonic(), hop2_funders)
                    await asyncio.sleep(0.3)
            else:
                hop2_funders = await self._extract_funders(hop1_funder)
                self._cache[cache_key] = (time.monotonic(), hop2_funders)
                await asyncio.sleep(0.3)

            # Map hop2 funders back to original wallets
            for h2f in hop2_funders:
                # Find which original wallets connect through this hop1_funder
                for orig_wallet, orig_funders in wallet_funders.items():
                    if hop1_funder in orig_funders:
                        hop2_graph[h2f].add(orig_wallet)

        # Check if any hop-2 funder connects 3+ original wallets
        for h2_funder, connected_wallets in sorted(
            hop2_graph.items(), key=lambda x: -len(x[1])
        ):
            if len(connected_wallets) >= 3:
                return h2_funder

        return None

    def clear_cache(self):
        self._cache.clear()


def _count_consecutive(indices: list[int]) -> int:
    """Count the longest run of consecutive integers in a sorted list.
    e.g. [3, 4, 5, 8, 9] → 3 (the run 3,4,5)."""
    if len(indices) < 2:
        return len(indices)
    best = 1
    current = 1
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _coefficient_of_variation(values: list[float]) -> float:
    """Calculate coefficient of variation (std_dev / mean).
    Lower values = more similar amounts. Returns 1.0 if insufficient data."""
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 1.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std_dev = math.sqrt(variance)
    return std_dev / mean


def _calculate_risk_level(analysis: BundleAnalysis) -> str:
    """Determine bundle risk level based on analysis results."""
    score = 0

    # Same-slot clusters are strongest signal
    if analysis.same_slot_groups >= 2:
        score += 3
    elif analysis.same_slot_groups >= 1:
        score += 2

    # Consecutive tx indices = confirmed Jito bundle (very strong)
    if analysis.has_consecutive_indices:
        score += 2

    # Many wallets in bundle
    if analysis.bundle_wallet_count >= 10:
        score += 3
    elif analysis.bundle_wallet_count >= 5:
        score += 2
    elif analysis.bundle_wallet_count >= 3:
        score += 1

    # High supply concentration
    if analysis.estimated_bundle_pct >= 40:
        score += 3
    elif analysis.estimated_bundle_pct >= 20:
        score += 2
    elif analysis.estimated_bundle_pct >= 10:
        score += 1

    # Common funder = strong evidence
    if analysis.common_funder:
        score += 2

    # Amount similarity
    if analysis.amount_cv < 0.15:
        score += 2
    elif analysis.amount_cv < AMOUNT_CV_THRESHOLD:
        score += 1

    # Bundle still holding = less immediate risk
    if analysis.estimated_held_pct > analysis.estimated_bundle_pct * 0.8:
        score -= 1  # Still holding, might be conviction

    if score >= 6:
        return "high"
    elif score >= 3:
        return "medium"
    elif score >= 1:
        return "low"
    return "none"


# Module-level singleton
bundle_analyzer = BundleAnalyzer()
