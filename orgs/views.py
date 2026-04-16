import json
import math
import re
from collections import defaultdict
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


def _extract_floor_number(unit) -> int | None:
	if unit is None:
		return None

	code_match = re.search(r"floor-(\d{2})", unit.code)
	if code_match:
		return int(code_match.group(1))

	cluster_match = re.search(r"f(\d{2})-cluster-[ab]", unit.code)
	if cluster_match:
		return int(cluster_match.group(1))

	name_match = re.search(r"floor\s*(\d+)", unit.name.lower())
	if name_match:
		return int(name_match.group(1))

	return None


def _extract_cluster_suffix(unit) -> str:
	cluster_match = re.search(r"cluster-([ab])", unit.code)
	if cluster_match:
		return cluster_match.group(1).upper()

	name_match = re.search(r"cluster\s*([ab])", unit.name.lower())
	if name_match:
		return name_match.group(1).upper()

	return "A"


def _risk_label_for_cluster(*, critical_alerts: int, alerts: int, night_ratio: float, flow_rate_l_min: float) -> tuple[str, str]:
	if critical_alerts > 0 or (alerts >= 2 and night_ratio >= 0.62) or flow_rate_l_min >= 18:
		return "Critical", "critical"
	if alerts > 0 or night_ratio >= 0.72 or flow_rate_l_min >= 13:
		return "Warning", "warning"
	return "Low Risk", "safe"


def _prediction_text_for_cluster(*, risk_color: str, night_ratio: float, usage_24h_l: float) -> str:
	if risk_color == "critical":
		return "Anomalous night-flow behavior; possible leakage signature"
	if risk_color == "warning":
		if night_ratio >= 0.5:
			return "Elevated off-peak usage detected; inspect fixtures"
		return "Usage pattern drifting upward; monitor next 6 hours"
	if usage_24h_l < 220:
		return "Low usage expected"
	return "Stable behavior expected"


def _minutes_ago_label(now, dt) -> str:
	if dt is None:
		return "No recent telemetry"
	minutes = max(0, int((now - dt).total_seconds() // 60))
	if minutes < 1:
		return "Updated just now"
	if minutes == 1:
		return "Updated 1 min ago"
	if minutes < 60:
		return f"Updated {minutes} min ago"
	hours = minutes // 60
	if hours == 1:
		return "Updated 1 hr ago"
	return f"Updated {hours} hrs ago"


def _sparkline_points(values: list[float], width: int = 116, height: int = 34) -> str:
	if not values:
		return ""

	v_min = min(values)
	v_max = max(values)
	range_v = (v_max - v_min) or 1.0
	step_x = width / max(len(values) - 1, 1)

	coords = []
	for idx, value in enumerate(values):
		x = round(idx * step_x, 2)
		y = round(height - ((value - v_min) / range_v) * height, 2)
		coords.append(f"{x},{y}")
	return " ".join(coords)


def _generate_synthetic_trend(base: float, count: int = 8) -> list[float]:
	values = []
	for idx in range(count):
		wave = math.sin((idx / max(count - 1, 1)) * math.pi * 2) * (base * 0.12)
		shape = (0.88 + (0.1 if idx in (2, 5) else 0.0)) * base
		values.append(max(0.05, round(shape + wave, 3)))
	return values


def _build_hostel_dashboard_context(hostel):
	now = timezone.now()
	since_24h = now - timedelta(hours=24)
	hostel_temp_c = _float(
		Reading.objects.filter(
			sensor__device__asset__hostel=active_hostel,
			sensor__kind=Sensor.SensorKind.TEMPERATURE,
		)
		.order_by("-timestamp")
		.values_list("value", flat=True)
		.first(),
		24.0,
	)

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
	units = list(list_units(hostel_id=parsed_hostel_id))

	floor_units = [unit for unit in units if unit.unit_type == unit.UnitType.FLOOR]
	cluster_units = [unit for unit in units if unit.unit_type == unit.UnitType.CLUSTER]

	clusters_by_floor: dict[int, list] = defaultdict(list)
	for unit in cluster_units:
		floor_no = _extract_floor_number(unit)
		if floor_no is None:
			continue
		clusters_by_floor[floor_no].append(unit)

	now = timezone.now()
	since_24h = now - timedelta(hours=24)
	hostel_temp_c = 24.0
	if active_hostel is not None:
		hostel_temp_c = _float(
			Reading.objects.filter(
				sensor__device__asset__hostel=active_hostel,
				sensor__kind=Sensor.SensorKind.TEMPERATURE,
			)
			.order_by("-timestamp")
			.values_list("value", flat=True)
			.first(),
			24.0,
		)

	floor_cards = []
	for floor in sorted(floor_units, key=lambda item: _extract_floor_number(item) or 999):
		floor_no = _extract_floor_number(floor)
		if floor_no is None:
			continue

		clusters = sorted(
			clusters_by_floor.get(floor_no, []),
			key=lambda item: _extract_cluster_suffix(item),
		)
		cluster_cards = []
		for cluster in clusters[:2]:
			flow_readings_qs = Reading.objects.filter(
				sensor__device__asset__unit=cluster,
				sensor__kind=Sensor.SensorKind.FLOW,
			)
			latest_reading_ts = flow_readings_qs.order_by("-timestamp").values_list("timestamp", flat=True).first()
			trend_points_raw = list(
				flow_readings_qs.filter(timestamp__gte=since_24h)
				.annotate(bucket=TruncHour("timestamp"))
				.values("bucket")
				.annotate(avg_value=Avg("value"))
				.order_by("bucket")
			)
			trend_values = [round(_float(item["avg_value"]), 3) for item in trend_points_raw[-8:]]
			trend_source = "Live"

			flow_rate_l_min = _float(
				flow_readings_qs.order_by("-timestamp").values_list("value", flat=True).first(),
				4.2,
			)
			usage_24h_l = _float(
				flow_readings_qs.filter(timestamp__gte=since_24h).aggregate(total=Sum("value"))["total"],
				240.0,
			)
			night_flow_l_min = _float(
				flow_readings_qs.filter(
					timestamp__gte=since_24h,
					timestamp__hour__lt=5,
				).aggregate(avg=Avg("value"))["avg"],
				flow_rate_l_min * 0.6,
			)
			day_flow_l_min = _float(
				flow_readings_qs.filter(
					timestamp__gte=since_24h,
					timestamp__hour__gte=6,
					timestamp__hour__lt=22,
				).aggregate(avg=Avg("value"))["avg"],
				max(flow_rate_l_min, 0.1),
			)
			night_ratio = night_flow_l_min / max(day_flow_l_min, 0.1)

			if len(trend_values) < 2:
				historical_values = [
					round(_float(value), 3)
					for value in reversed(list(flow_readings_qs.order_by("-timestamp").values_list("value", flat=True)[:8]))
				]
				if len(historical_values) >= 2:
					trend_values = historical_values
					trend_source = "Historical"
				else:
					trend_values = _generate_synthetic_trend(max(flow_rate_l_min, 1.0))
					trend_source = "Generated"
			has_trend_data = len(trend_values) >= 2

			cluster_alerts_qs = Alert.objects.filter(unit=cluster, ended_at__isnull=True)
			alerts_count = cluster_alerts_qs.count()
			critical_count = cluster_alerts_qs.filter(severity=Alert.Severity.CRITICAL).count()

			risk_label, risk_color = _risk_label_for_cluster(
				critical_alerts=critical_count,
				alerts=alerts_count,
				night_ratio=night_ratio,
				flow_rate_l_min=flow_rate_l_min,
			)
			if night_ratio >= 0.58:
				behavior = "Persistent off-peak flow"
			elif usage_24h_l < 220:
				behavior = "Conservative use pattern"
			else:
				behavior = "Balanced daily cycle"

			trend_delta_pct = 0.0
			trend_label = "No Trend"
			if has_trend_data:
				trend_delta_pct = ((trend_values[-1] - trend_values[0]) / max(trend_values[0], 0.1)) * 100
				if trend_delta_pct >= 12:
					trend_label = "Rising"
				elif trend_delta_pct <= -10:
					trend_label = "Dropping"
				else:
					trend_label = "Stable"
			cluster_cards.append(
				{
					"unit": cluster,
					"suffix": _extract_cluster_suffix(cluster),
					"flow_rate": round(flow_rate_l_min * 60, 1),
					"usage_24h": round(usage_24h_l, 1),
					"night_flow": round(night_flow_l_min * 60, 1),
					"alerts": alerts_count,
					"critical_alerts": critical_count,
					"behavior": behavior,
					"last_updated": _minutes_ago_label(now, latest_reading_ts),
					"trend_label": trend_label,
					"trend_delta_pct": round(trend_delta_pct, 1),
					"trend_source": trend_source,
					"sparkline_points": _sparkline_points(trend_values),
					"high_watermark_l_hr": round(max(trend_values) * 60, 1) if trend_values else 0,
					"temperature_c": round(hostel_temp_c + (0.2 if _extract_cluster_suffix(cluster) == "B" else -0.1), 1),
					"risk_label": risk_label,
					"risk_color": risk_color,
					"prediction": _prediction_text_for_cluster(
						risk_color=risk_color,
						night_ratio=night_ratio,
						usage_24h_l=usage_24h_l,
					),
				}
			)

		if not cluster_cards:
			continue

		avg_flow = sum(card["flow_rate"] for card in cluster_cards) / len(cluster_cards)
		floor_alerts = sum(card["alerts"] for card in cluster_cards)
		if any(card["risk_color"] == "critical" for card in cluster_cards):
			floor_status, floor_status_color = "Critical", "critical"
		elif any(card["risk_color"] == "warning" for card in cluster_cards):
			floor_status, floor_status_color = "Warning", "warning"
		else:
			floor_status, floor_status_color = "Low Risk", "safe"

		floor_cards.append(
			{
				"floor": floor,
				"floor_number": floor_no,
				"title": floor.name,
				"status": floor_status,
				"status_color": floor_status_color,
				"average_flow_l_hr": round(avg_flow, 1),
				"alerts": floor_alerts,
				"clusters": cluster_cards,
			}
		)

	active_alerts = 0
	if active_hostel is not None:
		active_alerts = Alert.objects.filter(hostel=active_hostel, ended_at__isnull=True).count()

	hostel_units_summary = {
		"total_floors": len(floor_cards),
		"total_clusters": sum(len(card["clusters"]) for card in floor_cards),
		"active_alerts": active_alerts,
		"total_floors_desc": "Floors mapped in this hostel",
		"total_clusters_desc": "Washroom clusters monitored",
		"active_alerts_desc": "Open alerts needing action",
	}
	return render(
		request,
		"orgs/units_explorer_page.html",
		{
			"page_title": "Main Campus Units Detail Dashboard",
			"hostels": hostels,
			"active_hostel": active_hostel,
			"units": units,
			"floor_cards": floor_cards,
			"hostel_units_summary": hostel_units_summary,
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
