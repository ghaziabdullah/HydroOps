from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
	path("overview/", views.overview_page_view, name="overview-page"),
	path("hostels/", views.hostels_page_view, name="hostels-page"),
	path("api/campus-overview/", views.campus_overview_api_view, name="campus-overview-api"),
	path("api/hostels-comparison/", views.hostels_comparison_api_view, name="hostels-comparison-api"),
	path("api/hostels/<int:hostel_id>/units-leaderboard/", views.hostel_units_leaderboard_api_view, name="units-leaderboard-api"),
]
