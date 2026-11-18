from django.urls import path

from .views import HeatmapView, MetaView, PlaceSearchView, TripPlanView

app_name = "api"

urlpatterns = [
    path("meta", MetaView.as_view(), name="meta"),
    path("places/search", PlaceSearchView.as_view(), name="place-search"),
    path("trips/plan", TripPlanView.as_view(), name="trip-plan"),
    path("trips/heatmap", HeatmapView.as_view(), name="trip-heatmap"),
]
