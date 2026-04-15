from django.contrib import admin

from ops.models import Alert, ForecastPoint, ForecastRun, ThresholdRule


@admin.register(ThresholdRule)
class ThresholdRuleAdmin(admin.ModelAdmin):
	list_display = ("rule_type", "hostel", "warning_value", "critical_value", "unit_symbol", "is_active")
	list_filter = ("rule_type", "is_active", "hostel")
	search_fields = ("rule_type", "hostel__name", "hostel__code")
	ordering = ("rule_type", "hostel__name")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
	list_display = (
		"severity",
		"alert_type",
		"message",
		"hostel",
		"unit",
		"started_at",
		"acknowledged_at",
	)
	list_filter = ("severity", "alert_type", "hostel", "started_at")
	search_fields = ("message", "hostel__name", "unit__name", "sensor__name", "asset__name")
	ordering = ("-started_at",)


class ForecastPointInline(admin.TabularInline):
	model = ForecastPoint
	extra = 0


@admin.register(ForecastRun)
class ForecastRunAdmin(admin.ModelAdmin):
	list_display = ("scope_type", "hostel", "unit", "method", "horizon_hours", "generated_at")
	list_filter = ("scope_type", "method", "hostel")
	search_fields = ("hostel__name", "unit__name", "notes")
	ordering = ("-generated_at",)
	inlines = [ForecastPointInline]
