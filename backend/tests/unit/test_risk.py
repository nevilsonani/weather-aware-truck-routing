import numpy as np
import pytest

from planner.domain.risk import UNKNOWN, RiskLevel, RiskRules
from planner.domain.weather import WeatherConditions

L, M, H, S, N = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
RULES = RiskRules()


def conditions(wind=0.0, rain=0.0, snow=0.0, gust=None):
    return WeatherConditions(wind_mph=wind, gust_mph=gust, rain_in_hr=rain, snow_in_hr=snow)


@pytest.mark.parametrize(
    ("mph", "expected"),
    [
        (0, L),
        (24.9, L),
        (25, M),
        (34.9, M),
        (35, H),
        (44.99, H),
        (45, S),
        (54.99, S),
        (55, N),
        (80, N),
    ],
)
def test_wind_bands(mph, expected):
    assert RULES.wind.classify(mph) == expected


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(0.0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.5, S), (1.0, S), (1.001, N)],
)
def test_rain_bands_shared_boundaries_go_to_the_more_severe_band(rate, expected):
    assert RULES.rain.classify(rate) == expected


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(0.49, L), (0.5, M), (0.99, M), (1.0, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_bands_respect_strict_no_travel_threshold(rate, expected):
    assert RULES.snow.classify(rate) == expected


@pytest.mark.parametrize(
    ("wind", "load", "expected"),
    [
        (56, 0, N),  # >= 55 mph is No Travel for any load
        (47, 30_000, S),  # rule needs strictly more than 30,000 lb
        (47, 30_001, N),  # 45-54 mph + >30,000 lb
        (40, 40_000, H),  # rule needs strictly more than 40,000 lb
        (40, 40_001, S),  # 35-44 mph + >40,000 lb
        (40, 35_000, H),  # heavy, but below the 35-44 mph threshold
        (30, 80_000, M),  # no load rule below 35 mph
        (47, 80_000, N),
    ],
)
def test_load_rules(wind, load, expected):
    assessment = RULES.assess(conditions(wind=wind), load)
    assert assessment.level == expected
    assert assessment.wind == expected


def test_load_rule_is_reported_and_explained():
    cond = conditions(wind=47)
    assessment = RULES.assess(cond, 35_000)
    assert assessment.wind_base == S
    assert assessment.load_rule is not None
    text = " ".join(RULES.explain(assessment, cond, 35_000))
    assert "35,000 lb > 30,000 lb" in text
    assert "No Travel" in text


def test_overall_level_is_worst_condition_and_drivers_name_it():
    assessment = RULES.assess(conditions(wind=30, rain=0.3, snow=0.6), 10_000)
    assert (assessment.wind, assessment.rain, assessment.snow) == (M, H, M)
    assert assessment.level == H
    assert assessment.drivers == ("rain",)


def test_calm_conditions_have_no_drivers():
    assessment = RULES.assess(conditions(wind=5), 10_000)
    assert assessment.level == L
    assert assessment.drivers == ()
    assert RULES.explain(assessment, conditions(wind=5), 10_000) == [
        "All conditions within Low thresholds"
    ]


def test_gust_basis_uses_gusts_when_available():
    gust_rules = RiskRules(wind_basis="gust")
    assert gust_rules.assess(conditions(wind=20, gust=40), 0).wind == H
    assert gust_rules.assess(conditions(wind=20, gust=None), 0).wind == L
    with pytest.raises(ValueError, match="wind_basis"):
        RiskRules(wind_basis="peak")


def test_vectorised_classification_matches_scalar_rules():
    rng = np.random.default_rng(42)
    wind = rng.uniform(0, 70, 2_000)
    rain = rng.choice([0, 0.1, 0.25, 0.5, 1.0, 1.5], 2_000) + rng.uniform(0, 0.05, 2_000)
    snow = rng.choice([0, 0.5, 1.0, 2.0, 3.0, 4.0], 2_000)
    for load in (0, 30_001, 40_001):
        vector = RULES.classify_many(wind, rain, snow, load)
        scalar = [
            int(RULES.assess(conditions(wind=w, rain=r, snow=s), load).level)
            for w, r, s in zip(wind, rain, snow, strict=True)
        ]
        assert vector.tolist() == scalar


def test_vectorised_classification_marks_missing_data_unknown():
    levels = RULES.classify_many(
        np.array([10.0, np.nan]), np.array([0.0, 0.0]), np.array([np.nan, 0.0]), 0
    )
    assert levels.tolist() == [UNKNOWN, UNKNOWN]
