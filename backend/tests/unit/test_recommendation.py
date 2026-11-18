import pytest

from planner.domain.recommendation import (
    RecommendationStatus,
    RiskProfile,
    RouteCandidate,
    build_profile,
    recommend,
)
from planner.domain.risk import RiskLevel

H = 3600.0


def candidate(route_id, *, nt=0.0, severe=0.0, high=0.0, avg=0.1, hours=10.0, unknown=0.0):
    miles = dict.fromkeys(RiskLevel, 0.0)
    miles[RiskLevel.NO_TRAVEL] = nt
    miles[RiskLevel.SEVERE] = severe
    miles[RiskLevel.HIGH] = high
    miles[RiskLevel.LOW] = 500.0
    profile = RiskProfile(
        miles_by_level=miles, unknown_miles=unknown, average_risk=avg, max_level=RiskLevel.LOW
    )
    return RouteCandidate(route_id, f"Route {route_id}", profile, hours * H)


def test_no_travel_miles_outrank_severe_miles():
    # Read literally, "fewest Severe miles" would pick A; A is impassable, so B must win.
    result = recommend([candidate("A", nt=50, severe=0), candidate("B", nt=0, severe=100)])
    assert result.route_id == "B"
    assert result.comparisons[0].criterion.key == "no_travel_miles"


def test_fewest_severe_miles_first():
    result = recommend([candidate("A", severe=25, high=0), candidate("B", severe=0, high=300)])
    assert result.route_id == "B"


def test_then_fewest_high_miles():
    result = recommend([candidate("A", high=40, avg=0.1), candidate("B", high=10, avg=0.9)])
    assert result.route_id == "B"
    assert result.comparisons[0].text == "Fewer High miles than Route A (10.0 mi vs 40.0 mi)"


def test_then_lowest_average_risk():
    result = recommend([candidate("A", avg=0.4, hours=8), candidate("B", avg=0.2, hours=12)])
    assert result.route_id == "B"


def test_then_shortest_travel_time():
    result = recommend(
        [candidate("A", hours=12), candidate("B", hours=11), candidate("C", hours=13)]
    )
    assert result.ranking == ("B", "A", "C")
    assert result.comparisons[0].criterion.key == "travel_time"


def test_float_noise_never_decides_the_ranking():
    a = candidate("A", severe=12.5, hours=11)
    b = candidate("B", severe=12.500001, hours=10)
    result = recommend([a, b])
    assert result.route_id == "B"  # severe miles tie, so travel time decides
    assert result.comparisons[0].criterion.key == "travel_time"


def test_full_tie_keeps_engine_order():
    result = recommend([candidate("A"), candidate("B")])
    assert result.route_id == "A"
    assert result.comparisons[0].criterion is None


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({}, RecommendationStatus.CLEAR),
        ({"high": 5}, RecommendationStatus.CAUTION),
        ({"severe": 5}, RecommendationStatus.CAUTION),
        ({"nt": 5}, RecommendationStatus.NO_SAFE_ROUTE),
        ({"avg": None}, RecommendationStatus.INSUFFICIENT_DATA),
    ],
)
def test_status(kwargs, status):
    assert recommend([candidate("A", **kwargs)]).status == status


def test_no_safe_route_headline_suggests_delaying():
    result = recommend([candidate("A", nt=10), candidate("B", nt=30)])
    assert result.route_id == "A"
    assert "Every route crosses No Travel" in result.headline
    assert "delaying departure" in result.headline


def test_unknown_average_sorts_last_on_that_criterion():
    result = recommend([candidate("A", avg=None, hours=1), candidate("B", avg=2.0, hours=50)])
    assert result.route_id == "B"


def test_build_profile_weights_by_covered_distance():
    class CP:
        def __init__(self, miles):
            self.coverage_m = miles * 1609.344

    class A:
        def __init__(self, level):
            self.level = level

    profile = build_profile([CP(10), CP(30), CP(20)], [A(RiskLevel.LOW), A(RiskLevel.HIGH), None])
    assert profile.miles(RiskLevel.HIGH) == pytest.approx(30)
    assert profile.unknown_miles == pytest.approx(20)
    assert profile.average_risk == pytest.approx((0 * 10 + 2 * 30) / 40)
    assert profile.max_level == RiskLevel.HIGH


def test_missing_forecast_is_not_treated_as_safe():
    # Review finding: a route whose weather batch failed scored 0 High/Severe miles and won.
    known_high = candidate("A", high=625, hours=10)
    mostly_unknown = candidate("B", unknown=895, hours=9)
    result = recommend([mostly_unknown, known_high])
    assert result.route_id == "A"
    assert result.comparisons[0].criterion.key == "weather_coverage"
    assert "without forecast" in result.comparisons[0].text


def test_recommended_route_with_large_gap_is_insufficient_data():
    result = recommend([candidate("A", unknown=300), candidate("B", unknown=400)])
    assert result.status == RecommendationStatus.INSUFFICIENT_DATA
    assert "missing for" in result.headline
    assert "fastest" not in result.headline


def test_small_gap_downgrades_clear_to_caution():
    result = recommend([candidate("A", unknown=20)])  # 20 of 520 mi, below the 10 % guard
    assert result.status == RecommendationStatus.CAUTION
    assert "had no forecast" in result.headline


def test_status_ignores_sub_tolerance_slivers():
    assert recommend([candidate("A", severe=0.04)]).status == RecommendationStatus.CLEAR
