from django.urls import path

from iot import views

app_name = "iot"

urlpatterns = [
	path("water-quality/", views.water_quality_page_view, name="water-quality-page"),
	path("api/assets/", views.asset_list_api_view, name="asset-list-api"),
	path("api/sensors/", views.sensor_list_api_view, name="sensor-list-api"),
	path("api/readings/", views.reading_list_api_view, name="reading-list-api"),
]
