"""Framework-agnostic trip planning core.

Layers (dependencies point inwards only):

* ``planner.domain``       pure business rules: risk, geometry, HOS, checkpoints, ranking.
* ``planner.integrations`` adapters for third-party APIs (routing, weather, geocoding).
* ``planner.services``     use-case orchestration built from the two layers above.

Nothing in this package imports Django; the HTTP layer lives in the ``api`` app and wires
concrete adapters into the services (see ``api.container``).
"""
