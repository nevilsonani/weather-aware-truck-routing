"""Uniform error envelope: ``{"error": {"code", "message", "details"}}`` for every failure."""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from planner.domain.errors import (
    InvalidTripRequest,
    NoRouteFound,
    PlannerError,
    UpstreamUnavailable,
)

logger = logging.getLogger(__name__)

PLANNER_STATUS = {
    InvalidTripRequest: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NoRouteFound: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UpstreamUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def exception_handler(exc: Exception, context: dict) -> Response:
    if isinstance(exc, PlannerError):
        http_status = PLANNER_STATUS.get(type(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(_envelope(exc.code, exc.message, exc.details), status=http_status)

    response = drf_exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, exceptions.ValidationError):
            body = _envelope("validation_error", "Some fields are invalid.", response.data)
        else:
            detail = (
                response.data.get("detail", str(exc))
                if isinstance(response.data, dict)
                else str(exc)
            )
            body = _envelope(getattr(exc, "default_code", "error"), str(detail))
        response.data = body
        return response

    logger.exception("Unhandled error in %s", context.get("view"))
    return Response(
        _envelope("internal_error", "Something went wrong while planning this trip."),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
