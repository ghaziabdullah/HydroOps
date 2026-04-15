import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Sum
from django.db.models.functions import TruncHour
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from iot.models import Asset, Reading, Sensor
from ops.models import Alert, ForecastPoint, ForecastRun
from orgs.selectors import get_hostel_or_none, get_unit_or_none, list_hostels, list_units


HOSTEL_TABS = [
	("overview", "Overview"),
	("usage", "Usage"),
	("units", "Units"),
	("tanks", "Tanks"),
	("pressure", "Pressure"),
	("quality", "Quality"),
	("alerts", "Alerts"),
	("forecast", "Forecast"),
]


def _float(value, default: float = 0.0) -> float:
	return float(value) if value is not None else default


def _default_curve(base: float, count: int = 8) -> list[float]:
	curve = []
	for idx in range(count):
		wave = 0.62 + (0.24 if idx in (2, 5) else 0) + (0.12 if idx == 4 else 0)
		curve.append(round(base * wave, 2))
	return curve


def _hourly_series(hostel, sensor_kind: str, since, fallback_base: float) -> tuple[list[str], list[float]]:
	points = (
		Reading.objects.filter(
			sensor__device__asset__hostel=hostel,
			sensor__kind=sensor_kind,
			timestamp__gte=since,
		)
		.annotate(bucket=TruncHour("timestamp"))
		.values("bucket")
		.annotate(avg_value=Avg("value"))
		.order_by("bucket")
	)

	if points:
		labels = [row["bucket"].strftime("%H:%M") for row in points]
		values = [round(_float(row["avg_value"]), 2) for row in points]
		return labels, values

	labels = []
	for idx in range(8):
		labels.append((since + timedelta(hours=idx * 3)).strftime("%H:%M"))
	return labels, _default_curve(fallback_base)


def _build_hostel_dashboard_context(hostel):
	now = timezone.now()
	since_24h = now - timedelta(hours=24)

	flow_readings = Reading.objects.filter(
		sensor__device__asset__hostel=hostel,
		sensor__kind=Sensor.SensorKind.FLOW,
	)
	pressure_readings = Reading.objects.filter(
		sensor__device__asset__hostel=hostel,
		sensor__kind=Sensor.SensorKind.PRESSURE,
	)

	today_usage_l = _float(flow_readings.filter(timestamp__gte=since_24h).aggregate(total=Sum("value"))["total"])
	current_flow_l_min = _float(flow_readings.order_by("-timestamp").values_list("value", flat=True).first())
	pressure_now = _float(pressure_readings.order_by("-timestamp").values_list("value", flat=True).first())
	night_flow = _float(
		flow_readings.filter(timestamp__gte=since_24h, timestamp__hour__lt=5).aggregate(avg=Avg("value"))["avg"]
	)

	level_avg = _float(
		Reading.objects.filter(
			sensor__device__asset__hostel=hostel,
			sensor__kind=Sensor.SensorKind.LEVEL,
			timestamp__gte=since_24h,
		).aggregate(avg=Avg("value"))["avg"],
		55.0,
	)
	ph_now = _float(
		Reading.objects.filter(
			sensor__device__asset__hostel=hostel,
			sensor__kind=Sensor.SensorKind.PH,
		).order_by("-timestamp").values_list("value", flat=True).first(),
		7.1,
	)
	turbidity_now = _float(
		Reading.objects.filter(
			sensor__device__asset__hostel=hostel,
			sensor__kind=Sensor.SensorKind.TURBIDITY,
		).order_by("-timestamp").values_list("value", flat=True).first(),
		3.0,
	)

	if pressure_now >= 2.6:
		pressure_health = "Good"
		pressure_health_color = "good"
	else:
		pressure_health = "Watch"
		pressure_health_color = "warn"

	if night_flow >= 22:
		night_indicator = "Warning - Orange"
		night_indicator_color = "warn"
	else:
		night_indicator = "Normal - Green"
		night_indicator_color = "good"

	if level_avg < 30:
		tank_risk = "High"
		tank_risk_color = "danger"
	elif level_avg < 50:
		tank_risk = "Medium"
		tank_risk_color = "warn"
	else:
		tank_risk = "Low"
		tank_risk_color = "good"

	quality_ok = 6.5 <= ph_now <= 8.5 and turbidity_now <= 5
	quality_status = "Optimal" if quality_ok else "Needs Attention"
	quality_color = "good" if quality_ok else "warn"

	usage_labels, usage_values = _hourly_series(hostel, Sensor.SensorKind.FLOW, since_24h, 4200)
	pressure_labels, pressure_values = _hourly_series(hostel, Sensor.SensorKind.PRESSURE, since_24h, 2.9)

	units = list_units(hostel_id=hostel.id)
	units_leaderboard = []
	for unit in units:
		unit_usage = _float(
			Reading.objects.filter(
				sensor__device__asset__unit=unit,
				sensor__kind=Sensor.SensorKind.FLOW,
				timestamp__gte=since_24h,
			).aggregate(total=Sum("value"))["total"]
		)
		predicted = max(unit_usage * 12.2, 3500)
		units_leaderboard.append(
			{
				"unit": unit,
				"label": unit.get_unit_type_display(),
				"sub": unit.code.replace("-", " ").title(),
				"current": round(unit_usage, 1),
				"predicted": round(predicted, 1),
			}
		)
	units_leaderboard.sort(key=lambda item: item["current"], reverse=True)
	units_leaderboard = units_leaderboard[:8]

	alerts = Alert.objects.filter(hostel=hostel).order_by("-started_at")[:12]
	critical_alerts = [alert for alert in alerts if alert.severity == Alert.Severity.CRITICAL]

	recommendations = []
	if night_flow >= 22:
		recommendations.append("Possible leak suspected in washroom clusters due to elevated night flow.")
	if level_avg < 50:
		recommendations.append("Schedule refill and inspect tank inlet valves.")
	if critical_alerts:
		recommendations.append("Acknowledge critical alerts and dispatch maintenance teams.")
	if not recommendations:
		recommendations.append("System is stable; keep monitoring forecast and quality trends.")

	tank_assets = Asset.objects.filter(hostel=hostel, asset_type=Asset.AssetType.TANK, is_active=True)
	tanks = []
	for asset in tank_assets:
		tank_level = _float(
			Reading.objects.filter(
				sensor__device__asset=asset,
				sensor__kind=Sensor.SensorKind.LEVEL,
			).order_by("-timestamp").values_list("value", flat=True).first(),
			level_avg,
		)
		if tank_level < 30:
			status = "Low"
		elif tank_level < 50:
			status = "Watch"
		else:
			status = "Healthy"
		tanks.append({"asset": asset, "level": round(tank_level, 1), "status": status})

	pressure_sensors = Sensor.objects.filter(
		device__asset__hostel=hostel,
		kind=Sensor.SensorKind.PRESSURE,
		is_active=True,
	).select_related("device__asset")
	pressure_rows = []
	for sensor in pressure_sensors:
		value = _float(sensor.readings.order_by("-timestamp").values_list("value", flat=True).first(), pressure_now)
		pressure_rows.append({"sensor": sensor, "value": round(value, 2)})

	quality_rows = []
	for kind, label, min_ok, max_ok in [
		(Sensor.SensorKind.PH, "pH", 6.5, 8.5),
		(Sensor.SensorKind.TURBIDITY, "Turbidity", 0, 5),
		(Sensor.SensorKind.TDS, "TDS", 0, 500),
	]:
		value = _float(
			Reading.objects.filter(
				sensor__device__asset__hostel=hostel,
				sensor__kind=kind,
			).order_by("-timestamp").values_list("value", flat=True).first(),
			0.0,
		)
		is_ok = min_ok <= value <= max_ok if max_ok else value >= min_ok
		quality_rows.append({"label": label, "value": round(value, 2), "status": "Good" if is_ok else "Warn"})

	forecast_run = ForecastRun.objects.filter(
		scope_type=ForecastRun.ScopeType.HOSTEL,
		hostel=hostel,
	).order_by("-generated_at").first()
	if forecast_run:
		forecast_points = list(
			ForecastPoint.objects.filter(forecast_run=forecast_run)
			.order_by("timestamp")
			.values("timestamp", "predicted_value")[:8]
		)
		forecast_labels = [point["timestamp"].strftime("%H:%M") for point in forecast_points]
		forecast_values = [round(_float(point["predicted_value"]), 2) for point in forecast_points]
	else:
		forecast_labels = usage_labels
		forecast_values = [round(value * 1.1, 2) for value in usage_values]

	return {
		"today_usage_l": round(today_usage_l, 1),
		"current_flow_l_min": round(current_flow_l_min, 1),
		"pressure_now": round(pressure_now, 2),
		"pressure_health": pressure_health,
		"pressure_health_color": pressure_health_color,
		"night_indicator": night_indicator,
		"night_indicator_color": night_indicator_color,
		"tank_risk": tank_risk,
		"tank_risk_color": tank_risk_color,
		"quality_status": quality_status,
		"quality_color": quality_color,
		"usage_labels": usage_labels,
		"usage_values": usage_values,
		"pressure_labels": pressure_labels,
		"pressure_values": pressure_values,
		"forecast_labels": forecast_labels,
		"forecast_values": forecast_values,
		"units_leaderboard": units_leaderboard,
		"alerts": alerts,
		"critical_alerts": critical_alerts,
		"recommendations": recommendations,
		"tanks": tanks,
		"pressure_rows": pressure_rows,
		"quality_rows": quality_rows,
	}


@login_required
def units_explorer_page_view(request):
	hostel_id = request.GET.get("hostel_id")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	hostels = list_hostels()
	if parsed_hostel_id is None and hostels.exists():
		parsed_hostel_id = hostels.first().id

	active_hostel = get_hostel_or_none(parsed_hostel_id) if parsed_hostel_id else None
	units = list_units(hostel_id=parsed_hostel_id)
	return render(
		request,
		"orgs/units_explorer_page.html",
		{
			"page_title": "Main Campus Units Detail Dashboard",
			"hostels": hostels,
			"active_hostel": active_hostel,
			"units": units,
		},
	)


@login_required
def hostel_detail_page_view(request, hostel_id: int, tab: str = "overview"):
	hostel = get_hostel_or_none(hostel_id)
	if hostel is None:
		raise Http404("Hostel not found")

	allowed_tabs = {slug for slug, _ in HOSTEL_TABS}
	active_tab = tab if tab in allowed_tabs else "overview"
	dashboard = _build_hostel_dashboard_context(hostel)
	chart_payload = {
		"usage": {"labels": dashboard["usage_labels"], "values": dashboard["usage_values"]},
		"pressure": {"labels": dashboard["pressure_labels"], "values": dashboard["pressure_values"]},
		"forecast": {"labels": dashboard["forecast_labels"], "values": dashboard["forecast_values"]},
	}

	return render(
		request,
		"orgs/hostel_detail_page.html",
		{
			"page_title": "Main Campus Hostel Detail Dashboard",
			"hostel": hostel,
			"tabs": HOSTEL_TABS,
			"active_tab": active_tab,
			"chart_data_json": json.dumps(chart_payload),
			**dashboard,
		},
	)


@login_required
def unit_detail_page_view(request, unit_id: int):
	unit = get_unit_or_none(unit_id)
	if unit is None:
		raise Http404("Unit not found")

	return render(request, "orgs/unit_detail_page.html", {"page_title": "Unit Detail", "unit": unit})


@login_required
def hostel_list_api_view(request):
	hostels = list_hostels()
	data = [
		{
			"id": hostel.id,
			"name": hostel.name,
			"code": hostel.code,
			"campus_name": hostel.campus_name,
			"is_active": hostel.is_active,
		}
		for hostel in hostels
	]
	return JsonResponse({"results": data})


@login_required
def hostel_detail_api_view(request, hostel_id: int):
	hostel = get_hostel_or_none(hostel_id)
	if hostel is None:
		raise Http404("Hostel not found")

	return JsonResponse(
		{
			"id": hostel.id,
			"name": hostel.name,
			"code": hostel.code,
			"campus_name": hostel.campus_name,
			"is_active": hostel.is_active,
			"units_count": hostel.units.count(),
		}
	)


@login_required
def unit_list_api_view(request):
	hostel_id = request.GET.get("hostel_id")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	units = list_units(hostel_id=parsed_hostel_id)
	data = [
		{
			"id": unit.id,
			"name": unit.name,
			"code": unit.code,
			"unit_type": unit.unit_type,
			"hostel": {
				"id": unit.hostel_id,
				"name": unit.hostel.name,
				"code": unit.hostel.code,
			},
			"is_active": unit.is_active,
		}
		for unit in units
	]
	return JsonResponse({"results": data})


@login_required
def unit_detail_api_view(request, unit_id: int):
	unit = get_unit_or_none(unit_id)
	if unit is None:
		raise Http404("Unit not found")

	return JsonResponse(
		{
			"id": unit.id,
			"name": unit.name,
			"code": unit.code,
			"unit_type": unit.unit_type,
			"hostel": {
				"id": unit.hostel_id,
				"name": unit.hostel.name,
				"code": unit.hostel.code,
			},
			"is_active": unit.is_active,
		}
	)
