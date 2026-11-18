from __future__ import annotations

import hashlib
from functools import cache

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .container import get_services
from .presenters import present_heatmap, present_meta, present_place, present_plan
from .serializers import HeatmapRequestSerializer, PlaceSearchSerializer, TripPlanRequestSerializer


class MetaView(APIView):
    throttle_classes: list = []

    @extend_schema(
        responses=OpenApiTypes.OBJECT,
        summary="Risk rules, ranking criteria and limits (single source of truth for the UI)",
    )
    def get(self, request: Request) -> Response:
        services = get_services()
        return Response(
            present_meta(services.rules, services.config, services.heatmap.config.hours)
        )


class TripPlanView(APIView):
    throttle_scope = "plan"

    @extend_schema(
        request=TripPlanRequestSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Plan a trip: route options, checkpoint weather risk and a recommendation",
    )
    def post(self, request: Request) -> Response:
        serializer = TripPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services = get_services()
        plan = services.planner.plan(serializer.to_trip_request())
        return Response(present_plan(plan, services.timezones.timezone_at))


class HeatmapView(APIView):
    throttle_scope = "heatmap"

    @extend_schema(
        request=HeatmapRequestSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Hourly corridor weather/risk frames for 0-48 h after departure",
    )
    def post(self, request: Request) -> Response:
        serializer = HeatmapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        service = get_services().heatmap
        heatmap = service.build(
            data["grid"]["spec"], serializer.cells, data["departure"], data["load_weight_lbs"]
        )
        return Response(present_heatmap(heatmap, service.config.hours))


class PlaceSearchView(APIView):
    throttle_scope = "places"

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, required=True, description="Free-text place or address"),
            OpenApiParameter("limit", int, description="Max results (1-10)"),
            OpenApiParameter("lat", float, description="Optional bias latitude"),
            OpenApiParameter("lon", float, description="Optional bias longitude"),
        ],
        responses=OpenApiTypes.OBJECT,
        summary="Search places for the origin/destination autocomplete",
    )
    def get(self, request: Request) -> Response:
        serializer = PlaceSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        query, limit, bias = (
            serializer.validated_data["q"],
            serializer.validated_data["limit"],
            serializer.bias(),
        )

        services = get_services()
        raw_key = f"{query.lower()}|{limit}|{bias and (round(bias.lat, 1), round(bias.lon, 1))}"
        key = "places:" + hashlib.sha256(raw_key.encode()).hexdigest()
        results = services.cache.get(key)
        if results is None:
            places = services.geocoder.search(query, limit=limit, bias=bias)
            results = [
                present_place(p, services.timezones.timezone_at(p.position.lat, p.position.lon))
                for p in places
            ]
            services.cache.set(key, results, timeout=settings.PLANNER["PLACES_CACHE_TTL_S"])
        return Response({"results": results})


def api_index(request: HttpRequest) -> JsonResponse:
    """Landing response for the API's root URL, so a visitor finds the docs instead of a 404."""

    def link(path: str) -> str:
        return request.build_absolute_uri(path)

    return JsonResponse(
        {
            "service": "Weather-Aware Truck Routing API",
            "status": "ok",
            "docs": link("/api/docs"),
            "openapi_schema": link("/api/schema"),
            "health": link("/api/health"),
            "endpoints": {
                "meta": "GET /api/v1/meta",
                "place_search": "GET /api/v1/places/search?q=denver",
                "plan_trip": "POST /api/v1/trips/plan",
                "corridor_heatmap": "POST /api/v1/trips/heatmap",
            },
        },
        json_dumps_params={"indent": 2},
    )


@cache
def _index_html() -> bytes:
    return (settings.WHITENOISE_ROOT / "index.html").read_bytes()


def spa_index(request: HttpRequest) -> HttpResponse:
    """Serves the React shell for client-side routes when the SPA is bundled with the API."""
    return HttpResponse(_index_html(), content_type="text/html; charset=utf-8")
