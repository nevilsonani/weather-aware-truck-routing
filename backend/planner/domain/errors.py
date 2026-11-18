"""Domain-level exceptions. The HTTP layer maps these to status codes."""


class PlannerError(Exception):
    """Base class for all expected (non-bug) planner failures."""

    code = "planner_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidTripRequest(PlannerError):
    """The request is well-formed but semantically impossible (e.g. origin == destination)."""

    code = "invalid_trip"


class NoRouteFound(PlannerError):
    """The routing provider answered, but no drivable route exists between the points."""

    code = "no_route"


class UpstreamUnavailable(PlannerError):
    """A third-party dependency is down, timing out or rate limiting us."""

    code = "upstream_unavailable"
