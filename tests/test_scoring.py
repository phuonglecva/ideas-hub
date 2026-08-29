from ideas_hub.pipeline import signal_score
from ideas_hub.schemas import OpportunityScore


def test_signal_score_is_bounded():
    assert signal_score(1, 1, 1, 1, 1, 1) == 100
    assert signal_score(0, 0, 0, 0, 0, 0) == 0


def test_opportunity_score_penalizes_regulatory_risk():
    safe = OpportunityScore(
        pain=80, market_change=80, willingness_to_pay=80, why_now=80,
        competition_gap=80, distribution=80, buildability=80, reason_to_win=80,
        regulatory_risk=0, confidence=0.8,
    )
    risky = safe.model_copy(update={"regulatory_risk": 100})
    assert safe.weighted_score() > risky.weighted_score()
