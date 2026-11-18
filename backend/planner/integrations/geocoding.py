"""Place search adapters (Photon primary, Nominatim fallback)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from planner.domain.errors import UpstreamUnavailable
from planner.domain.geo import LatLon

from .http import HttpClient, json_or_raise

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Place:
    id: str
    name: str
    label: str
    position: LatLon
    kind: str
    country_code: str | None = None


class Geocoder(Protocol):
    name: str

    def search(self, query: str, *, limit: int, bias: LatLon | None = None) -> list[Place]: ...


def _compose_label(parts: Sequence[str | None]) -> str:
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def _dedupe(places: list[Place], limit: int) -> list[Place]:
    unique: dict[str, Place] = {}
    for place in places:
        unique.setdefault(place.label.lower(), place)
    return list(unique.values())[:limit]


class PhotonGeocoder:
    """Komoot Photon: OSM-based search designed for type-ahead."""

    name = "photon"

    def __init__(self, base_url: str, http: HttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http

    def search(self, query: str, *, limit: int, bias: LatLon | None = None) -> list[Place]:
        params: dict[str, Any] = {"q": query, "limit": limit * 2, "lang": "en"}
        if bias:
            params.update(lat=bias.lat, lon=bias.lon)
        response = self.http.get(f"{self.base_url}/api/", params=params)
        if response.status_code >= 400:
            raise UpstreamUnavailable(f"Photon returned HTTP {response.status_code}")
        data = json_or_raise(response, "Photon")
        return _dedupe([self._to_place(f) for f in data.get("features", [])], limit)

    @staticmethod
    def _to_place(feature: dict[str, Any]) -> Place:
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"]
        street = " ".join(p for p in (props.get("housenumber"), props.get("street")) if p)
        name = props.get("name") or street or props.get("city") or "Unnamed place"
        return Place(
            id=f"{props.get('osm_type', '')}{props.get('osm_id', '')}",
            name=name,
            label=_compose_label(
                [
                    name,
                    street if street != name else None,
                    props.get("city"),
                    props.get("state"),
                    props.get("country"),
                ]
            ),
            position=LatLon(float(lat), float(lon)),
            kind=props.get("type") or props.get("osm_value") or "place",
            country_code=(props.get("countrycode") or "").upper() or None,
        )


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, base_url: str, http: HttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http

    def search(self, query: str, *, limit: int, bias: LatLon | None = None) -> list[Place]:
        del bias  # Nominatim has no point bias, only bounding boxes
        params = {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1}
        response = self.http.get(f"{self.base_url}/search", params=params)
        if response.status_code >= 400:
            raise UpstreamUnavailable(f"Nominatim returned HTTP {response.status_code}")
        return _dedupe([self._to_place(r) for r in json_or_raise(response, "Nominatim")], limit)

    @staticmethod
    def _to_place(row: dict[str, Any]) -> Place:
        address = row.get("address", {})
        name = row.get("name") or row.get("display_name", "").split(",")[0]
        city = address.get("city") or address.get("town") or address.get("village")
        return Place(
            id=f"nominatim:{row.get('place_id')}",
            name=name,
            label=_compose_label([name, city, address.get("state"), address.get("country")]),
            position=LatLon(float(row["lat"]), float(row["lon"])),
            kind=row.get("addresstype") or row.get("type") or "place",
            country_code=(address.get("country_code") or "").upper() or None,
        )


class FallbackGeocoder:
    def __init__(self, geocoders: Sequence[Geocoder]) -> None:
        self.geocoders = list(geocoders)
        self.name = "+".join(g.name for g in self.geocoders)

    def search(self, query: str, *, limit: int, bias: LatLon | None = None) -> list[Place]:
        last_error: UpstreamUnavailable | None = None
        for geocoder in self.geocoders:
            try:
                return geocoder.search(query, limit=limit, bias=bias)
            except UpstreamUnavailable as exc:
                logger.warning("Geocoder %s unavailable: %s", geocoder.name, exc.message)
                last_error = exc
        raise last_error or UpstreamUnavailable("No geocoder configured")
