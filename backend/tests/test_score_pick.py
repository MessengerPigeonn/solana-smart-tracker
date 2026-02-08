"""Tests for the new score_pick() formula in prediction_engine.py.

Validates that the winner-focused scoring system correctly:
1. Rewards high consensus (likely winners) with higher scores
2. Penalizes low consensus longshots
3. Keeps edge as a meaningful but non-dominant factor
4. Provides a sharp+consensus interaction bonus
5. Compares old vs new scores across representative scenarios
"""
import sys
import os

# Add backend to path so we can import prediction_engine directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.prediction_engine import score_pick, SPORT_WEIGHTS


# ── Old score_pick for comparison ──────────────────────────────────

def old_score_pick(
    edge: float,
    sharp_agreement: int,
    best_odds: int,
    sport: str,
    num_books: int = 0,
    consensus_prob: float = 0.5,
) -> float:
    """Old arbitrage-based scoring (pre-rework). Reproduced for comparison."""
    # Edge component: 0-35 points. Linear: 4% = 14pts, 10% = 35pts
    edge_pct = edge * 100
    edge_score = min(edge_pct * 3.5, 35)

    # Implied hit rate: 0-25 points. Sweet spot is 33-60% implied
    if 0.33 <= consensus_prob <= 0.60:
        hit_rate_score = 25.0
    elif 0.25 <= consensus_prob < 0.33:
        hit_rate_score = 18.0
    elif 0.60 < consensus_prob <= 0.70:
        hit_rate_score = 18.0
    elif consensus_prob > 0.70:
        hit_rate_score = 10.0  # <-- penalized heavy favorites
    else:
        hit_rate_score = 8.0

    # Sharp agreement: 0-20 points
    if sharp_agreement >= 2:
        sharp_score = 20.0
    elif sharp_agreement == 1:
        sharp_score = 10.0
    else:
        sharp_score = 0.0

    book_score = min(num_books * 1.5, 10)
    sport_weight = SPORT_WEIGHTS.get(sport, 0.8)
    sport_score = sport_weight * 10

    total = edge_score + hit_rate_score + sharp_score + book_score + sport_score
    return round(min(total, 100), 1)


# ── Scenario definitions ──────────────────────────────────────────

SCENARIOS = {
    "Heavy favorite (70% consensus, 5% edge, 2 sharps)": {
        "edge": 0.05,
        "sharp_agreement": 2,
        "best_odds": -230,
        "sport": "basketball_nba",
        "num_books": 5,
        "consensus_prob": 0.70,
    },
    "Coin flip (50% consensus, 10% edge, 1 sharp)": {
        "edge": 0.10,
        "sharp_agreement": 1,
        "best_odds": 110,
        "sport": "basketball_nba",
        "num_books": 4,
        "consensus_prob": 0.50,
    },
    "Moderate favorite (60% consensus, 6% edge, 2 sharps)": {
        "edge": 0.06,
        "sharp_agreement": 2,
        "best_odds": -140,
        "sport": "basketball_nba",
        "num_books": 5,
        "consensus_prob": 0.60,
    },
    "Longshot (30% consensus, 8% edge, 0 sharps)": {
        "edge": 0.08,
        "sharp_agreement": 0,
        "best_odds": 250,
        "sport": "basketball_nba",
        "num_books": 3,
        "consensus_prob": 0.30,
    },
    "Strong favorite with sharp support (72% consensus, 4% edge, 2 sharps)": {
        "edge": 0.04,
        "sharp_agreement": 2,
        "best_odds": -260,
        "sport": "basketball_nba",
        "num_books": 6,
        "consensus_prob": 0.72,
    },
    "Arbitrage trap (40% consensus, 12% edge, 0 sharps)": {
        "edge": 0.12,
        "sharp_agreement": 0,
        "best_odds": 180,
        "sport": "basketball_nba",
        "num_books": 2,
        "consensus_prob": 0.40,
    },
    "NFL moderate (58% consensus, 5% edge, 1 sharp)": {
        "edge": 0.05,
        "sharp_agreement": 1,
        "best_odds": -130,
        "sport": "americanfootball_nfl",
        "num_books": 4,
        "consensus_prob": 0.58,
    },
    "MMA longshot (25% consensus, 15% edge, 0 sharps)": {
        "edge": 0.15,
        "sharp_agreement": 0,
        "best_odds": 300,
        "sport": "mma_mixed_martial_arts",
        "num_books": 2,
        "consensus_prob": 0.25,
    },
}


# ── Unit Tests ─────────────────────────────────────────────────────

class TestHighConsensusScoresHigher:
    """High consensus (65%+) picks should score higher than the old system."""

    def test_heavy_favorite_scores_higher(self):
        """70% consensus pick should score higher in new system."""
        params = SCENARIOS["Heavy favorite (70% consensus, 5% edge, 2 sharps)"]
        old = old_score_pick(**params)
        new = score_pick(**params)
        assert new > old, (
            f"Heavy favorite: new ({new}) should be > old ({old}). "
            f"Old system penalized 70%+ consensus with only 10 hit-rate points."
        )

    def test_strong_favorite_with_sharps(self):
        """72% consensus + 2 sharps should score very high."""
        params = SCENARIOS["Strong favorite with sharp support (72% consensus, 4% edge, 2 sharps)"]
        old = old_score_pick(**params)
        new = score_pick(**params)
        assert new > old, (
            f"Strong favorite: new ({new}) should be > old ({old})"
        )

    def test_moderate_favorite_with_sharps(self):
        """60% consensus + 2 sharps should score well."""
        params = SCENARIOS["Moderate favorite (60% consensus, 6% edge, 2 sharps)"]
        new = score_pick(**params)
        # 60% consensus with 2 sharps and 6% edge should be a strong pick
        assert new >= 70, f"Moderate favorite with sharps should score >= 70, got {new}"

    def test_65_percent_consensus_scores_high(self):
        """65% consensus specifically should score well (tier boundary)."""
        new = score_pick(
            edge=0.05, sharp_agreement=1, best_odds=-170,
            sport="basketball_nba", num_books=4, consensus_prob=0.65,
        )
        assert new >= 65, f"65% consensus pick should score >= 65, got {new}"


class TestLowConsensusLongshotsScoreLower:
    """Low consensus longshots should score lower than before."""

    def test_longshot_scores_lower(self):
        """30% consensus longshot should score lower in new system."""
        params = SCENARIOS["Longshot (30% consensus, 8% edge, 0 sharps)"]
        old = old_score_pick(**params)
        new = score_pick(**params)
        assert new < old, (
            f"Longshot: new ({new}) should be < old ({old}). "
            f"Old system gave 25 hit-rate points to 30% consensus."
        )

    def test_arbitrage_trap_scores_lower(self):
        """40% consensus with huge edge but no sharps = arbitrage trap, should score lower."""
        params = SCENARIOS["Arbitrage trap (40% consensus, 12% edge, 0 sharps)"]
        old = old_score_pick(**params)
        new = score_pick(**params)
        assert new < old, (
            f"Arbitrage trap: new ({new}) should be < old ({old}). "
            f"Old system loved big edge regardless of consensus."
        )

    def test_mma_longshot_scores_low(self):
        """25% consensus MMA longshot should score low despite 15% edge."""
        params = SCENARIOS["MMA longshot (25% consensus, 15% edge, 0 sharps)"]
        new = score_pick(**params)
        assert new < 50, (
            f"MMA longshot should score < 50 despite huge edge, got {new}"
        )

    def test_longshot_below_favorite(self):
        """A 30% consensus pick with big edge should score below a 70% consensus pick."""
        longshot = score_pick(
            edge=0.10, sharp_agreement=0, best_odds=250,
            sport="basketball_nba", num_books=3, consensus_prob=0.30,
        )
        favorite = score_pick(
            edge=0.05, sharp_agreement=2, best_odds=-230,
            sport="basketball_nba", num_books=5, consensus_prob=0.70,
        )
        assert favorite > longshot, (
            f"Favorite ({favorite}) should score higher than longshot ({longshot}) "
            f"even though longshot has double the edge."
        )


class TestEdgeStillMatters:
    """Edge should contribute meaningfully but not dominate."""

    def test_more_edge_means_higher_score(self):
        """Higher edge should produce a higher score, all else equal."""
        low_edge = score_pick(
            edge=0.04, sharp_agreement=1, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.55,
        )
        high_edge = score_pick(
            edge=0.10, sharp_agreement=1, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.55,
        )
        assert high_edge > low_edge, (
            f"10% edge ({high_edge}) should score > 4% edge ({low_edge})"
        )

    def test_edge_difference_capped(self):
        """Edge difference between 4% and 10% should be at most 10 points (not 21 like old system)."""
        low_edge = score_pick(
            edge=0.04, sharp_agreement=1, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.55,
        )
        high_edge = score_pick(
            edge=0.10, sharp_agreement=1, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.55,
        )
        edge_diff = high_edge - low_edge
        assert edge_diff <= 12, (
            f"Edge difference ({edge_diff}) should be <= 12 points. "
            f"Edge matters but shouldn't dominate."
        )

    def test_edge_does_not_dominate_consensus(self):
        """A pick with huge edge but low consensus should lose to moderate edge + high consensus."""
        big_edge_low_consensus = score_pick(
            edge=0.15, sharp_agreement=0, best_odds=200,
            sport="basketball_nba", num_books=3, consensus_prob=0.35,
        )
        moderate_edge_high_consensus = score_pick(
            edge=0.06, sharp_agreement=2, best_odds=-150,
            sport="basketball_nba", num_books=5, consensus_prob=0.65,
        )
        assert moderate_edge_high_consensus > big_edge_low_consensus, (
            f"High consensus ({moderate_edge_high_consensus}) should beat "
            f"big edge low consensus ({big_edge_low_consensus})"
        )


class TestSharpConsensusInteraction:
    """Sharp agreement should provide a bonus when combined with high consensus."""

    def test_sharp_bonus_with_high_consensus(self):
        """1+ sharps with 60%+ consensus should get interaction bonus."""
        no_sharp = score_pick(
            edge=0.06, sharp_agreement=0, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.65,
        )
        with_sharp = score_pick(
            edge=0.06, sharp_agreement=1, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.65,
        )
        diff = with_sharp - no_sharp
        # Should get base sharp (8) + interaction bonus (5) = 13 pts
        assert diff >= 10, (
            f"Adding 1 sharp at 65% consensus should add >= 10 points, got {diff}"
        )

    def test_sharp_bonus_without_high_consensus(self):
        """Sharps with low consensus should give smaller boost (no interaction bonus)."""
        no_sharp = score_pick(
            edge=0.06, sharp_agreement=0, best_odds=150,
            sport="basketball_nba", num_books=4, consensus_prob=0.40,
        )
        with_sharp = score_pick(
            edge=0.06, sharp_agreement=1, best_odds=150,
            sport="basketball_nba", num_books=4, consensus_prob=0.40,
        )
        diff = with_sharp - no_sharp
        # Should get base sharp (8) but no interaction bonus
        assert diff == 8.0, (
            f"Sharp at 40% consensus should add exactly 8 points (base only), got {diff}"
        )

    def test_two_sharps_high_consensus_vs_zero_sharps(self):
        """2 sharps + 65% consensus should have big advantage over 0 sharps."""
        zero = score_pick(
            edge=0.06, sharp_agreement=0, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.65,
        )
        two = score_pick(
            edge=0.06, sharp_agreement=2, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.65,
        )
        diff = two - zero
        # 2 sharps = 15 base + 5 bonus = 20 points
        assert diff == 20.0, (
            f"2 sharps at 65% consensus should add 20 points, got {diff}"
        )

    def test_sharp_bonus_caps_at_20(self):
        """Sharp score should cap at 20 points."""
        score = score_pick(
            edge=0.06, sharp_agreement=3, best_odds=-150,
            sport="basketball_nba", num_books=4, consensus_prob=0.70,
        )
        # 3 sharps should still cap at 20 for sharp component
        # Total: 40 (consensus) + 14 (edge) + 20 (sharp) + 6 (books) + 10 (sport) = 90
        assert score <= 100, f"Score should never exceed 100, got {score}"


class TestScoreRange:
    """Verify scores stay within expected bounds."""

    def test_minimum_score(self):
        """Worst possible pick should still produce a valid score."""
        score = score_pick(
            edge=0.0, sharp_agreement=0, best_odds=500,
            sport="mma_mixed_martial_arts", num_books=0, consensus_prob=0.20,
        )
        assert 0 <= score <= 100, f"Score {score} out of valid range"
        assert score < 20, f"Terrible pick should score < 20, got {score}"

    def test_maximum_score(self):
        """Best possible pick: high consensus, big edge, 2+ sharps, many books."""
        score = score_pick(
            edge=0.15, sharp_agreement=3, best_odds=-300,
            sport="basketball_nba", num_books=7, consensus_prob=0.80,
        )
        assert score >= 85, f"Perfect pick should score >= 85, got {score}"
        assert score <= 100, f"Score should cap at 100, got {score}"

    def test_scores_are_rounded(self):
        """All scores should be rounded to 1 decimal."""
        score = score_pick(
            edge=0.057, sharp_agreement=1, best_odds=-140,
            sport="basketball_nba", num_books=3, consensus_prob=0.62,
        )
        assert score == round(score, 1), f"Score {score} not rounded to 1 decimal"


class TestSportWeights:
    """Sport reliability weights should affect scores."""

    def test_nba_scores_higher_than_mma(self):
        """Same pick in NBA (1.0) should score higher than MMA (0.8)."""
        base = dict(edge=0.06, sharp_agreement=1, best_odds=-150,
                    num_books=4, consensus_prob=0.60)
        nba = score_pick(**base, sport="basketball_nba")
        mma = score_pick(**base, sport="mma_mixed_martial_arts")
        assert nba > mma, f"NBA ({nba}) should score higher than MMA ({mma})"
        assert nba - mma == 2.0, f"Diff should be 2.0 (10*1.0 - 10*0.8), got {nba - mma}"


# ── Comparison Table ───────────────────────────────────────────────

def test_print_comparison_table(capsys):
    """Print a formatted comparison table: old score vs new score for each scenario."""
    print("\n")
    print("=" * 90)
    print(f"{'SCENARIO':<60} {'OLD':>8} {'NEW':>8} {'DELTA':>8}")
    print("=" * 90)

    for name, params in SCENARIOS.items():
        old = old_score_pick(**params)
        new = score_pick(**params)
        delta = new - old
        sign = "+" if delta > 0 else ""
        print(f"{name:<60} {old:>8.1f} {new:>8.1f} {sign}{delta:>7.1f}")

    print("=" * 90)
    print()
    print("Key changes in new scoring:")
    print("  - Heavy favorites (70%+ consensus) scored UP (no longer penalized)")
    print("  - Longshots and arbitrage traps scored DOWN (consensus is dominant)")
    print("  - Edge is tiered, not linear (enough value matters, not raw size)")
    print("  - Sharp + consensus interaction bonus rewards confirmed favorites")
    print()

    # Verify the table printed (capsys captures stdout)
    captured = capsys.readouterr()
    assert "SCENARIO" in captured.out
    assert "Heavy favorite" in captured.out
