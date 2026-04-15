from django.db import models


class ThresholdRule(models.Model):
	class RuleType(models.TextChoices):
		NIGHT_CONTINUOUS_FLOW = "NIGHT_CONTINUOUS_FLOW", "Night Continuous Flow"
		BLOCKAGE_PATTERN = "BLOCKAGE_PATTERN", "Blockage Pattern"
		TANK_LOW = "TANK_LOW", "Tank Low"
		TANK_OVERFLOW_RISK = "TANK_OVERFLOW_RISK", "Tank Overflow Risk"
		QUALITY_PH = "QUALITY_PH", "pH Exceedance"
		QUALITY_TURBIDITY = "QUALITY_TURBIDITY", "Turbidity Exceedance"
		QUALITY_TDS = "QUALITY_TDS", "TDS Exceedance"
		SENSOR_OFFLINE_MINUTES = "SENSOR_OFFLINE_MINUTES", "Sensor Offline Minutes"
		CAMPUS_INLET_DIFF_PERCENT = "CAMPUS_INLET_DIFF_PERCENT", "Campus Inlet Difference Percent"

	hostel = models.ForeignKey(
		"orgs.Hostel",
		on_delete=models.CASCADE,
		related_name="threshold_rules",
		null=True,
		blank=True,
	)
	rule_type = models.CharField(max_length=40, choices=RuleType.choices)
	warning_value = models.FloatField()
	critical_value = models.FloatField()
	unit_symbol = models.CharField(max_length=20, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["rule_type", "hostel__name"]
		constraints = [
			models.UniqueConstraint(fields=["hostel", "rule_type"], name="unique_threshold_per_scope"),
		]
		indexes = [
			models.Index(fields=["hostel", "rule_type"]),
			models.Index(fields=["is_active"]),
		]

	def __str__(self) -> str:
		scope = self.hostel.code if self.hostel_id else "GLOBAL"
		return f"{scope} - {self.rule_type}"


class Alert(models.Model):
	class Severity(models.TextChoices):
		INFO = "INFO", "Info"
		WARN = "WARN", "Warn"
		CRITICAL = "CRITICAL", "Critical"

	class AlertType(models.TextChoices):
		LEAK_SUSPECTED = "LEAK_SUSPECTED", "Leak Suspected"
		BLOCKAGE_SUSPECTED = "BLOCKAGE_SUSPECTED", "Blockage Suspected"
		TANK_LOW = "TANK_LOW", "Tank Low"
		OVERFLOW_RISK = "OVERFLOW_RISK", "Overflow Risk"
		QUALITY_EXCEEDANCE = "QUALITY_EXCEEDANCE", "Quality Exceedance"
		SENSOR_OFFLINE = "SENSOR_OFFLINE", "Sensor Offline"
		ABNORMAL_USAGE = "ABNORMAL_USAGE", "Abnormal Usage"

	severity = models.CharField(max_length=10, choices=Severity.choices)
	alert_type = models.CharField(max_length=30, choices=AlertType.choices)
	message = models.CharField(max_length=300)
	hostel = models.ForeignKey(
		"orgs.Hostel", on_delete=models.SET_NULL, related_name="alerts", null=True, blank=True
	)
	unit = models.ForeignKey("orgs.Unit", on_delete=models.SET_NULL, related_name="alerts", null=True, blank=True)
	asset = models.ForeignKey("iot.Asset", on_delete=models.SET_NULL, related_name="alerts", null=True, blank=True)
	sensor = models.ForeignKey("iot.Sensor", on_delete=models.SET_NULL, related_name="alerts", null=True, blank=True)
	started_at = models.DateTimeField()
	ended_at = models.DateTimeField(null=True, blank=True)
	acknowledged_at = models.DateTimeField(null=True, blank=True)
	acknowledged_by = models.ForeignKey(
		"auth.User",
		on_delete=models.SET_NULL,
		related_name="acknowledged_alerts",
		null=True,
		blank=True,
	)
	metadata = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-started_at"]
		indexes = [
			models.Index(fields=["severity", "alert_type"]),
			models.Index(fields=["hostel", "unit"]),
			models.Index(fields=["started_at"]),
			models.Index(fields=["acknowledged_at"]),
		]

	def __str__(self) -> str:
		return f"{self.severity} - {self.alert_type}: {self.message}"


class ForecastRun(models.Model):
	class ScopeType(models.TextChoices):
		CAMPUS = "CAMPUS", "Campus"
		HOSTEL = "HOSTEL", "Hostel"
		UNIT = "UNIT", "Unit"

	class Method(models.TextChoices):
		BASELINE = "BASELINE", "Baseline"
		AI = "AI", "AI"

	scope_type = models.CharField(max_length=10, choices=ScopeType.choices)
	hostel = models.ForeignKey(
		"orgs.Hostel",
		on_delete=models.SET_NULL,
		related_name="forecast_runs",
		null=True,
		blank=True,
	)
	unit = models.ForeignKey("orgs.Unit", on_delete=models.SET_NULL, related_name="forecast_runs", null=True, blank=True)
	method = models.CharField(max_length=10, choices=Method.choices, default=Method.BASELINE)
	horizon_hours = models.PositiveIntegerField(default=24)
	generated_at = models.DateTimeField(auto_now_add=True)
	notes = models.CharField(max_length=255, blank=True)

	class Meta:
		ordering = ["-generated_at"]
		indexes = [
			models.Index(fields=["scope_type", "generated_at"]),
			models.Index(fields=["hostel", "unit"]),
		]

	def __str__(self) -> str:
		return f"{self.scope_type} forecast ({self.method}) @ {self.generated_at:%Y-%m-%d %H:%M}"


class ForecastPoint(models.Model):
	forecast_run = models.ForeignKey("ops.ForecastRun", on_delete=models.CASCADE, related_name="points")
	timestamp = models.DateTimeField()
	predicted_value = models.DecimalField(max_digits=12, decimal_places=3)
	lower_bound = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
	upper_bound = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

	class Meta:
		ordering = ["timestamp"]
		constraints = [
			models.UniqueConstraint(fields=["forecast_run", "timestamp"], name="unique_forecast_point_timestamp"),
		]
		indexes = [
			models.Index(fields=["forecast_run", "timestamp"]),
		]

	def __str__(self) -> str:
		return f"{self.forecast_run_id} @ {self.timestamp:%Y-%m-%d %H:%M}"
