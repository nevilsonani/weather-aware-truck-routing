"""Request validation. Responses are built by ``api.presenters`` (plain dicts are much faster
than nested DRF serializers for payloads with hundreds of checkpoints and heat-map frames)."""

from __future__ import annotations

from datetime import datetime

import numpy as np
from rest_framework import serializers

from planner.domain.corridor import GridSpec
from planner.domain.geo import LatLon
from planner.services.trip_planner import Endpoint, TripRequest

MAX_LOAD_LBS = 100_000
SAMPLE_INTERVALS = (10, 25, 50)


def parse_iso_datetime(value: str, *, require_offset: bool) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise serializers.ValidationError("Use ISO-8601, e.g. 2026-11-20T08:00.") from exc
    if require_offset and parsed.tzinfo is None:
        raise serializers.ValidationError("Include a UTC offset, e.g. 2026-11-20T08:00:00Z.")
    return parsed


class EndpointSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


def _endpoint(data: dict) -> Endpoint:
    return Endpoint(
        position=LatLon(data["lat"], data["lon"]),
        label=data["label"] or f"{data['lat']:.4f}, {data['lon']:.4f}",
    )


class TripPlanRequestSerializer(serializers.Serializer):
    origin = EndpointSerializer()
    destination = EndpointSerializer()
    departure = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text=(
            "ISO-8601. A naive value (no offset) is wall-clock time at the origin, which is "
            "what a driver means by '8 AM'. Omit for 'leave now'."
        ),
    )
    load_weight_lbs = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LBS)
    sample_interval_mi = serializers.ChoiceField(choices=SAMPLE_INTERVALS, default=25)
    apply_hos = serializers.BooleanField(
        default=True, help_text="Insert FMCSA hours-of-service breaks and rests into ETAs."
    )

    def validate_departure(self, value: str | None) -> datetime | None:
        return parse_iso_datetime(value, require_offset=False) if value else None

    def to_trip_request(self) -> TripRequest:
        data = self.validated_data
        return TripRequest(
            origin=_endpoint(data["origin"]),
            destination=_endpoint(data["destination"]),
            load_weight_lbs=data["load_weight_lbs"],
            sample_interval_mi=int(data["sample_interval_mi"]),
            departure=data.get("departure"),
            apply_hos=data["apply_hos"],
        )


class GridSerializer(serializers.Serializer):
    west = serializers.FloatField(min_value=-180, max_value=180)
    east = serializers.FloatField(min_value=-180, max_value=180)
    south = serializers.FloatField(min_value=-90, max_value=90)
    north = serializers.FloatField(min_value=-90, max_value=90)
    nx = serializers.IntegerField(min_value=1, max_value=2000)
    ny = serializers.IntegerField(min_value=1, max_value=2000)
    cells = serializers.ListField(
        child=serializers.IntegerField(min_value=0), min_length=1, max_length=1000
    )

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["spec"] = GridSpec(
                west=attrs["west"],
                east=attrs["east"],
                south=attrs["south"],
                north=attrs["north"],
                nx=attrs["nx"],
                ny=attrs["ny"],
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return attrs


class HeatmapRequestSerializer(serializers.Serializer):
    grid = GridSerializer()
    departure = serializers.CharField(
        help_text="Departure instant with UTC offset (from the plan)."
    )
    load_weight_lbs = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LBS)

    def validate_departure(self, value: str) -> datetime:
        return parse_iso_datetime(value, require_offset=True)

    @property
    def cells(self) -> np.ndarray:
        return np.asarray(self.validated_data["grid"]["cells"], dtype=np.int64)


class PlaceSearchSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    limit = serializers.IntegerField(min_value=1, max_value=10, default=6)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)

    def bias(self) -> LatLon | None:
        data = self.validated_data
        if "lat" in data and "lon" in data:
            return LatLon(data["lat"], data["lon"])
        return None
