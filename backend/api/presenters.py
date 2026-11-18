"""Domain objects -> JSON-ready dicts. Every key states its unit (``_mi``, ``_s``, ``_utc``)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import numpy as np

from planner.domain import geo
from planner.domain.checkpoints import Checkpoint
from planner.domain.corridor import CorridorGrid
from planner.domain.hos import HosPolicy
from planner.domain.recommendation import CRITERIA, Comparison
from planner.domain.risk import RiskAssessment, RiskLevel, RiskRules, ThresholdScale
from planner.domain.units import meters_to_miles
from planner.domain.weather import WeatherConditions
from planner.integrations.geocoding import Place
from planner.services.heatmap import Heatmap
from planner.services.trip_planner import PlannerConfig, RouteAnalysis, TripPlan

GEOMETRY_TOLERANCE_M = 25.0  # display-only simplification of route lines


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def miles(meters: float, digits: int = 2) -> float:
    return round(meters_to_miles(meters), digits)


def _nullable(values: np.ndarray, digits: int) -> list[list[float | None]]:
    rounded = np.round(values, digits).tolist()
    return [[None if math.isnan(v) else v for v in row] for row in rounded]


# --- trip plan -------------------------------------------------------------------------------


def present_plan(plan: TripPlan, timezone_at) -> dict[str, Any]:
    rec = plan.recommendation
    rank = {route_id: i + 1 for i, route_id in enumerate(rec.ranking)}
    lost_because = {c.route_id: c for c in rec.comparisons}
    req = plan.request
    dest = req.destination.position
    return {
        "trip": {
            "origin": _endpoint(req.origin.position, req.origin.label, plan.origin_timezone),
            "destination": _endpoint(dest, req.destination.label, timezone_at(dest.lat, dest.lon)),
            "departure_utc": iso(plan.departure),
            "load_weight_lbs": req.load_weight_lbs,
            "gross_weight_lbs": plan.gross_weight_lbs,
            "sample_interval_mi": req.sample_interval_mi,
            "apply_hos": req.apply_hos,
            "provider": plan.provider,
        },
        "recommendation": {
            "route_id": rec.route_id,
            "status": rec.status.value,
            "headline": rec.headline,
            "ranking": list(rec.ranking),
            "reasons": [c.text for c in rec.comparisons],
            "criteria": [c.key for c in CRITERIA],
        },
        "routes": [
            _route(a, rank[a.id], a.id == rec.route_id, lost_because.get(a.id)) for a in plan.routes
        ],
        "corridor": {**present_grid(plan.corridor), "buffer_mi": miles(plan.corridor.buffer_m)},
        "warnings": plan.warnings,
        "generated_at": iso(plan.generated_at),
    }


def _endpoint(position: geo.LatLon, label: str, timezone: str) -> dict[str, Any]:
    return {"lat": position.lat, "lon": position.lon, "label": label, "timezone": timezone}


def _route(
    a: RouteAnalysis, rank: int, recommended: bool, lost: Comparison | None
) -> dict[str, Any]:
    profile = a.profile
    by_level = {level.key: round(profile.miles(level), 2) for level in RiskLevel}
    by_level["unknown"] = round(profile.unknown_miles, 2)
    return {
        "id": a.id,
        "label": a.label,
        "name": a.name,
        "rank": rank,
        "recommended": recommended,
        "not_recommended_because": (
            {"criterion": lost.criterion.key if lost.criterion else None, "text": lost.text}
            if lost
            else None
        ),
        "distance_mi": miles(a.route.distance_m),
        "driving_time_s": round(a.schedule.total_driving_s),
        "stop_time_s": round(a.schedule.total_stop_s),
        "total_time_s": round(a.schedule.total_elapsed_s),
        "departure_utc": iso(a.departure),
        "arrival_utc": iso(a.arrival),
        "arrival_timezone": a.timezones[-1],
        "geometry": geo.encode_polyline(
            geo.simplify(a.route.coords, GEOMETRY_TOLERANCE_M), precision=6
        ),
        "summary": {
            "miles_by_level": by_level,
            "average_risk": None
            if profile.average_risk is None
            else round(profile.average_risk, 3),
            "max_level": profile.max_level.key if profile.max_level is not None else None,
            "checkpoint_count": len(a.checkpoints),
        },
        "checkpoints": [
            _checkpoint(cp, cond, assessment, reasons, tz)
            for cp, cond, assessment, reasons, tz in zip(
                a.checkpoints, a.conditions, a.assessments, a.reasons, a.timezones, strict=True
            )
        ],
        "rest_stops": [
            {
                "kind": stop.kind.value,
                "start_utc": iso(stop.start),
                "end_utc": iso(stop.end),
                "distance_mi": miles(stop.distance_m),
                "lat": round(stop.position.lat, 5),
                "lon": round(stop.position.lon, 5),
            }
            for stop in a.rest_stops
        ],
        "timeline": [[round(t), round(meters_to_miles(d), 3)] for t, d in a.timeline.tolist()],
        "notices": list(a.route.notices),
    }


def _checkpoint(
    cp: Checkpoint,
    conditions: WeatherConditions | None,
    assessment: RiskAssessment | None,
    reasons: list[str],
    timezone: str,
) -> dict[str, Any]:
    return {
        "index": cp.index,
        "distance_mi": miles(cp.distance_m),
        "lat": round(cp.position.lat, 5),
        "lon": round(cp.position.lon, 5),
        "road": cp.road,
        "eta_utc": iso(cp.eta),
        "elapsed_s": round(cp.elapsed_s),
        "timezone": timezone,
        "coverage_mi": [miles(cp.coverage_start_m), miles(cp.coverage_end_m)],
        "weather": None
        if conditions is None
        else {
            "wind_mph": round(conditions.wind_mph, 1),
            "gust_mph": None if conditions.gust_mph is None else round(conditions.gust_mph, 1),
            "rain_in_hr": round(conditions.rain_in_hr, 3),
            "snow_in_hr": round(conditions.snow_in_hr, 3),
        },
        "risk": None
        if assessment is None
        else {
            "level": assessment.level.key,
            "score": int(assessment.level),
            "wind": assessment.wind.key,
            "rain": assessment.rain.key,
            "snow": assessment.snow.key,
            "load_escalated": assessment.load_rule is not None,
            "drivers": list(assessment.drivers),
        },
        "reasons": reasons,
    }


def present_grid(grid: CorridorGrid) -> dict[str, Any]:
    spec = grid.spec
    return {
        "west": spec.west,
        "east": spec.east,
        "south": spec.south,
        "north": spec.north,
        "nx": spec.nx,
        "ny": spec.ny,
        "cells": grid.cells.tolist(),
    }


# --- heat map --------------------------------------------------------------------------------


def present_heatmap(heatmap: Heatmap, hours: int) -> dict[str, Any]:
    return {
        "start_utc": iso(heatmap.start),
        "departure_utc": iso(heatmap.departure),
        "step_s": int(heatmap.step.total_seconds()),
        "frame_count": heatmap.frame_count,
        "hours": hours,
        "grid": present_grid(heatmap.grid),
        "layers": {
            "risk": heatmap.risk.astype(int).tolist(),  # -1 = no data
            "wind_mph": _nullable(heatmap.wind_mph, 1),
            "rain_in_hr": _nullable(heatmap.rain_in_hr, 3),
            "snow_in_hr": _nullable(heatmap.snow_in_hr, 3),
        },
        "warnings": heatmap.warnings,
    }


# --- places & metadata -----------------------------------------------------------------------


def present_place(place: Place, timezone: str) -> dict[str, Any]:
    return {
        "id": place.id,
        "name": place.name,
        "label": place.label,
        "lat": round(place.position.lat, 6),
        "lon": round(place.position.lon, 6),
        "kind": place.kind,
        "country_code": place.country_code,
        "timezone": timezone,
    }


def _scale(scale: ThresholdScale) -> dict[str, Any]:
    return {
        "unit": scale.unit,
        "thresholds": [
            {"level": t.level.key, "value": t.value, "inclusive": t.inclusive}
            for t in scale.thresholds
        ],
    }


def present_meta(rules: RiskRules, config: PlannerConfig, heatmap_hours: int) -> dict[str, Any]:
    hos: HosPolicy = config.hos_policy
    return {
        "risk_levels": [
            {"key": lvl.key, "label": lvl.label, "score": int(lvl)} for lvl in RiskLevel
        ],
        "conditions": {
            "wind": _scale(rules.wind),
            "rain": _scale(rules.rain),
            "snow": _scale(rules.snow),
        },
        "load_rules": [
            {
                "wind_level": r.wind_level.key,
                "load_over_lbs": r.load_over_lbs,
                "escalate_to": r.escalate_to.key,
            }
            for r in rules.load_rules
        ],
        "wind_basis": rules.wind_basis,
        "ranking_criteria": [c.key for c in CRITERIA],
        "sample_intervals_mi": list(config.sample_intervals_mi),
        "max_departure_days": config.max_departure_ahead.days,
        "truck_tare_weight_lbs": config.truck_tare_weight_lbs,
        "heatmap_hours": heatmap_hours,
        "hos": {
            "max_driving_h": hos.max_driving_s / 3600,
            "break_after_h": hos.break_after_driving_s / 3600,
            "break_min": hos.break_duration_s / 60,
            "rest_h": hos.rest_duration_s / 3600,
        },
    }
