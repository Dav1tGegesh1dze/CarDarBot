from __future__ import annotations

from cardarbot.analysis.comparables import select_comparables_and_estimate_value
from cardarbot.analysis.profit import calculate_profit_estimate
from cardarbot.analysis.scoring import calculate_deal_score
from cardarbot.analysis.spam_filter import evaluate_listing_credibility
from cardarbot.domain.deals import DealEvaluationDomain
from cardarbot.domain.enums import (
    ConfidenceLevel,
    CustomsStatus,
    DealClassification,
    FuelType,
)
from cardarbot.domain.vehicles import NormalizedListing


def _make_listing(
    listing_id: str,
    price: float,
    year: int = 2013,
    mileage: int = 160000,
    desc: str = "განბაჟებულია, კარგ მდგომარეობაში",
    customs: CustomsStatus = CustomsStatus.CLEARED,
) -> NormalizedListing:
    return NormalizedListing(
        source="myauto",
        source_listing_id=listing_id,
        url=f"https://www.myauto.ge/ka/pr/{listing_id}",
        make="Toyota",
        model="Prius",
        year=year,
        fuel=FuelType.HYBRID,
        powertrain="hybrid",
        mileage_km=mileage,
        location="Tbilisi",
        customs_status=customs,
        price=price,
        currency="USD",
        usd_price=price,
        description=desc,
    )


def test_spam_and_georgian_text_filtering() -> None:
    # 1. $1 placeholder Toyota Prius
    p1 = _make_listing("101", price=1.0)
    r1 = evaluate_listing_credibility(p1)
    assert r1.is_rejected is True
    assert any("placeholder" in reason.lower() for reason in r1.rejection_reasons)

    # 2. $50 BMW in running condition
    p2 = _make_listing("102", price=50.0)
    r2 = evaluate_listing_credibility(p2)
    assert r2.is_rejected is True

    # 3. Georgian down-payment-only (პირველი შენატანი)
    p3 = _make_listing("103", price=1500.0, desc="ფასი არის პირველი შენატანი 1500$")
    r3 = evaluate_listing_credibility(p3)
    assert r3.is_rejected is True
    assert r3.condition_indicators.get("down_payment_only") is True

    # 4. Parts-only (ნაწილებად) and non-running (არ იქოქება)
    p4 = _make_listing("104", price=2000.0, desc="იყიდება ნაწილებად, არ იქოქება")
    r4 = evaluate_listing_credibility(p4)
    assert r4.is_rejected is True
    assert r4.condition_indicators.get("parts_only") is True
    assert r4.condition_indicators.get("non_running") is True

    # 5. Engine or gearbox problem (ძრავის პრობლემა / კოლოფის პრობლემა)
    p5 = _make_listing("105", price=2500.0, desc="აქვს ძრავის პრობლემა და კოლოფის პრობლემა")
    r5 = evaluate_listing_credibility(p5)
    assert r5.is_rejected is True
    assert r5.condition_indicators.get("engine_problem") is True
    assert r5.condition_indicators.get("gearbox_problem") is True

    # 6. Urgent sale (სასწრაფოდ) alone is NOT rejected
    p6 = _make_listing("106", price=3400.0, desc="სასწრაფოდ! განბაჟებულია, იდეალურ მდგომარეობაში")
    r6 = evaluate_listing_credibility(p6)
    assert r6.is_rejected is False
    assert r6.condition_indicators.get("urgent_sale") is True


def test_comparable_selection_profit_and_scoring() -> None:
    candidate = _make_listing("cand1", price=3200.0, year=2013, mileage=155000)
    spam_res = evaluate_listing_credibility(candidate)
    assert spam_res.is_rejected is False

    # Pool of 6 clean comparables around $4,900 - $5,200 plus 1 duplicate and 1 rejected
    pool = [
        _make_listing("c1", price=4900.0, year=2013, mileage=160000),
        _make_listing("c2", price=5000.0, year=2013, mileage=150000),
        _make_listing("c3", price=5100.0, year=2014, mileage=145000),
        _make_listing("c4", price=5050.0, year=2012, mileage=170000),
        _make_listing("c5", price=5200.0, year=2013, mileage=155000),
        _make_listing("c6", price=4950.0, year=2013, mileage=165000),
        # Duplicate of c1 (same make, model, year, price, mileage)
        _make_listing("c1_dup", price=4900.0, year=2013, mileage=160000),
        # Suspicious $100 listing
        _make_listing("c_bad", price=100.0, year=2013, mileage=150000),
    ]

    valuation = select_comparables_and_estimate_value(
        candidate=candidate,
        pool=pool,
        min_comparables=5,
        resale_discount_percent=10.0,
    )
    assert valuation.comparable_count == 6
    assert valuation.is_uncertain is False
    assert valuation.confidence in {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}
    assert valuation.conservative_resale_usd is not None
    assert 4400.0 <= valuation.conservative_resale_usd <= 4600.0

    profit = calculate_profit_estimate(
        listing=candidate,
        valuation=valuation,
        min_profit_usd=500.0,
        default_expense_buffer_usd=400.0,
    )
    assert profit.total_expenses_usd == 400.0
    assert profit.net_profit_usd is not None
    assert profit.net_profit_usd >= 800.0
    assert profit.meets_min_profit is True

    score = calculate_deal_score(
        listing=candidate,
        spam_result=spam_res,
        valuation=valuation,
        profit=profit,
        min_comparables=5,
        target_profit_usd=500.0,
    )
    assert score.total_score >= 85
    assert score.classification == DealClassification.EXCEPTIONAL
    assert score.hard_rejected is False

    eval_domain = DealEvaluationDomain(
        source_listing_id=candidate.source_listing_id,
        valuation=valuation,
        profit=profit,
        score=score,
    )
    assert eval_domain.score.total_score == score.total_score


def test_insufficient_comparables_caps_alert_confidence() -> None:
    candidate = _make_listing("cand2", price=3000.0, year=2013)
    spam_res = evaluate_listing_credibility(candidate)
    # Only 2 comparables (<5 minimum)
    pool = [
        _make_listing("c1", price=5000.0, year=2013, mileage=150000),
        _make_listing("c2", price=5200.0, year=2013, mileage=160000),
    ]
    valuation = select_comparables_and_estimate_value(candidate, pool, min_comparables=5)
    assert valuation.is_uncertain is True
    assert valuation.confidence == ConfidenceLevel.UNCERTAIN

    profit = calculate_profit_estimate(candidate, valuation)
    score = calculate_deal_score(candidate, spam_res, valuation, profit, min_comparables=5)
    # Invariant: Do not send high-confidence alerts (>=70) for unsupported valuations
    assert score.total_score < 70
    assert score.classification == DealClassification.REVIEW
