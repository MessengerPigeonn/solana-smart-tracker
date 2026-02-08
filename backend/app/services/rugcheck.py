from __future__ import annotations
import asyncio
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

RUGCHECK_BASE = "https://api.rugcheck.xyz/v1"


class RugcheckClient:
    """Client for Rugcheck.xyz free API — no API key needed."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)

    async def get_token_report(self, mint: str) -> Optional[dict]:
        """GET /tokens/{mint}/report — full security report.

        Returns dict with:
        - risks: list of risk factors [{name, description, level, score}]
        - score: int (0 = safest, higher = riskier)
        - tokenMeta: {mutable, mintAuthority, freezeAuthority}
        - topHolders: list of top holders
        - markets: list of market/LP info
        """
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(f"{RUGCHECK_BASE}/tokens/{mint}/report")
                    resp.raise_for_status()
                    data = resp.json()
                    return self._parse_report(data)
            except httpx.HTTPStatusError as e:
                logger.warning(f"Rugcheck report failed for {mint}: HTTP {e.response.status_code}")
                return None
            except Exception as e:
                logger.warning(f"Rugcheck report failed for {mint}: {e}")
                return None

    async def get_token_report_summary(self, mint: str) -> Optional[dict]:
        """GET /tokens/{mint}/report/summary — lightweight version."""
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{RUGCHECK_BASE}/tokens/{mint}/report/summary")
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                logger.warning(f"Rugcheck summary failed for {mint}: {e}")
                return None

    def _parse_report(self, data: dict) -> dict:
        """Parse raw Rugcheck response into our standard format."""
        risks = data.get("risks", [])
        score = data.get("score", 0)  # 0 = safest in Rugcheck
        token_meta = data.get("tokenMeta", {})
        top_holders = data.get("topHolders", [])
        markets = data.get("markets", [])

        # Count risk levels
        critical_risks = [r for r in risks if r.get("level") == "danger" or r.get("level") == "critical"]
        warning_risks = [r for r in risks if r.get("level") == "warn" or r.get("level") == "warning"]

        # Check LP lock status from markets
        lp_locked = False
        for market in markets:
            if market.get("lp", {}).get("lpLockedPct", 0) > 50:
                lp_locked = True
                break

        # Top holder concentration
        top_holder_pct = 0.0
        if top_holders:
            top_holder_pct = sum(h.get("pct", 0) for h in top_holders[:10]) * 100

        # Safety score: Rugcheck score where 0 = safe. Convert to our 0-100 where 100 = safe
        # Rugcheck scores typically range 0-10000+, normalize
        safety_score = max(0, 100 - min(score / 100, 100))

        return {
            "safety_score": round(safety_score, 1),
            "rugcheck_raw_score": score,
            "risks": risks,
            "critical_risk_count": len(critical_risks),
            "warning_risk_count": len(warning_risks),
            "risk_descriptions": [r.get("description", r.get("name", "")) for r in critical_risks],
            "is_mintable": bool(token_meta.get("mintAuthority")),
            "is_freezable": bool(token_meta.get("freezeAuthority")),
            "is_mutable": bool(token_meta.get("mutable")),
            "lp_locked": lp_locked,
            "top_holder_pct": round(top_holder_pct, 2),
            "top_holders": top_holders[:10],
        }


rugcheck_client = RugcheckClient()
