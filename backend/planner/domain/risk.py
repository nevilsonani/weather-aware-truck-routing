"""Weather risk classification: the assessment's *Risk Rules* and *Load rules*.

Boundary convention
-------------------
The specification's bands share end points (``Rain 0.10-0.25`` / ``0.25-0.50``) and use integer
mph bands (``25-34`` / ``35-44``) for a continuous measurement. We resolve both the same way:

* every band starts *at* its lower bound (inclusive), so a shared boundary belongs to the more
  severe band (safety first) and 34.6 mph is Moderate, 35.0 mph is High;
* the only exceptions are the explicit strict inequalities of the table itself: Rain ``> 1.00``
  and Snow ``> 3.0`` for No Travel, i.e. exactly 1.00 in/hr rain is still Severe.

Load rules escalate the *wind* classification only (they are stated in terms of wind) and never
downgrade it. A checkpoint's overall level is the worst of wind, rain and snow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from .weather import WeatherConditions

UNKNOWN = -1  # sentinel used in vectorised (heat-map) classification
WIND_BASES = ("sustained", "gust")


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class Threshold:
    """A band that starts at ``value``; ``inclusive`` decides ``>=`` versus ``>``."""

    level: RiskLevel
    value: float
    inclusive: bool = True

    def met_by(self, x):
        return x >= self.value if self.inclusive else x > self.value


@dataclass(frozen=True)
class ThresholdScale:
    condition: str
    unit: str
    thresholds: tuple[Threshold, ...]

    def __post_init__(self) -> None:
        levels = [t.level for t in self.thresholds]
        values = [t.value for t in self.thresholds]
        if levels != sorted(levels) or values != sorted(values):
            raise ValueError(f"{self.condition} thresholds must ascend in level and value")

    def classify(self, value: float) -> RiskLevel:
        level = RiskLevel.LOW
        for threshold in self.thresholds:
            if not threshold.met_by(value):
                break
            level = threshold.level
        return level

    def classify_many(self, values: np.ndarray) -> np.ndarray:
        """Vectorised :meth:`classify`; NaN maps to ``UNKNOWN``."""
        levels = np.full(values.shape, int(RiskLevel.LOW), dtype=np.int8)
        with np.errstate(invalid="ignore"):
            for threshold in self.thresholds:
                levels[threshold.met_by(values)] = int(threshold.level)
        levels[np.isnan(values)] = UNKNOWN
        return levels


@dataclass(frozen=True)
class LoadRule:
    """If wind is classified ``wind_level`` and the load is strictly heavier than
    ``load_over_lbs``, the wind risk becomes ``escalate_to``."""

    wind_level: RiskLevel
    load_over_lbs: float
    escalate_to: RiskLevel

    def applies(self, wind_level: RiskLevel, load_lbs: float) -> bool:
        return wind_level == self.wind_level and load_lbs > self.load_over_lbs


WIND_SCALE = ThresholdScale(
    "wind",
    "mph",
    (
        Threshold(RiskLevel.MODERATE, 25),
        Threshold(RiskLevel.HIGH, 35),
        Threshold(RiskLevel.SEVERE, 45),
        Threshold(RiskLevel.NO_TRAVEL, 55),
    ),
)
RAIN_SCALE = ThresholdScale(
    "rain",
    "in/hr",
    (
        Threshold(RiskLevel.MODERATE, 0.10),
        Threshold(RiskLevel.HIGH, 0.25),
        Threshold(RiskLevel.SEVERE, 0.50),
        Threshold(RiskLevel.NO_TRAVEL, 1.00, inclusive=False),
    ),
)
SNOW_SCALE = ThresholdScale(
    "snow",
    "in/hr",
    (
        Threshold(RiskLevel.MODERATE, 0.5),
        Threshold(RiskLevel.HIGH, 1.0),
        Threshold(RiskLevel.SEVERE, 2.0),
        Threshold(RiskLevel.NO_TRAVEL, 3.0, inclusive=False),
    ),
)
# ">= 55 mph -> No Travel for any load" is already the top band of WIND_SCALE.
LOAD_RULES = (
    LoadRule(RiskLevel.SEVERE, 30_000, RiskLevel.NO_TRAVEL),  # 45-54 mph + > 30,000 lb
    LoadRule(RiskLevel.HIGH, 40_000, RiskLevel.SEVERE),  # 35-44 mph + > 40,000 lb
)


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel  # after load escalation
    wind_base: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    wind_mph_used: float
    load_rule: LoadRule | None = None

    @property
    def drivers(self) -> tuple[str, ...]:
        """Conditions responsible for the overall level (empty when Low)."""
        if self.level == RiskLevel.LOW:
            return ()
        by_condition = {"wind": self.wind, "rain": self.rain, "snow": self.snow}
        return tuple(name for name, lvl in by_condition.items() if lvl == self.level)


@dataclass(frozen=True)
class RiskRules:
    wind: ThresholdScale = WIND_SCALE
    rain: ThresholdScale = RAIN_SCALE
    snow: ThresholdScale = SNOW_SCALE
    load_rules: tuple[LoadRule, ...] = LOAD_RULES
    wind_basis: str = "sustained"  # or "gust": classify on gusts when the provider has them

    def __post_init__(self) -> None:
        if self.wind_basis not in WIND_BASES:
            raise ValueError(f"wind_basis must be one of {WIND_BASES}")

    def wind_value(self, conditions: WeatherConditions) -> float:
        if self.wind_basis == "gust" and conditions.gust_mph is not None:
            return conditions.gust_mph
        return conditions.wind_mph

    def escalate_wind(
        self, wind_level: RiskLevel, load_lbs: float
    ) -> tuple[RiskLevel, LoadRule | None]:
        """Strongest applicable rule, judged on the *unescalated* level (order-independent)."""
        applicable = [
            rule
            for rule in self.load_rules
            if rule.applies(wind_level, load_lbs) and rule.escalate_to > wind_level
        ]
        if not applicable:
            return wind_level, None
        strongest = max(applicable, key=lambda rule: rule.escalate_to)
        return strongest.escalate_to, strongest

    def assess(self, conditions: WeatherConditions, load_lbs: float) -> RiskAssessment:
        wind_mph = self.wind_value(conditions)
        wind_base = self.wind.classify(wind_mph)
        wind, rule = self.escalate_wind(wind_base, load_lbs)
        rain = self.rain.classify(conditions.rain_in_hr)
        snow = self.snow.classify(conditions.snow_in_hr)
        return RiskAssessment(
            level=max(wind, rain, snow),
            wind=wind,
            wind_base=wind_base,
            rain=rain,
            snow=snow,
            wind_mph_used=wind_mph,
            load_rule=rule,
        )

    def classify_many(
        self, wind_mph: np.ndarray, rain_in: np.ndarray, snow_in: np.ndarray, load_lbs: float
    ) -> np.ndarray:
        """Vectorised overall level for same-shaped arrays (``UNKNOWN`` where data is missing)."""
        base = self.wind.classify_many(wind_mph)
        wind = base.copy()
        for rule in self.load_rules:  # masks use the base level, so rules never chain
            if load_lbs > rule.load_over_lbs:
                mask = base == int(rule.wind_level)
                wind[mask] = np.maximum(wind[mask], int(rule.escalate_to))
        levels = np.maximum.reduce(
            [wind, self.rain.classify_many(rain_in), self.snow.classify_many(snow_in)]
        )
        missing = np.isnan(wind_mph) | np.isnan(rain_in) | np.isnan(snow_in)
        levels[missing] = UNKNOWN
        return levels

    def explain(
        self, assessment: RiskAssessment, conditions: WeatherConditions, load_lbs: float
    ) -> list[str]:
        """Human-readable reasons for every condition at Moderate or above."""
        reasons: list[str] = []
        if assessment.wind_base > RiskLevel.LOW or assessment.load_rule:
            basis = (
                "gusts" if self.wind_basis == "gust" and conditions.gust_mph is not None else "wind"
            )
            text = (
                f"{basis.capitalize()} {_truncate(assessment.wind_mph_used, 1)} mph → "
                f"{assessment.wind_base.label}"
            )
            if assessment.load_rule:
                rule = assessment.load_rule
                text += (
                    f"; load {load_lbs:,.0f} lb > {rule.load_over_lbs:,.0f} lb raises it to "
                    f"{rule.escalate_to.label}"
                )
            reasons.append(text)
        if assessment.rain > RiskLevel.LOW:
            reasons.append(
                f"Rain {_truncate(conditions.rain_in_hr, 3)} in/hr → {assessment.rain.label}"
            )
        if assessment.snow > RiskLevel.LOW:
            reasons.append(
                f"Snow {_truncate(conditions.snow_in_hr, 3)} in/hr → {assessment.snow.label}"
            )
        return reasons or ["All conditions within Low thresholds"]


def _truncate(value: float, digits: int) -> str:
    """Format without rounding up, so 34.96 mph never reads "35.0 mph → Moderate"."""
    factor = 10**digits
    return f"{math.floor(value * factor + 1e-9) / factor:.{digits}f}"  # 1e-9: float error
