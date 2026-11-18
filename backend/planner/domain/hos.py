"""Hours-of-Service (HOS) aware trip timing.

Routing engines return pure *driving* time. A property-carrying truck driver in the US must,
under FMCSA rules (49 CFR 395.3):

* take a 30-minute break after 8 cumulative hours of driving, and
* stop for 10 consecutive hours off duty after 11 hours of driving.

Ignoring this badly skews ETAs on long trips (a 16 h drive actually arrives ~10.5 h later),
which in turn samples the wrong forecast hour at every downstream checkpoint.

Assumptions (documented in the README): the driver starts with fresh clocks, does nothing but
drive (so the 14-hour window never binds before the 11-hour limit), and the 70-hour/8-day cycle
is not exhausted during the trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

HOUR_S = 3600.0


class StopKind(StrEnum):
    BREAK = "break"
    REST = "rest"


@dataclass(frozen=True)
class HosPolicy:
    enabled: bool = True
    max_driving_s: float = 11 * HOUR_S
    break_after_driving_s: float = 8 * HOUR_S
    break_duration_s: float = 0.5 * HOUR_S
    rest_duration_s: float = 10 * HOUR_S

    @classmethod
    def disabled(cls) -> HosPolicy:
        return cls(enabled=False)


@dataclass(frozen=True, slots=True)
class ScheduledStop:
    kind: StopKind
    driving_s: float  # cumulative driving time when the stop begins
    elapsed_start_s: float  # wall-clock seconds since departure when the stop begins
    duration_s: float

    @property
    def elapsed_end_s(self) -> float:
        return self.elapsed_start_s + self.duration_s


class DrivingSchedule:
    """Maps cumulative driving time to wall-clock elapsed time, inserting mandatory stops."""

    def __init__(self, total_driving_s: float, policy: HosPolicy) -> None:
        self.total_driving_s = float(total_driving_s)
        self.policy = policy
        self.stops = self._plan_stops() if policy.enabled else ()
        self._stop_driving = np.array([s.driving_s for s in self.stops])
        self._stop_cum_duration = np.cumsum([s.duration_s for s in self.stops])

    def _plan_stops(self) -> tuple[ScheduledStop, ...]:
        p = self.policy
        stops: list[ScheduledStop] = []
        driven = since_break = since_rest = elapsed_pause = 0.0
        while True:
            to_break = p.break_after_driving_s - since_break
            to_rest = p.max_driving_s - since_rest
            step = min(to_break, to_rest)
            if driven + step >= self.total_driving_s:  # destination reached first: no stop
                break
            driven += step
            since_break += step
            since_rest += step
            if to_rest <= to_break:
                kind, duration = StopKind.REST, p.rest_duration_s
                since_rest = since_break = 0.0  # 10 h off duty also satisfies the break rule
            else:
                kind, duration = StopKind.BREAK, p.break_duration_s
                since_break = 0.0
            stops.append(ScheduledStop(kind, driven, driven + elapsed_pause, duration))
            elapsed_pause += duration
        return tuple(stops)

    def elapsed_at(self, driving_s: np.ndarray | float) -> np.ndarray:
        """Wall-clock seconds since departure when ``driving_s`` of driving is completed.

        A stop that starts exactly at ``driving_s`` is *not* included: the truck reaches
        that point first, then rests.
        """
        driving = np.asarray(driving_s, dtype=float)
        if not self.stops:
            return driving.copy()
        completed = np.searchsorted(self._stop_driving, driving, side="left")
        pauses = np.where(completed > 0, self._stop_cum_duration[np.maximum(completed - 1, 0)], 0.0)
        return driving + pauses

    @property
    def total_elapsed_s(self) -> float:
        return float(self.elapsed_at(self.total_driving_s))

    @property
    def total_stop_s(self) -> float:
        return self.total_elapsed_s - self.total_driving_s
