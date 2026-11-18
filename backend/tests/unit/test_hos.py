import numpy as np
import pytest

from planner.domain.hos import DrivingSchedule, HosPolicy, StopKind

H = 3600.0


def kinds(schedule):
    return [(s.kind, s.driving_s / H) for s in schedule.stops]


def test_short_trip_needs_no_stops():
    schedule = DrivingSchedule(7.5 * H, HosPolicy())
    assert schedule.stops == ()
    assert schedule.total_elapsed_s == 7.5 * H


def test_arriving_exactly_at_a_limit_does_not_trigger_a_stop():
    assert DrivingSchedule(8 * H, HosPolicy()).stops == ()
    assert kinds(DrivingSchedule(11 * H, HosPolicy())) == [(StopKind.BREAK, 8.0)]


def test_break_after_eight_hours_of_driving():
    schedule = DrivingSchedule(9 * H, HosPolicy())
    assert kinds(schedule) == [(StopKind.BREAK, 8.0)]
    assert schedule.total_elapsed_s == pytest.approx(9.5 * H)


def test_ten_hour_rest_after_eleven_hours_of_driving():
    # Denver -> Chicago is ~15.75 h of truck driving.
    schedule = DrivingSchedule(15.75 * H, HosPolicy())
    assert kinds(schedule) == [(StopKind.BREAK, 8.0), (StopKind.REST, 11.0)]
    assert schedule.total_elapsed_s == pytest.approx(26.25 * H)
    assert schedule.total_stop_s == pytest.approx(10.5 * H)


def test_multi_day_trip_repeats_the_cycle():
    schedule = DrivingSchedule(30 * H, HosPolicy())
    assert kinds(schedule) == [
        (StopKind.BREAK, 8.0),
        (StopKind.REST, 11.0),
        (StopKind.BREAK, 19.0),
        (StopKind.REST, 22.0),
    ]
    assert schedule.total_elapsed_s == pytest.approx((30 + 0.5 + 10 + 0.5 + 10) * H)


def test_elapsed_time_excludes_a_stop_that_starts_at_that_instant():
    schedule = DrivingSchedule(20 * H, HosPolicy())
    elapsed = schedule.elapsed_at(np.array([0, 8, 8.5, 11, 12]) * H) / H
    assert elapsed.tolist() == pytest.approx([0, 8, 9.0, 11.5, 22.5])


def test_disabled_policy_maps_driving_time_to_itself():
    schedule = DrivingSchedule(40 * H, HosPolicy.disabled())
    assert schedule.stops == ()
    assert schedule.elapsed_at(np.array([1.0, 39 * H])).tolist() == [1.0, 39 * H]


def test_stop_start_times_include_previous_pauses():
    schedule = DrivingSchedule(15 * H, HosPolicy())
    brk, rest = schedule.stops
    assert brk.elapsed_start_s == 8 * H
    assert rest.elapsed_start_s == pytest.approx(11.5 * H)
    assert rest.elapsed_end_s == pytest.approx(21.5 * H)
