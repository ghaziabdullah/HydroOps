from django.urls import path

from ops import views

app_name = "ops"

urlpatterns = [
	path("alerts-center/", views.alerts_center_page_view, name="alerts-center-page"),
	path("reports/", views.reports_page_view, name="reports-page"),
	path("maintenance/", views.maintenance_page_view, name="maintenance-page"),
	path("forecasting/", views.forecasting_page_view, name="forecasting-page"),
	path("settings/", views.settings_page_view, name="settings-page"),
	path("settings/rules/<int:rule_id>/", views.update_threshold_rule_view, name="update-threshold-rule"),
	path("api/threshold-rules/", views.threshold_rule_list_api_view, name="threshold-rule-list-api"),
	path("api/alerts/", views.alert_list_api_view, name="alert-list-api"),
	path("api/alerts/<int:alert_id>/acknowledge/", views.alert_acknowledge_api_view, name="alert-acknowledge-api"),
	path("api/alerts/run-rules/", views.run_rules_api_view, name="alert-run-rules-api"),
	path("api/forecasts/latest/", views.forecast_latest_api_view, name="forecast-latest-api"),
]
