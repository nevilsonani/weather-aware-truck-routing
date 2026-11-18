"""Route risk profiles and the recommendation policy.

Policy (from the specification, applied lexicographically), with two guards in front:

a. **Weather coverage.** Miles without a forecast (provider outage, horizon) are *unknown*, not
   safe. A route missing data for more than ``MAX_UNKNOWN_SHARE`` of its length ranks after
   every adequately covered route; otherwise a data gap would look like "0 Severe miles".
b. Fewest **No Travel** miles. The spec's list starts at "fewest Severe miles", but read
   literally that would prefer a route with 50 No-Travel miles and 0 Severe miles over one with
   10 Severe miles. No Travel is strictly worse than Severe, so it is compared first.
1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk (distance-weighted over known miles, Low=0 ... No Travel=4)
4. Shortest travel time (wall-clock, including mandatory HOS stops)

Values are quantised to a per-criterion tolerance before comparison, which keeps the ordering
transitive and stops ordinary float noise (12.5 vs 12.500001 miles) from deciding a ranking.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from .checkpoints import Checkpoint
from .risk import RiskAssessment, RiskLevel
from .units import meters_to_miles

MAX_UNKNOWN_SHARE = 0.10  # more missing forecast than this and a route cannot be trusted
MILES_TOLERANCE = 0.1


@dataclass(frozen=True)
class RiskProfile:
    miles_by_level: dict[RiskLevel, float]
    unknown_miles: float
    average_risk: float | None
    max_level: RiskLevel | None

    def miles(self, level: RiskLevel) -> float:
        return self.miles_by_level.get(level, 0.0)

    @property
    def known_miles(self) -> float:
        return sum(self.miles_by_level.values())

    @property
    def unknown_share(self) -> float:
        total = self.known_miles + self.unknown_miles
        return self.unknown_miles / total if total > 0 else 1.0

    def has(self, level: RiskLevel) -> bool:
        """At least one tolerance unit of ``level`` miles (consistent with the ranking)."""
        return _significant(self.miles(level))


def _significant(miles: float) -> bool:
    return round(miles / MILES_TOLERANCE) > 0


def build_profile(
    checkpoints: Sequence[Checkpoint], assessments: Sequence[RiskAssessment | None]
) -> RiskProfile:
    miles_by_level = dict.fromkeys(RiskLevel, 0.0)
    unknown = weighted = 0.0
    max_level: RiskLevel | None = None
    for checkpoint, assessment in zip(checkpoints, assessments, strict=True):
        miles = meters_to_miles(checkpoint.coverage_m)
        if assessment is None:
            unknown += miles
            continue
        miles_by_level[assessment.level] += miles
        weighted += int(assessment.level) * miles
        max_level = assessment.level if max_level is None else max(max_level, assessment.level)
    known = sum(miles_by_level.values())
    return RiskProfile(
        miles_by_level=miles_by_level,
        unknown_miles=unknown,
        average_risk=weighted / known if known > 0 else None,
        max_level=max_level,
    )


@dataclass(frozen=True)
class RouteCandidate:
    route_id: str
    label: str
    profile: RiskProfile
    total_time_s: float


@dataclass(frozen=True)
class Criterion:
    key: str
    better: str  # phrase used in explanations, e.g. "fewer Severe miles"
    tolerance: float
    extract: Callable[[RouteCandidate], float | None]
    fmt: Callable[[float | None], str]
    # When set, only "above the threshold or not" matters (a pass/fail guard, not a scale).
    threshold: float | None = None

    def quantize(self, candidate: RouteCandidate) -> float:
        value = self.extract(candidate)
        if value is None:
            return math.inf
        if self.threshold is not None:
            return float(value > self.threshold)
        return round(value / self.tolerance)


def format_miles(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.1f} mi"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _format_score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _format_missing(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%} without forecast"


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "weather_coverage",
        "more complete weather data",
        1.0,
        lambda c: c.profile.unknown_share,
        _format_missing,
        threshold=MAX_UNKNOWN_SHARE,
    ),
    Criterion(
        "no_travel_miles",
        "fewer No Travel miles",
        MILES_TOLERANCE,
        lambda c: c.profile.miles(RiskLevel.NO_TRAVEL),
        format_miles,
    ),
    Criterion(
        "severe_miles",
        "fewer Severe miles",
        MILES_TOLERANCE,
        lambda c: c.profile.miles(RiskLevel.SEVERE),
        format_miles,
    ),
    Criterion(
        "high_miles",
        "fewer High miles",
        MILES_TOLERANCE,
        lambda c: c.profile.miles(RiskLevel.HIGH),
        format_miles,
    ),
    Criterion(
        "average_risk",
        "lower average risk",
        0.01,
        lambda c: c.profile.average_risk,
        _format_score,
    ),
    Criterion(
        "travel_time",
        "shorter travel time",
        60.0,
        lambda c: c.total_time_s,
        format_duration,
    ),
)


class RecommendationStatus(StrEnum):
    CLEAR = "clear"  # fully forecast and nothing above Moderate on the recommended route
    CAUTION = "caution"  # High/Severe stretches remain, or small forecast gaps
    NO_SAFE_ROUTE = "no_safe_route"  # every route crosses No Travel conditions
    INSUFFICIENT_DATA = "insufficient_data"  # too much of the recommended route lacks forecasts


@dataclass(frozen=True)
class Comparison:
    route_id: str
    label: str
    criterion: Criterion | None  # None when equivalent on every criterion
    recommended_value: float | None = None
    other_value: float | None = None

    @property
    def text(self) -> str:
        if self.criterion is None:
            return f"Ties with {self.label} on every criterion"
        c = self.criterion
        return (
            f"{c.better[0].upper()}{c.better[1:]} than {self.label} "
            f"({c.fmt(self.recommended_value)} vs {c.fmt(self.other_value)})"
        )


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    ranking: tuple[str, ...]
    status: RecommendationStatus
    headline: str
    comparisons: tuple[Comparison, ...] = field(default=())


def ranking_key(candidate: RouteCandidate) -> tuple[float, ...]:
    return tuple(criterion.quantize(candidate) for criterion in CRITERIA)


def recommend(candidates: Sequence[RouteCandidate]) -> Recommendation:
    if not candidates:
        raise ValueError("At least one route candidate is required")
    # sorted() is stable, so full ties keep the routing engine's order.
    ranked = sorted(candidates, key=ranking_key)
    best = ranked[0]
    comparisons = tuple(_compare(best, other) for other in ranked[1:])
    status = _status(best)
    return Recommendation(
        route_id=best.route_id,
        ranking=tuple(c.route_id for c in ranked),
        status=status,
        headline=_headline(best, status, len(candidates)),
        comparisons=comparisons,
    )


def _compare(best: RouteCandidate, other: RouteCandidate) -> Comparison:
    for criterion in CRITERIA:
        if criterion.quantize(best) != criterion.quantize(other):
            return Comparison(
                route_id=other.route_id,
                label=other.label,
                criterion=criterion,
                recommended_value=criterion.extract(best),
                other_value=criterion.extract(other),
            )
    return Comparison(route_id=other.route_id, label=other.label, criterion=None)


def _status(best: RouteCandidate) -> RecommendationStatus:
    profile = best.profile
    if profile.average_risk is None or profile.unknown_share > MAX_UNKNOWN_SHARE:
        return RecommendationStatus.INSUFFICIENT_DATA
    if profile.has(RiskLevel.NO_TRAVEL):
        return RecommendationStatus.NO_SAFE_ROUTE
    if profile.has(RiskLevel.SEVERE) or profile.has(RiskLevel.HIGH):
        return RecommendationStatus.CAUTION
    if _significant(profile.unknown_miles):  # small gap: never claim "clear" unverified
        return RecommendationStatus.CAUTION
    return RecommendationStatus.CLEAR


def _headline(best: RouteCandidate, status: RecommendationStatus, count: int) -> str:
    p = best.profile
    if status is RecommendationStatus.NO_SAFE_ROUTE:
        scope = "Every route" if count > 1 else "The only route"
        return (
            f"{scope} crosses No Travel conditions at this departure time. {best.label} has "
            f"the least exposure ({format_miles(p.miles(RiskLevel.NO_TRAVEL))}); "
            "consider delaying departure."
        )
    if status is RecommendationStatus.INSUFFICIENT_DATA:
        return (
            f"Weather forecasts are missing for {p.unknown_share:.0%} of {best.label}, so its "
            "risk cannot be fully assessed. Re-plan shortly before relying on it."
        )
    gap = (
        f" {format_miles(p.unknown_miles)} had no forecast and are not scored."
        if _significant(p.unknown_miles)
        else ""
    )
    if p.has(RiskLevel.SEVERE) or p.has(RiskLevel.HIGH):
        exposure = ", ".join(
            f"{format_miles(p.miles(level))} {level.label}"
            for level in (RiskLevel.SEVERE, RiskLevel.HIGH)
            if p.has(level)
        )
        return f"{best.label} has the lowest weather exposure, but expect {exposure}.{gap}"
    if gap:
        return f"{best.label} shows no High, Severe or No Travel conditions where forecast.{gap}"
    return f"{best.label} is clear of High, Severe and No Travel conditions."
