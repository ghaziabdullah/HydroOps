from django.urls import path

from orgs import views

app_name = "orgs"

urlpatterns = [
	path("units-explorer/", views.units_explorer_page_view, name="units-explorer-page"),
	path("hostels/<int:hostel_id>/dashboard/", views.hostel_detail_page_view, name="hostel-detail-page"),
	path("hostels/<int:hostel_id>/dashboard/<slug:tab>/", views.hostel_detail_page_view, name="hostel-detail-tab-page"),
	path("units/<int:unit_id>/", views.unit_detail_page_view, name="unit-detail-page"),
	path("api/hostels/", views.hostel_list_api_view, name="hostel-list-api"),
	path("api/hostels/<int:hostel_id>/", views.hostel_detail_api_view, name="hostel-detail-api"),
	path("api/units/", views.unit_list_api_view, name="unit-list-api"),
	path("api/units/<int:unit_id>/", views.unit_detail_api_view, name="unit-detail-api"),
]
