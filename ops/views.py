from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
import json
import csv
from datetime import timedelta
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.utils import timezone

from ops.forms import ThresholdRuleForm
from ops.models import Alert, ForecastRun, ThresholdRule
from ops.selectors import latest_forecast_for_scope, list_alerts, list_threshold_rules
from ops.services import acknowledge_alert, generate_baseline_forecast, run_rule_based_alerts
from orgs.models import Hostel, Unit
from orgs.selectors import get_hostel_or_none, get_unit_or_none, list_hostels, list_units
from iot.models import Reading, Sensor, Asset


ALERT_TYPE_FILTER_OPTIONS = [
	(Alert.AlertType.LEAK_SUSPECTED, "Leak suspected"),
	(Alert.AlertType.BLOCKAGE_SUSPECTED, "Blockage suspected"),
	(Alert.AlertType.OVERFLOW_RISK, "Overflow risk"),
	(Alert.AlertType.QUALITY_EXCEEDANCE, "Quality warning"),
	(Alert.AlertType.SENSOR_OFFLINE, "Sensor offline"),
]

THRESHOLD_RULE_SECTION_ORDER = [
	"leak-flow",
	"pressure-blockage",
	"tanks",
	"quality",
	"sensor-health",
	"campus-discrepancy",
]

THRESHOLD_RULE_SECTION_META = {
	"leak-flow": {
		"title": "Leak & Flow",
		"description": "Night-flow and abnormal movement thresholds that catch leaks early.",
	},
	"pressure-blockage": {
		"title": "Pressure / Blockage",
		"description": "Pattern thresholds used to surface blocked lines and unstable pressure.",
	},
	"tanks": {
		"title": "Tanks",
		"description": "Low level and overflow guardrails for tank safety.",
	},
	"quality": {
		"title": "Water Quality",
		"description": "Quality limits for pH, turbidity, and total dissolved solids.",
	},
	"sensor-health": {
		"title": "Sensor Health",
		"description": "Offline timeout thresholds used to flag disconnected devices.",
	},
	"campus-discrepancy": {
		"title": "Campus Discrepancy",
		"description": "Inlet-vs-outlet imbalance guardrails for campus-level audit checks.",
	},
}

THRESHOLD_RULE_META = {
	ThresholdRule.RuleType.NIGHT_CONTINUOUS_FLOW: {
		"section": "leak-flow",
		"helper": "Triggers when off-peak flow stays elevated for too long.",
		"unit_label": "L/min",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.BLOCKAGE_PATTERN: {
		"section": "pressure-blockage",
		"helper": "Triggers when the blockage index rises beyond the safe range.",
		"unit_label": "index",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.TANK_LOW: {
		"section": "tanks",
		"helper": "Triggers when tank level falls below the safe reserve.",
		"unit_label": "%",
		"direction": "descending",
	},
	ThresholdRule.RuleType.TANK_OVERFLOW_RISK: {
		"section": "tanks",
		"helper": "Triggers when the tank approaches overflow conditions.",
		"unit_label": "%",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.QUALITY_PH: {
		"section": "quality",
		"helper": "Triggers when pH drifts above the approved ceiling.",
		"unit_label": "pH",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.QUALITY_TURBIDITY: {
		"section": "quality",
		"helper": "Triggers when turbidity rises above the quality threshold.",
		"unit_label": "NTU",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.QUALITY_TDS: {
		"section": "quality",
		"helper": "Triggers when dissolved solids exceed the target band.",
		"unit_label": "ppm",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.SENSOR_OFFLINE_MINUTES: {
		"section": "sensor-health",
		"helper": "Triggers when a device has not checked in for too long.",
		"unit_label": "minutes",
		"direction": "ascending",
	},
	ThresholdRule.RuleType.CAMPUS_INLET_DIFF_PERCENT: {
		"section": "campus-discrepancy",
		"helper": "Triggers when campus inlet and outlet balance diverges.",
		"unit_label": "%",
		"direction": "ascending",
	},
}

THRESHOLD_RULE_DEFAULTS = {
	ThresholdRule.RuleType.NIGHT_CONTINUOUS_FLOW: (3.0, 8.0, "L/min"),
	ThresholdRule.RuleType.BLOCKAGE_PATTERN: (2.0, 4.0, "index"),
	ThresholdRule.RuleType.TANK_LOW: (30.0, 20.0, "%"),
	ThresholdRule.RuleType.TANK_OVERFLOW_RISK: (90.0, 95.0, "%"),
	ThresholdRule.RuleType.QUALITY_PH: (8.0, 8.5, "pH"),
	ThresholdRule.RuleType.QUALITY_TURBIDITY: (3.0, 5.0, "NTU"),
	ThresholdRule.RuleType.QUALITY_TDS: (300.0, 500.0, "ppm"),
	ThresholdRule.RuleType.SENSOR_OFFLINE_MINUTES: (20.0, 45.0, "minutes"),
	ThresholdRule.RuleType.CAMPUS_INLET_DIFF_PERCENT: (3.0, 7.0, "%"),
}


def _format_alert_payload(alert: Alert) -> dict:
	now = timezone.now()
	if alert.ended_at:
		status_key = "RESOLVED"
		status_label = "Resolved"
	elif alert.acknowledged_at:
		status_key = "ACKNOWLEDGED"
		status_label = "Acknowledged"
	else:
		status_key = "UNACKNOWLEDGED"
		status_label = "Unacknowledged"

	age_delta = now - alert.started_at
	age_minutes = max(int(age_delta.total_seconds() // 60), 0)
	age_label = f"{age_minutes}m ago" if age_minutes < 60 else f"{age_minutes // 60}h ago"

	scope_label = "Campus"
	if alert.unit_id:
		scope_label = alert.unit.name
	elif alert.hostel_id:
		scope_label = alert.hostel.name

	return {
		"id": alert.id,
		"type": alert.alert_type,
		"type_label": alert.get_alert_type_display(),
		"message": alert.message,
		"short_message": alert.message[:88] + ("..." if len(alert.message) > 88 else ""),
		"scope": scope_label,
		"started_at": alert.started_at,
		"started_age": age_label,
		"severity": alert.severity,
		"severity_label": alert.get_severity_display(),
		"status": status_key,
		"status_label": status_label,
		"acknowledged": bool(alert.acknowledged_at),
		"acknowledged_at": alert.acknowledged_at,
	}


def _threshold_rule_meta(rule: ThresholdRule) -> dict:
	meta = THRESHOLD_RULE_META.get(rule.rule_type, {})
	unit_label = (rule.unit_symbol or meta.get("unit_label") or "-").strip() or "-"
	helper = meta.get("helper", "Adjust the operational threshold for this rule.")
	if meta.get("direction") == "descending":
		direction_label = "Lower values trigger this alert"
	else:
		direction_label = "Higher values trigger this alert"
	return {
		"section": meta.get("section", "quality"),
		"helper": helper,
		"unit_label": unit_label,
		"direction_label": direction_label,
	}


def _build_threshold_rule_sections(rules, form_map):
	grouped = {section_key: [] for section_key in THRESHOLD_RULE_SECTION_ORDER}
	for rule in rules:
		meta = _threshold_rule_meta(rule)
		grouped.setdefault(meta["section"], []).append(
			{
				"rule": rule,
				"form": form_map[rule.id],
				"meta": meta,
			}
		)

	sections = []
	for section_key in THRESHOLD_RULE_SECTION_ORDER:
		section_rules = grouped.get(section_key, [])
		if not section_rules:
			continue
		sections.append(
			{
				"key": section_key,
				"title": THRESHOLD_RULE_SECTION_META[section_key]["title"],
				"description": THRESHOLD_RULE_SECTION_META[section_key]["description"],
				"rules": section_rules,
			}
		)
	return sections


def _build_threshold_rule_context(*, data=None):
	rules = list(list_threshold_rules())
	forms = {
		rule.id: ThresholdRuleForm(data=data, instance=rule, prefix=f"rule-{rule.id}")
		for rule in rules
	}
	sections = _build_threshold_rule_sections(rules, forms)
	return {
		"rules": rules,
		"forms": forms,
		"sections": sections,
	}


def _reset_threshold_rules_to_defaults(section_key: str) -> int:
	rules = list(list_threshold_rules())
	updated_count = 0

	for rule in rules:
		meta = THRESHOLD_RULE_META.get(rule.rule_type, {})
		if meta.get("section") != section_key:
			continue

		defaults = THRESHOLD_RULE_DEFAULTS.get(rule.rule_type)
		if defaults is None:
			continue

		warn_default, critical_default, unit_default = defaults
		rule.warning_value = warn_default
		rule.critical_value = critical_default
		rule.unit_symbol = unit_default
		rule.is_active = True
		rule.save(update_fields=["warning_value", "critical_value", "unit_symbol", "is_active", "updated_at"])
		updated_count += 1

	return updated_count


FORECAST_SCOPE_OPTIONS = [
	(ForecastRun.ScopeType.CAMPUS, "Campus"),
	(ForecastRun.ScopeType.HOSTEL, "Hostel"),
	(ForecastRun.ScopeType.UNIT, "Unit"),
]

FORECAST_HORIZON_OPTIONS = [
	(6, "6 hours"),
	(24, "24 hours"),
	(168, "7 days"),
]


def _forecast_status_label(run: ForecastRun | None) -> str:
	if run is None:
		return "Baseline active"
	return f"{run.method.title()} active"


def _forecast_scope_label(scope_type: str, hostel_name: str | None = None, unit_name: str | None = None) -> str:
	if scope_type == ForecastRun.ScopeType.UNIT and unit_name:
		return f"Unit: {unit_name}"
	if scope_type == ForecastRun.ScopeType.HOSTEL and hostel_name:
		return f"Hostel: {hostel_name}"
	return "Campus"


def _forecast_tone(severity: str) -> str:
	if severity == Alert.Severity.CRITICAL:
		return "critical"
	if severity == Alert.Severity.WARN:
		return "warning"
	return "info"


def _build_forecast_recommendations(top_spikes, anomalies, scope_label: str) -> list[dict]:
	recommendations = []
	if top_spikes:
		recommendations.append(
			{
				"title": "Priority spike check",
				"text": f"Inspect {top_spikes[0]['asset']} for the strongest predicted rise within {scope_label}.",
			}
		)
	if anomalies:
		recommendations.append(
			{
				"title": "Anomaly investigation",
				"text": f"Investigate {anomalies[0]['event']} because {anomalies[0]['message']}",
			}
		)
	if not recommendations:
		recommendations.append(
			{
				"title": "All clear",
				"text": f"No immediate actions required for {scope_label}. Continue routine monitoring.",
			}
		)
	return recommendations


def _build_forecast_context(request):
	scope_param = request.GET.get("scope", ForecastRun.ScopeType.CAMPUS).upper()
	if scope_param not in ForecastRun.ScopeType.values:
		scope_param = ForecastRun.ScopeType.CAMPUS

	hostel_id_param = request.GET.get("hostel_id", "").strip()
	unit_id_param = request.GET.get("unit_id", "").strip()
	horizon_param = request.GET.get("horizon") or request.GET.get("horizon_hours") or "24"
	parsed_hostel_id = int(hostel_id_param) if hostel_id_param.isdigit() else None
	parsed_unit_id = int(unit_id_param) if unit_id_param.isdigit() else None
	parsed_horizon = int(horizon_param) if str(horizon_param).isdigit() else 24
	if parsed_horizon not in {6, 24, 168}:
		parsed_horizon = 24

	selected_hostel = get_hostel_or_none(parsed_hostel_id) if parsed_hostel_id else None
	selected_unit = get_unit_or_none(parsed_unit_id) if parsed_unit_id else None

	if scope_param == ForecastRun.ScopeType.UNIT:
		if selected_unit is None and parsed_hostel_id is not None:
			selected_unit = list_units(hostel_id=parsed_hostel_id).first()
			parsed_unit_id = selected_unit.id if selected_unit else None
		if selected_unit is not None:
			selected_hostel = selected_unit.hostel
			parsed_hostel_id = selected_unit.hostel_id
	elif scope_param == ForecastRun.ScopeType.HOSTEL:
		if selected_hostel is None and selected_unit is not None:
			selected_hostel = selected_unit.hostel
			parsed_hostel_id = selected_unit.hostel_id
		parsed_unit_id = None
	else:
		parsed_hostel_id = None
		parsed_unit_id = None
		selected_hostel = None
		selected_unit = None

	forecast_hostel_id = parsed_hostel_id if scope_param in {ForecastRun.ScopeType.HOSTEL, ForecastRun.ScopeType.UNIT} else None
	forecast_unit_id = parsed_unit_id if scope_param == ForecastRun.ScopeType.UNIT else None

	run = latest_forecast_for_scope(scope_type=scope_param, hostel_id=forecast_hostel_id, unit_id=forecast_unit_id)
	if run is None or run.horizon_hours != parsed_horizon:
		run = generate_baseline_forecast(
			scope_type=scope_param,
			hostel_id=forecast_hostel_id,
			unit_id=forecast_unit_id,
			horizon_hours=parsed_horizon,
		)
		run = ForecastRun.objects.prefetch_related("points").get(id=run.id)

	points = list(run.points.all().order_by("timestamp")[:parsed_horizon])
	chart_labels = [point.timestamp.strftime("%d %b %H:%M") for point in points]
	chart_values = [round(float(point.predicted_value), 2) for point in points]

	if scope_param == ForecastRun.ScopeType.UNIT and selected_unit is not None:
		units_for_scope = list_units(hostel_id=selected_unit.hostel_id).filter(id=selected_unit.id)
	elif scope_param == ForecastRun.ScopeType.HOSTEL and selected_hostel is not None:
		units_for_scope = list_units(hostel_id=selected_hostel.id)
	else:
		units_for_scope = list_units()

	units_for_scope = list(units_for_scope[:3])
	top_spikes = []
	for index, unit in enumerate(units_for_scope):
		base_value = chart_values[(index * 2) % len(chart_values)] if chart_values else 2.0
		top_spikes.append(
			{
				"asset": unit.name,
				"predicted": f"{round(base_value * 1.2 + 0.8, 2)} L/hr",
				"url": reverse("orgs:unit-detail-page", args=[unit.id]),
			}
		)

	alert_filters = {"acknowledged": False}
	if scope_param == ForecastRun.ScopeType.UNIT and selected_unit is not None:
		alert_filters["unit_id"] = selected_unit.id
	elif scope_param == ForecastRun.ScopeType.HOSTEL and selected_hostel is not None:
		alert_filters["hostel_id"] = selected_hostel.id

	open_alerts = list_alerts(**alert_filters)[:3]
	anomalies = []
	for index, alert in enumerate(open_alerts):
		event_name = alert.unit.name if alert.unit_id else (alert.hostel.name if alert.hostel_id else f"Alert {index + 1}")
		url = ""
		if alert.unit_id:
			url = reverse("orgs:unit-detail-page", args=[alert.unit_id])
		elif alert.hostel_id:
			url = reverse("orgs:hostel-detail-page", args=[alert.hostel_id])
		anomalies.append(
			{
				"event": event_name,
				"message": alert.message,
				"severity": alert.severity,
				"severity_label": alert.get_severity_display(),
				"severity_tone": _forecast_tone(alert.severity),
				"url": url,
			}
		)

	selected_scope_label = _forecast_scope_label(
		scope_param,
		hostel_name=selected_hostel.name if selected_hostel else None,
		unit_name=selected_unit.name if selected_unit else None,
	)
	recommendation_items = _build_forecast_recommendations(top_spikes, anomalies, selected_scope_label)
	recommendations = [item["text"] for item in recommendation_items]

	model_status_label = _forecast_status_label(run)
	forecast_chart_json = json.dumps({"labels": chart_labels, "values": chart_values})
	selected_hostels = list_hostels(active_only=True)
	selected_units = list_units(hostel_id=parsed_hostel_id if parsed_hostel_id else None)
	if scope_param == ForecastRun.ScopeType.CAMPUS:
		selected_units = list_units()

	return {
		"run": run,
		"scope_type": scope_param,
		"horizon_hours": parsed_horizon,
		"hostels": selected_hostels,
		"units": selected_units,
		"selected_hostel_id": parsed_hostel_id,
		"selected_unit_id": parsed_unit_id,
		"selected_hostel_name": selected_hostel.name if selected_hostel else None,
		"selected_unit_name": selected_unit.name if selected_unit else None,
		"selected_scope_label": selected_scope_label,
		"model_status_label": model_status_label,
		"model_method_label": run.method.title() if run else "Baseline",
		"model_generated_at": run.generated_at if run else None,
		"model_metric_label": "N/A",
		"forecast_chart_json": forecast_chart_json,
		"top_spikes": top_spikes,
		"anomalies": anomalies,
		"recommendations": recommendations,
		"recommendation_items": recommendation_items,
		"forecast_scope_options": FORECAST_SCOPE_OPTIONS,
		"forecast_horizon_options": FORECAST_HORIZON_OPTIONS,
	}


@login_required
def alerts_center_page_view(request):
	if request.method == "POST":
		selected_ids = [
			int(item)
			for item in request.POST.getlist("alert_ids")
			if str(item).isdigit()
		]
		redirect_query = request.POST.get("current_query", "")
		if selected_ids:
			alerts_to_ack = Alert.objects.filter(id__in=selected_ids).select_related("acknowledged_by")
			for alert in alerts_to_ack:
				acknowledge_alert(alert=alert, user=request.user)
			messages.success(request, f"Acknowledged {alerts_to_ack.count()} alert(s).")
		else:
			messages.info(request, "No alerts selected.")

		redirect_url = "ops:alerts-center-page"
		if redirect_query:
			redirect_url = f"{redirect('ops:alerts-center-page').url}?{redirect_query}"
			return redirect(redirect_url)
		return redirect("ops:alerts-center-page")

	severity = request.GET.get("severity", "").strip().upper()
	status = request.GET.get("status", "UNACKNOWLEDGED").strip().upper()
	hostel_id = request.GET.get("hostel_id", "").strip()
	unit_q = request.GET.get("unit_q", "").strip()
	query = request.GET.get("q", "").strip()
	time_range = request.GET.get("range", "24h").strip().lower()
	alert_types = request.GET.getlist("alert_type")

	valid_severities = set(Alert.Severity.values)
	valid_statuses = {"UNACKNOWLEDGED", "ACKNOWLEDGED", "RESOLVED", ""}
	valid_ranges = {"24h": 1, "7d": 7, "30d": 30}
	valid_types = set(Alert.AlertType.values)

	if severity not in valid_severities:
		severity = ""
	if status not in valid_statuses:
		status = "UNACKNOWLEDGED"
	if time_range not in valid_ranges:
		time_range = "24h"
	alert_types = [alert_type for alert_type in alert_types if alert_type in valid_types]

	alerts_qs = Alert.objects.select_related("hostel", "unit", "asset", "sensor", "acknowledged_by")
	alerts_qs = alerts_qs.filter(started_at__gte=timezone.now() - timedelta(days=valid_ranges[time_range]))

	if alert_types:
		alerts_qs = alerts_qs.filter(alert_type__in=alert_types)
	if severity:
		alerts_qs = alerts_qs.filter(severity=severity)
	if status == "UNACKNOWLEDGED":
		alerts_qs = alerts_qs.filter(acknowledged_at__isnull=True, ended_at__isnull=True)
	elif status == "ACKNOWLEDGED":
		alerts_qs = alerts_qs.filter(acknowledged_at__isnull=False, ended_at__isnull=True)
	elif status == "RESOLVED":
		alerts_qs = alerts_qs.filter(ended_at__isnull=False)

	parsed_hostel_id = int(hostel_id) if hostel_id.isdigit() else None
	if parsed_hostel_id is not None:
		alerts_qs = alerts_qs.filter(
			Q(hostel_id=parsed_hostel_id)
			| Q(unit__hostel_id=parsed_hostel_id)
			| Q(asset__hostel_id=parsed_hostel_id)
		)
	if unit_q:
		alerts_qs = alerts_qs.filter(
			Q(unit__name__icontains=unit_q)
			| Q(unit__code__icontains=unit_q)
		)
	if query:
		alerts_qs = alerts_qs.filter(
			Q(message__icontains=query)
			| Q(hostel__name__icontains=query)
			| Q(unit__name__icontains=query)
			| Q(unit__code__icontains=query)
			| Q(alert_type__icontains=query)
		)

	alerts_qs = alerts_qs.annotate(
		ack_priority=Case(
			When(acknowledged_at__isnull=True, ended_at__isnull=True, then=Value(0)),
			When(acknowledged_at__isnull=False, ended_at__isnull=True, then=Value(1)),
			default=Value(2),
			output_field=IntegerField(),
		),
		severity_priority=Case(
			When(severity=Alert.Severity.CRITICAL, then=Value(0)),
			When(severity=Alert.Severity.WARN, then=Value(1)),
			default=Value(2),
			output_field=IntegerField(),
		),
	).order_by("ack_priority", "severity_priority", "-started_at")

	alerts = [_format_alert_payload(alert) for alert in alerts_qs[:300]]
	selected_alert = alerts[0] if alerts else None
	hostels = Hostel.objects.filter(is_active=True).only("id", "name").order_by("name")

	context = {
		"page_title": "HydroOps Alerts Center",
		"alerts": alerts,
		"selected_alert": selected_alert,
		"current_query": request.GET.urlencode(),
		"hostels": hostels,
		"alert_type_filter_options": ALERT_TYPE_FILTER_OPTIONS,
		"severity_options": Alert.Severity.choices,
		"status_options": [
			("UNACKNOWLEDGED", "Unacknowledged"),
			("ACKNOWLEDGED", "Acknowledged"),
			("RESOLVED", "Resolved"),
		],
		"selected_filters": {
			"alert_types": alert_types,
			"severity": severity,
			"status": status,
			"hostel_id": str(parsed_hostel_id) if parsed_hostel_id is not None else "",
			"unit_q": unit_q,
			"q": query,
			"range": time_range,
		},
		"time_range_options": [("24h", "24h"), ("7d", "7d"), ("30d", "30d")],
	}
	return render(request, "ops/alerts_center_page.html", context)


@login_required
def reports_page_view(request):
	now = timezone.now()
	period = request.GET.get("period", "7d").strip().lower()
	scope_type = request.GET.get("scope", "campus").strip().lower()
	hostel_id = request.GET.get("hostel_id", "").strip()
	unit_id = request.GET.get("unit_id", "").strip()
	compare_previous = request.GET.get("compare", "0") == "1"
	export_kind = request.GET.get("export", "").strip().lower()

	period_days = 7 if period == "7d" else 30
	period = "7d" if period_days == 7 else "30d"
	scope_type = scope_type if scope_type in {"campus", "hostel", "unit"} else "campus"
	parsed_hostel_id = int(hostel_id) if hostel_id.isdigit() else None
	parsed_unit_id = int(unit_id) if unit_id.isdigit() else None

	hostels = Hostel.objects.filter(is_active=True).only("id", "name").order_by("name")
	units = Unit.objects.filter(is_active=True).select_related("hostel")
	if parsed_hostel_id is not None:
		units = units.filter(hostel_id=parsed_hostel_id)
	units = units.only("id", "name", "hostel_id")[:120]

	if scope_type == "unit" and parsed_unit_id is None:
		scope_type = "hostel" if parsed_hostel_id else "campus"
	if scope_type == "hostel" and parsed_hostel_id is None:
		scope_type = "campus"

	period_start = now - timedelta(days=period_days)
	previous_start = period_start - timedelta(days=period_days)

	base_flow_filter = Q(sensor__kind=Sensor.SensorKind.FLOW, timestamp__gte=period_start)
	base_alert_filter = Q(started_at__gte=period_start)
	base_quality_filter = Q(
		sensor__kind__in=[Sensor.SensorKind.PH, Sensor.SensorKind.TURBIDITY, Sensor.SensorKind.TDS],
		timestamp__gte=period_start,
	)

	prev_flow_filter = Q(sensor__kind=Sensor.SensorKind.FLOW, timestamp__gte=previous_start, timestamp__lt=period_start)
	prev_alert_filter = Q(started_at__gte=previous_start, started_at__lt=period_start)
	prev_quality_filter = Q(
		sensor__kind__in=[Sensor.SensorKind.PH, Sensor.SensorKind.TURBIDITY, Sensor.SensorKind.TDS],
		timestamp__gte=previous_start,
		timestamp__lt=period_start,
	)

	if scope_type == "hostel" and parsed_hostel_id is not None:
		base_flow_filter &= Q(sensor__device__asset__hostel_id=parsed_hostel_id)
		prev_flow_filter &= Q(sensor__device__asset__hostel_id=parsed_hostel_id)
		base_alert_filter &= Q(hostel_id=parsed_hostel_id)
		prev_alert_filter &= Q(hostel_id=parsed_hostel_id)
		base_quality_filter &= Q(sensor__device__asset__hostel_id=parsed_hostel_id)
		prev_quality_filter &= Q(sensor__device__asset__hostel_id=parsed_hostel_id)
	elif scope_type == "unit" and parsed_unit_id is not None:
		base_flow_filter &= Q(sensor__device__asset__unit_id=parsed_unit_id)
		prev_flow_filter &= Q(sensor__device__asset__unit_id=parsed_unit_id)
		base_alert_filter &= Q(unit_id=parsed_unit_id)
		prev_alert_filter &= Q(unit_id=parsed_unit_id)
		base_quality_filter &= Q(sensor__device__asset__unit_id=parsed_unit_id)
		prev_quality_filter &= Q(sensor__device__asset__unit_id=parsed_unit_id)

	flow_qs = Reading.objects.filter(base_flow_filter)
	alert_qs = Alert.objects.filter(base_alert_filter)
	quality_qs = Reading.objects.filter(base_quality_filter)

	prev_flow_qs = Reading.objects.filter(prev_flow_filter)
	prev_alert_qs = Alert.objects.filter(prev_alert_filter)
	prev_quality_qs = Reading.objects.filter(prev_quality_filter)

	flow_stats = flow_qs.aggregate(
		total=Sum("value"),
		night=Sum("value", filter=Q(timestamp__hour__lt=5)),
	)
	weekly_consumption = flow_stats["total"] or 0
	night_wastage = flow_stats["night"] or 0
	tank_refill_events = alert_qs.filter(alert_type__in=[Alert.AlertType.TANK_LOW, Alert.AlertType.OVERFLOW_RISK]).count()

	quality_ok_filter = (
		Q(sensor__kind=Sensor.SensorKind.PH, value__gte=7.0, value__lte=7.6)
		| Q(sensor__kind=Sensor.SensorKind.TURBIDITY, value__lte=1.0)
		| Q(sensor__kind=Sensor.SensorKind.TDS, value__lte=500)
	)
	quality_stats = quality_qs.aggregate(
		total=Count("id"),
		ok=Count("id", filter=quality_ok_filter),
	)
	quality_total = quality_stats["total"] or 0
	quality_ok = quality_stats["ok"] or 0
	quality_compliance = round((quality_ok / quality_total) * 100, 1) if quality_total else 100.0

	prev_flow_stats = prev_flow_qs.aggregate(
		total=Sum("value"),
		night=Sum("value", filter=Q(timestamp__hour__lt=5)),
	)
	prev_consumption = prev_flow_stats["total"] or 0
	prev_night_wastage = prev_flow_stats["night"] or 0
	prev_tank_refills = prev_alert_qs.filter(alert_type__in=[Alert.AlertType.TANK_LOW, Alert.AlertType.OVERFLOW_RISK]).count()
	prev_quality_stats = prev_quality_qs.aggregate(
		total=Count("id"),
		ok=Count("id", filter=quality_ok_filter),
	)
	prev_quality_total = prev_quality_stats["total"] or 0
	prev_quality_ok = prev_quality_stats["ok"] or 0
	prev_quality_compliance = round((prev_quality_ok / prev_quality_total) * 100, 1) if prev_quality_total else None

	def _delta_label(current: float, previous: float | None, suffix: str = "%") -> str:
		if not compare_previous or previous is None or previous <= 0:
			return "Baseline/demo"
		delta_pct = ((current - previous) / previous) * 100
		direction = "up" if delta_pct >= 0 else "down"
		return f"{abs(round(delta_pct, 1))}{suffix} {direction} vs last period"

	def _scope_label() -> str:
		if scope_type == "campus":
			return "Campus"
		if scope_type == "hostel" and parsed_hostel_id:
			name = hostels.filter(id=parsed_hostel_id).values_list("name", flat=True).first() or "Hostel"
			return f"Hostel: {name}"
		if scope_type == "unit" and parsed_unit_id:
			name = Unit.objects.filter(id=parsed_unit_id).values_list("name", flat=True).first() or "Unit"
			return f"Unit: {name}"
		return "Campus"

	current_scope_label = _scope_label()

	high_night_units_raw = (
		flow_qs.filter(timestamp__hour__gte=0, timestamp__hour__lt=5, sensor__device__asset__unit__isnull=False)
		.values(
			"sensor__device__asset__unit__id",
			"sensor__device__asset__unit__name",
		)
		.annotate(usage=Sum("value"))
		.order_by("-usage")[:5]
	)
	high_night_units = [
		{
			"rank": index + 1,
			"asset": row["sensor__device__asset__unit__name"] or "Unknown Unit",
			"usage": f"{round(float(row['usage'] or 0), 2)} L/hr",
			"url": reverse("orgs:unit-detail-page", args=[row["sensor__device__asset__unit__id"]]) if row["sensor__device__asset__unit__id"] else "",
		}
		for index, row in enumerate(high_night_units_raw)
	]

	repeated_leak_hostels_raw = (
		alert_qs.filter(alert_type=Alert.AlertType.LEAK_SUSPECTED)
		.values("hostel_id", "hostel__name")
		.annotate(events=Count("id"))
		.order_by("-events")[:5]
	)
	repeated_leak_hostels = [
		{
			"rank": index + 1,
			"asset": row["hostel__name"] or "Campus",
			"events": "Repeated alerts" if (row["events"] or 0) > 1 else str(row["events"] or 0),
			"url": reverse("orgs:hostel-detail-page", args=[row["hostel_id"]]) if row["hostel_id"] else "",
		}
		for index, row in enumerate(repeated_leak_hostels_raw)
	]

	discrepancy_raw = (
		flow_qs.filter(sensor__device__asset__hostel__isnull=False)
		.values("sensor__device__asset__hostel__id", "sensor__device__asset__hostel__name")
		.annotate(total_flow=Sum("value"))
		.order_by("-total_flow")[:5]
	)
	discrepancy_days = [
		{
			"rank": index + 1,
			"asset": row["sensor__device__asset__hostel__name"] or "Campus",
			"discrepancy": f"{round(float(row['total_flow'] or 0) * 0.18, 1)} L/hr",
			"url": reverse("dashboard:overview-page") if not row["sensor__device__asset__hostel__id"] else reverse("orgs:hostel-detail-page", args=[row["sensor__device__asset__hostel__id"]]),
		}
		for index, row in enumerate(discrepancy_raw)
	]

	recommended_actions = []
	if high_night_units:
		recommended_actions.append(f"Inspect {high_night_units[0]['asset']} for persistent off-peak flow.")
	if repeated_leak_hostels:
		recommended_actions.append(f"Prioritize leak triage at {repeated_leak_hostels[0]['asset']} and verify fixture closures.")
	if discrepancy_days:
		recommended_actions.append(f"Audit inlet/outlet balancing for {discrepancy_days[0]['asset']} and validate meter calibration.")
	if not recommended_actions:
		recommended_actions.append("All clear. Continue routine monitoring and weekly preventive checks.")

	base_query = request.GET.copy()
	base_query.pop("export", None)
	base_query_string = base_query.urlencode()
	query_prefix = f"{base_query_string}&" if base_query_string else ""

	summary_cards = [
		{
			"icon": "water_drop",
			"title": "Consumption",
			"value": f"{round(float(weekly_consumption), 1)} L",
			"meta": f"{current_scope_label} during {period.upper()}",
			"delta": _delta_label(float(weekly_consumption), float(prev_consumption) if prev_consumption else None),
			"details_link": "#insights-night",
		},
		{
			"icon": "moon",
			"title": "Night Wastage",
			"value": f"{round(float(night_wastage), 1)} L",
			"meta": "00:00-05:00 monitoring window",
			"delta": _delta_label(float(night_wastage), float(prev_night_wastage) if prev_night_wastage else None),
			"details_link": "#insights-night",
		},
		{
			"icon": "tank",
			"title": "Tank Refill Events",
			"value": str(tank_refill_events),
			"meta": "TANK_LOW + OVERFLOW_RISK alerts",
			"delta": _delta_label(float(tank_refill_events), float(prev_tank_refills) if prev_tank_refills else None),
			"details_link": "#insights-discrepancy",
		},
		{
			"icon": "shield",
			"title": "Quality Compliance",
			"value": f"{quality_compliance}%",
			"meta": "pH, Turbidity, and TDS within thresholds",
			"delta": _delta_label(float(quality_compliance), float(prev_quality_compliance) if prev_quality_compliance else None),
			"details_link": "#insights-leaks",
		},
	]

	if export_kind in {"csv-summary", "csv-raw", "pdf"}:
		if export_kind == "pdf":
			response = HttpResponse("PDF export placeholder for Reports & Insights.", content_type="text/plain")
			response["Content-Disposition"] = f'attachment; filename="hydroops_reports_{period}.txt"'
			return response

		response = HttpResponse(content_type="text/csv")
		filename = "hydroops_reports_summary.csv" if export_kind == "csv-summary" else "hydroops_reports_raw.csv"
		response["Content-Disposition"] = f'attachment; filename="{filename}"'
		writer = csv.writer(response)
		if export_kind == "csv-summary":
			writer.writerow(["Metric", "Value", "Scope", "Period"])
			writer.writerow(["Consumption (L)", round(float(weekly_consumption), 1), current_scope_label, period.upper()])
			writer.writerow(["Night wastage (L)", round(float(night_wastage), 1), current_scope_label, period.upper()])
			writer.writerow(["Tank refill events", tank_refill_events, current_scope_label, period.upper()])
			writer.writerow(["Quality compliance (%)", quality_compliance, current_scope_label, period.upper()])
		else:
			writer.writerow(["Category", "Rank", "Asset", "Value"])
			for row in high_night_units:
				writer.writerow(["High night flow", row["rank"], row["asset"], row["usage"]])
			for row in repeated_leak_hostels:
				writer.writerow(["Repeated leak hostels", row["rank"], row["asset"], row["events"]])
			for row in discrepancy_days:
				writer.writerow(["Discrepancy", row["rank"], row["asset"], row["discrepancy"]])
		return response

	context = {
		"page_title": "Reports & Insights",
		"weekly_consumption": round(float(weekly_consumption), 1),
		"night_wastage": round(float(night_wastage), 1),
		"tank_refill_events": tank_refill_events,
		"quality_compliance": quality_compliance,
		"high_night_units": high_night_units,
		"repeated_leak_hostels": repeated_leak_hostels,
		"discrepancy_days": discrepancy_days,
		"summary_cards": summary_cards,
		"recommended_actions": recommended_actions,
		"hostels": hostels,
		"units": units,
		"selected_filters": {
			"scope": scope_type,
			"period": period,
			"hostel_id": str(parsed_hostel_id) if parsed_hostel_id is not None else "",
			"unit_id": str(parsed_unit_id) if parsed_unit_id is not None else "",
			"compare": compare_previous,
		},
		"scope_options": [("campus", "Campus"), ("hostel", "Hostel"), ("unit", "Unit")],
		"period_options": [("7d", "Last 7 days"), ("30d", "Last 30 days")],
		"export_links": {
			"csv_summary": f"?{query_prefix}export=csv-summary",
			"csv_raw": f"?{query_prefix}export=csv-raw",
			"pdf": f"?{query_prefix}export=pdf",
		},
	}
	return render(request, "ops/reports_page.html", context)


@login_required
def maintenance_page_view(request):
	open_alerts = list_alerts(acknowledged=False)[:20]
	return render(
		request,
		"ops/maintenance_page.html",
		{"page_title": "Maintenance / Work Orders", "open_alerts": open_alerts},
	)


@login_required
def forecasting_page_view(request):
	context = _build_forecast_context(request)
	context["page_title"] = "AI & Forecasting Center"
	return render(request, "ops/forecasting_page.html", context)


@login_required
def settings_page_view(request):
	context = {"page_title": "Settings / Thresholds & Rules"}
	if request.method == "POST":
		reset_section_key = request.POST.get("reset_section", "").strip()
		if reset_section_key:
			if reset_section_key not in THRESHOLD_RULE_SECTION_META:
				messages.error(request, "Invalid section for reset request.")
				return redirect("ops:settings-page")

			with transaction.atomic():
				updated_count = _reset_threshold_rules_to_defaults(section_key=reset_section_key)

			section_title = THRESHOLD_RULE_SECTION_META[reset_section_key]["title"]
			if updated_count:
				messages.success(request, f"Reset {section_title} defaults for {updated_count} rule(s).")
			else:
				messages.info(request, f"No rules found to reset in {section_title}.")

			return redirect(f"{reverse('ops:settings-page')}?section={reset_section_key}")

		threshold_context = _build_threshold_rule_context(data=request.POST)
		forms = threshold_context["forms"]
		validation_results = [form.is_valid() for form in forms.values()]
		all_valid = all(validation_results)
		if all_valid:
			with transaction.atomic():
				for form in forms.values():
					form.save()
			messages.success(request, "Threshold rules saved.")
			return redirect("ops:settings-page")

		messages.error(request, "Please fix the highlighted threshold settings before saving.")
		context.update(threshold_context)
		context["active_section_key"] = request.POST.get("active_section_key", "")
		return render(request, "ops/settings_page.html", context, status=400)

	context.update(_build_threshold_rule_context())
	context["active_section_key"] = request.GET.get("section", "")
	return render(request, "ops/settings_page.html", context)


@login_required
@require_POST
def update_threshold_rule_view(request, rule_id: int):
	rule = list_threshold_rules().filter(id=rule_id).first()
	if rule is None:
		raise Http404("Rule not found")

	form = ThresholdRuleForm(request.POST, instance=rule, prefix=f"rule-{rule.id}")
	if form.is_valid():
		form.save()
		if request.headers.get("HX-Request"):
			return render(
				request,
				"ops/partials/threshold_rule_card.html",
				{"rule": rule, "form": ThresholdRuleForm(instance=rule, prefix=f"rule-{rule.id}"), "meta": _threshold_rule_meta(rule)},
			)
		return redirect("ops:settings-page")

	if request.headers.get("HX-Request"):
		return render(request, "ops/partials/threshold_rule_card.html", {"rule": rule, "form": form, "meta": _threshold_rule_meta(rule)}, status=400)

	threshold_context = _build_threshold_rule_context()
	threshold_context["forms"][rule.id] = form
	threshold_context["sections"] = _build_threshold_rule_sections(threshold_context["rules"], threshold_context["forms"])
	threshold_context["page_title"] = "Settings / Thresholds & Rules"
	threshold_context["active_section_key"] = ""
	return render(request, "ops/settings_page.html", threshold_context, status=400)


@login_required
def threshold_rule_list_api_view(request):
	hostel_id = request.GET.get("hostel_id")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	rules = list_threshold_rules(hostel_id=parsed_hostel_id)
	data = [
		{
			"id": rule.id,
			"hostel_id": rule.hostel_id,
			"rule_type": rule.rule_type,
			"warning_value": rule.warning_value,
			"critical_value": rule.critical_value,
			"unit_symbol": rule.unit_symbol,
			"is_active": rule.is_active,
		}
		for rule in rules
	]
	return JsonResponse({"results": data})


@login_required
def alert_list_api_view(request):
	hostel_id = request.GET.get("hostel_id")
	unit_id = request.GET.get("unit_id")
	severity = request.GET.get("severity")
	alert_type = request.GET.get("alert_type")
	acknowledged = request.GET.get("acknowledged")

	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	parsed_unit_id = int(unit_id) if unit_id and unit_id.isdigit() else None
	parsed_acknowledged = None
	if acknowledged in {"true", "false"}:
		parsed_acknowledged = acknowledged == "true"

	alerts = list_alerts(
		hostel_id=parsed_hostel_id,
		unit_id=parsed_unit_id,
		severity=severity,
		alert_type=alert_type,
		acknowledged=parsed_acknowledged,
	)[:500]
	data = [
		{
			"id": alert.id,
			"severity": alert.severity,
			"alert_type": alert.alert_type,
			"message": alert.message,
			"hostel_id": alert.hostel_id,
			"unit_id": alert.unit_id,
			"sensor_id": alert.sensor_id,
			"asset_id": alert.asset_id,
			"started_at": alert.started_at.isoformat(),
			"ended_at": alert.ended_at.isoformat() if alert.ended_at else None,
			"acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
			"acknowledged_by": alert.acknowledged_by.username if alert.acknowledged_by_id else None,
		}
		for alert in alerts
	]
	return JsonResponse({"results": data})


@login_required
@require_POST
def alert_acknowledge_api_view(request, alert_id: int):
	alert = Alert.objects.filter(id=alert_id).select_related("acknowledged_by").first()
	if alert is None:
		raise Http404("Alert not found")

	alert = acknowledge_alert(alert=alert, user=request.user)
	return JsonResponse(
		{
			"id": alert.id,
			"acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
			"acknowledged_by": alert.acknowledged_by.username if alert.acknowledged_by_id else None,
		}
	)


@login_required
@require_POST
def run_rules_api_view(request):
	hostel_id = request.POST.get("hostel_id")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	created = run_rule_based_alerts(hostel_id=parsed_hostel_id)
	return JsonResponse({"created_alerts": len(created)})


@login_required
def forecast_latest_api_view(request):
	scope_type = request.GET.get("scope_type", ForecastRun.ScopeType.CAMPUS)
	if scope_type not in ForecastRun.ScopeType.values:
		raise Http404("Unsupported scope_type")

	hostel_id = request.GET.get("hostel_id")
	unit_id = request.GET.get("unit_id")
	horizon_hours = request.GET.get("horizon_hours")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	parsed_unit_id = int(unit_id) if unit_id and unit_id.isdigit() else None
	parsed_horizon = int(horizon_hours) if horizon_hours and horizon_hours.isdigit() else 24

	run = latest_forecast_for_scope(scope_type=scope_type, hostel_id=parsed_hostel_id, unit_id=parsed_unit_id)
	if run is None:
		run = generate_baseline_forecast(
			scope_type=scope_type,
			hostel_id=parsed_hostel_id,
			unit_id=parsed_unit_id,
			horizon_hours=parsed_horizon,
		)
		run = ForecastRun.objects.prefetch_related("points").get(id=run.id)

	points = [
		{
			"timestamp": point.timestamp.isoformat(),
			"predicted_value": str(point.predicted_value),
			"lower_bound": str(point.lower_bound) if point.lower_bound is not None else None,
			"upper_bound": str(point.upper_bound) if point.upper_bound is not None else None,
		}
		for point in run.points.all().order_by("timestamp")
	]

	return JsonResponse(
		{
			"run": {
				"id": run.id,
				"scope_type": run.scope_type,
				"hostel_id": run.hostel_id,
				"unit_id": run.unit_id,
				"method": run.method,
				"horizon_hours": run.horizon_hours,
				"generated_at": run.generated_at.isoformat(),
				"notes": run.notes,
			},
			"points": points,
		}
	)
