"""Job Atlas pricing engine.

Central place for margin math. Every place that quotes a client price for
talent hours (Projects, milestones, browse-talent hover cards, admin margin
dashboards) MUST go through `sell_rate()` / `price_team()` here so we never
end up with two divergent formulas.

Design goals
------------
* Guarantee a **10%–20% gross margin** on every hour we sell.
* Slide the margin **down** as talent rate goes **up** so that top-of-market
  experts remain price-competitive (customers are more price-sensitive on
  senior rates) while entry/mid tiers absorb a larger cushion.
* Support mixed teams (e.g. 1× $200/hr architect + 3× $50/hr engineers) —
  each seat is priced independently, blended margin is reported separately.
* Volume relief: a small discount on the client price for large monthly
  hour commitments, but we never breach the 10% floor.

Tier ladder (talent-facing rate in USD/hr, applied to each seat)
----------------------------------------------------------------
    <= $50/hr           →  20% margin  (entry / junior)
    $51 – $100/hr       →  18% margin  (mid)
    $101 – $150/hr      →  15% margin  (senior)
    $151 – $200/hr      →  12% margin  (principal)
    >$200/hr            →  10% margin  (top / niche)
"""
from typing import Any, Dict, List, Optional


MARGIN_TIERS = [
    {"max_rate":  50, "margin_pct": 20, "label": "Entry"},
    {"max_rate": 100, "margin_pct": 18, "label": "Mid"},
    {"max_rate": 150, "margin_pct": 15, "label": "Senior"},
    {"max_rate": 200, "margin_pct": 12, "label": "Principal"},
    {"max_rate": 10_000, "margin_pct": 10, "label": "Top / Niche"},
]

# Volume tiers reduce the client price a tiny bit for big monthly commitments.
# We slice from the margin, never from the talent rate — so the talent always
# gets what they quoted. Floor is 10%.
VOLUME_DISCOUNTS = [
    {"min_monthly_hours":   0, "discount_pct": 0.0},
    {"min_monthly_hours": 320, "discount_pct": 2.0},   # 2 seats × 160h
    {"min_monthly_hours": 640, "discount_pct": 3.5},   # 4 seats
    {"min_monthly_hours": 960, "discount_pct": 5.0},   # 6 seats
]

DEFAULT_HOURS_PER_MONTH = 160


def margin_pct(talent_rate: float) -> float:
    """Return the tier margin percentage for a given talent hourly rate."""
    r = float(talent_rate or 0)
    for tier in MARGIN_TIERS:
        if r <= tier["max_rate"]:
            return float(tier["margin_pct"])
    return float(MARGIN_TIERS[-1]["margin_pct"])


def sell_rate(talent_rate: float, volume_discount_pct: float = 0.0) -> float:
    """Compute the per-hour client price for a talent seat.

    volume_discount_pct is deducted from the margin (never taking us below 10%).
    """
    r = float(talent_rate or 0)
    m = margin_pct(r)
    effective = max(10.0, m - float(volume_discount_pct or 0))
    return round(r * (1 + effective / 100.0), 2)


def _volume_discount_for(monthly_hours: float) -> float:
    d = 0.0
    for tier in VOLUME_DISCOUNTS:
        if monthly_hours >= tier["min_monthly_hours"]:
            d = tier["discount_pct"]
    return d


def price_team(
    team: List[Dict[str, Any]],
    hours_per_month: int = DEFAULT_HOURS_PER_MONTH,
    months: int = 1,
) -> Dict[str, Any]:
    """Price a mixed team.

    `team` is a list of seats. Each seat must include one of:
      - `rate` (float)  — explicit talent rate
      - `rate_range` [low, high]  — mid is used when `rate` is missing
    Every seat may also include `role`, `talent_name`, etc. — those pass through
    untouched into the breakdown.

    Returns a bundle with per-seat monthly numbers, program totals and the
    blended margin.
    """
    seats = list(team or [])
    seat_count = len(seats)
    monthly_hours = seat_count * hours_per_month
    v_disc = _volume_discount_for(monthly_hours)

    breakdown = []
    total_talent_monthly = 0.0
    total_client_monthly = 0.0
    for seat in seats:
        rate = seat.get("rate")
        if rate is None:
            rr = seat.get("rate_range") or [0, 0]
            rate = (float(rr[0]) + float(rr[1])) / 2.0 if rr else 0.0
        rate = float(rate or 0)
        m = margin_pct(rate)
        eff_margin = max(10.0, m - v_disc)
        s_rate = round(rate * (1 + eff_margin / 100.0), 2)
        seat_talent_month = round(rate * hours_per_month, 2)
        seat_client_month = round(s_rate * hours_per_month, 2)
        breakdown.append({
            "role": seat.get("role"),
            "talent_name": seat.get("talent_name"),
            "talent_id": seat.get("talent_id"),
            "seat_index": seat.get("seat_index"),
            "talent_rate": rate,
            "margin_pct": m,
            "effective_margin_pct": round(eff_margin, 2),
            "sell_rate": s_rate,
            "monthly_talent_cost": seat_talent_month,
            "monthly_client_price": seat_client_month,
        })
        total_talent_monthly += seat_talent_month
        total_client_monthly += seat_client_month

    total_talent = round(total_talent_monthly * months, 2)
    total_client = round(total_client_monthly * months, 2)
    total_margin = round(total_client - total_talent, 2)
    blended_margin_pct = round((total_margin / total_talent) * 100, 2) if total_talent > 0 else 0.0

    return {
        "breakdown": breakdown,
        "seat_count": seat_count,
        "months": months,
        "hours_per_month_per_seat": hours_per_month,
        "monthly_hours": monthly_hours,
        "volume_discount_pct": v_disc,
        "monthly_talent_cost": round(total_talent_monthly, 2),
        "monthly_client_price": round(total_client_monthly, 2),
        "total_talent_cost": total_talent,
        "total_client_price": total_client,
        "total_margin": total_margin,
        "blended_margin_pct": blended_margin_pct,
    }


def tiers_summary() -> Dict[str, Any]:
    """Public snapshot of the pricing ladder for the /pricing page + admin UI."""
    return {
        "margin_tiers": [
            {"max_rate": t["max_rate"], "margin_pct": t["margin_pct"], "label": t["label"]}
            for t in MARGIN_TIERS
        ],
        "volume_discounts": VOLUME_DISCOUNTS,
        "hours_per_month_per_seat": DEFAULT_HOURS_PER_MONTH,
        "min_margin_floor_pct": 10,
        "notes": [
            "Talent is always paid the rate they listed. Job Atlas margin is added on top when quoting the employer.",
            "Margin narrows as talent rate rises so senior experts stay price-competitive.",
            "Volume discounts trim the margin (never the talent rate) and never drop below 10%.",
        ],
    }
