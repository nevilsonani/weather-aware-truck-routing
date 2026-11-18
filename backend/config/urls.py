from django.conf import settings
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api.views import api_index, spa_index

# GET /api/health is answered by config.middleware.HealthCheckMiddleware.
urlpatterns = [
    path("api/v1/", include("api.urls")),
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if getattr(settings, "WHITENOISE_ROOT", None):
    # Client-side routes fall back to the SPA shell; real files are served by WhiteNoise.
    urlpatterns.append(re_path(r"^(?!api/|static/).*$", spa_index, name="spa"))
else:
    # API-only deployment: the root URL points visitors to the docs.
    urlpatterns.append(path("", api_index, name="index"))
