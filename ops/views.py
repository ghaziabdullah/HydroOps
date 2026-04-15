from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
import json
from datetime import timedelta
from django.db.models import Count, Sum, Q
from django.utils import timezone

from ops.forms import ThresholdRuleForm
from ops.models import Alert, ForecastRun
from ops.selectors import latest_forecast_for_scope, list_alerts, list_threshold_rules
from ops.services import acknowledge_alert, generate_baseline_forecast, run_rule_based_alerts
from orgs.models import Hostel, Unit
from iot.models import Reading, Sensor, Asset


@login_required
def alerts_center_page_view(request):
	alerts = list_alerts()[:100]
	return render(request, "ops/alerts_center_page.html", {"page_title": "HydroOps Alerts Center", "alerts": alerts})


@login_required
def reports_page_view(request):
	now = timezone.now()
	today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
	week_start = now - timedelta(days=7)

	weekly_consumption = (
		Reading.objects.filter(sensor__kind=Sensor.SensorKind.FLOW, timestamp__gte=week_start)
		.aggregate(v=Sum("value"))["v"]
		or 0
	)

	night_wastage = (
		Reading.objects.filter(
			sensor__kind=Sensor.SensorKind.FLOW,
			timestamp__gte=week_start,
			timestamp__hour__gte=0,
			timestamp__hour__lt=5,
		)
		.aggregate(v=Sum("value"))["v"]
		or 0
	)

	tank_refill_events = Alert.objects.filter(
		alert_type__in=[Alert.AlertType.TANK_LOW, Alert.AlertType.OVERFLOW_RISK],
		started_at__gte=week_start,
	).count()

	quality_total = Reading.objects.filter(
		sensor__kind__in=[Sensor.SensorKind.PH, Sensor.SensorKind.TURBIDITY, Sensor.SensorKind.TDS],
		timestamp__gte=week_start,
	).count()
	quality_ok = Reading.objects.filter(
		Q(sensor__kind=Sensor.SensorKind.PH, value__gte=7.0, value__lte=7.6)
		| Q(sensor__kind=Sensor.SensorKind.TURBIDITY, value__lte=1.0)
		| Q(sensor__kind=Sensor.SensorKind.TDS, value__lte=500),
		timestamp__gte=week_start,
	).count()
	quality_compliance = round((quality_ok / quality_total) * 100, 1) if quality_total else 100

	high_night_units_raw = (
		Reading.objects.filter(
			sensor__kind=Sensor.SensorKind.FLOW,
			timestamp__gte=week_start,
			timestamp__hour__gte=0,
			timestamp__hour__lt=5,
			sensor__device__asset__unit__isnull=False,
		)
		.values("sensor__device__asset__unit__name")
		.annotate(usage=Sum("value"))
		.order_by("-usage")[:5]
	)
	high_night_units = [
		{
			"rank": index + 1,
			"asset": row["sensor__device__asset__unit__name"] or "Unknown Unit",
			"usage": f"{round(float(row['usage'] or 0), 2)} L/hr",
		}
		for index, row in enumerate(high_night_units_raw)
	]

	repeated_leak_hostels_raw = (
		Alert.objects.filter(alert_type=Alert.AlertType.LEAK_SUSPECTED, started_at__gte=week_start)
		.values("hostel__name")
		.annotate(events=Count("id"))
		.order_by("-events")[:5]
	)
	repeated_leak_hostels = [
		{
			"rank": index + 1,
			"asset": row["hostel__name"] or "Campus",
			"events": "Repeated alerts" if (row["events"] or 0) > 1 else str(row["events"] or 0),
		}
		for index, row in enumerate(repeated_leak_hostels_raw)
	]

	discrepancy_raw = (
		Reading.objects.filter(
			sensor__kind=Sensor.SensorKind.FLOW,
			timestamp__gte=today_start,
			sensor__device__asset__hostel__isnull=False,
		)
		.values("sensor__device__asset__hostel__name")
		.annotate(total_flow=Sum("value"))
		.order_by("-total_flow")[:5]
	)
	discrepancy_days = [
		{
			"rank": index + 1,
			"asset": row["sensor__device__asset__hostel__name"] or "Campus",
			"discrepancy": f"{round(float(row['total_flow'] or 0) * 0.18, 1)} L/hr",
		}
		for index, row in enumerate(discrepancy_raw)
	]

	context = {
		"page_title": "Reports & Insights",
		"weekly_consumption": round(float(weekly_consumption), 1),
		"night_wastage": round(float(night_wastage), 1),
		"tank_refill_events": tank_refill_events,
		"quality_compliance": quality_compliance,
		"high_night_units": high_night_units,
		"repeated_leak_hostels": repeated_leak_hostels,
		"discrepancy_days": discrepancy_days,
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
	hostel_id = request.GET.get("hostel_id")
	unit_id = request.GET.get("unit_id")
	horizon_hours = request.GET.get("horizon_hours")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	parsed_unit_id = int(unit_id) if unit_id and unit_id.isdigit() else None
	parsed_horizon = int(horizon_hours) if horizon_hours and horizon_hours.isdigit() else 24

	scope_type = ForecastRun.ScopeType.CAMPUS
	if parsed_unit_id:
		scope_type = ForecastRun.ScopeType.UNIT
	elif parsed_hostel_id:
		scope_type = ForecastRun.ScopeType.HOSTEL

	run = latest_forecast_for_scope(
		scope_type=scope_type,
		hostel_id=parsed_hostel_id,
		unit_id=parsed_unit_id,
	)
	if run is None:
		run = generate_baseline_forecast(
			scope_type=scope_type,
			hostel_id=parsed_hostel_id,
			unit_id=parsed_unit_id,
			horizon_hours=parsed_horizon,
		)
		run = ForecastRun.objects.prefetch_related("points").get(id=run.id)

	points = list(run.points.all().order_by("timestamp")[:parsed_horizon])
	chart_labels = [point.timestamp.strftime("%H:%M") for point in points]
	chart_values = [round(float(point.predicted_value), 1) for point in points]

	selected_hostel_name = None
	selected_unit_name = None
	if parsed_hostel_id:
		selected_hostel_name = Hostel.objects.filter(id=parsed_hostel_id).values_list("name", flat=True).first()
	if parsed_unit_id:
		selected_unit_name = Unit.objects.filter(id=parsed_unit_id).values_list("name", flat=True).first()

	units_for_spikes = Unit.objects.filter(is_active=True).select_related("hostel")[:3]
	top_spikes = []
	for index, unit in enumerate(units_for_spikes):
		base_value = chart_values[(index * 2) % len(chart_values)] if chart_values else 2.0
		top_spikes.append(
			{
				"asset": unit.name,
				"predicted": f"{round(base_value / 2.6 + 1.1, 2)} L/hr",
			}
		)

	open_alerts = list_alerts(acknowledged=False)[:3]
	anomalies = []
	for index, alert in enumerate(open_alerts):
		event_name = alert.unit.name if alert.unit_id else (alert.hostel.name if alert.hostel_id else f"Cluster {index}")
		anomalies.append(
			{
				"event": event_name,
				"message": alert.message,
			}
		)

	recommendations = [
		"Review setpoints",
		"Review setpoints for washroom clusters",
		"Review setpoints for current pressure thresholds",
	]

	context = {
		"page_title": "AI & Forecasting Center",
		"run": run,
		"scope_type": scope_type,
		"horizon_hours": parsed_horizon,
		"selected_hostel_name": selected_hostel_name,
		"selected_unit_name": selected_unit_name,
		"forecast_chart_json": json.dumps({"labels": chart_labels, "values": chart_values}),
		"top_spikes": top_spikes,
		"anomalies": anomalies,
		"recommendations": recommendations,
	}
	return render(request, "ops/forecasting_page.html", context)


@login_required
def settings_page_view(request):
	rules = list_threshold_rules()
	forms = []
	for rule in rules:
		forms.append({"rule": rule, "form": ThresholdRuleForm(instance=rule, prefix=f"rule-{rule.id}")})
	return render(request, "ops/settings_page.html", {"page_title": "Settings / Thresholds & Rules", "forms": forms})


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
				{"rule": rule, "form": ThresholdRuleForm(instance=rule, prefix=f"rule-{rule.id}")},
			)
		return redirect("ops:settings-page")

	if request.headers.get("HX-Request"):
		return render(request, "ops/partials/threshold_rule_card.html", {"rule": rule, "form": form}, status=400)

	forms = [{"rule": item, "form": ThresholdRuleForm(instance=item, prefix=f"rule-{item.id}")} for item in list_threshold_rules()]
	for index, item in enumerate(forms):
		if item["rule"].id == rule.id:
			forms[index]["form"] = form
	return render(request, "ops/settings_page.html", {"page_title": "Settings / Thresholds & Rules", "forms": forms}, status=400)


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
