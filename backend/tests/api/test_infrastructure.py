"""Deployment plumbing: the API landing page and the fail-open Redis cache."""

import time

from rest_framework.test import APIClient

from config.cache import ResilientRedisCache


def test_root_points_visitors_to_the_docs():
    response = APIClient().get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["docs"].endswith("/api/docs")
    assert body["health"].endswith("/api/health")
    assert "POST /api/v1/trips/plan" in body["endpoints"].values()


def test_unreachable_redis_behaves_like_an_empty_cache():
    # Port 1 refuses connections: every operation must degrade, not raise.
    cache = ResilientRedisCache(
        "redis://127.0.0.1:1/0",
        {"OPTIONS": {"socket_connect_timeout": 0.2, "socket_timeout": 0.2}},
    )
    started = time.perf_counter()
    assert cache.get("k", "fallback") == "fallback"
    assert cache.get_many(["a", "b"]) == {}
    cache.set("k", 1)
    assert cache.set_many({"a": 1}) == []
    assert cache.add("k", 1) is False
    assert cache.has_key("k") is False
    assert time.perf_counter() - started < 5  # short socket timeouts: no request hangs
