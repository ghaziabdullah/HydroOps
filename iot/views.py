from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Avg
from django.db.models.functions import TruncHour
import json
from datetime import timedelta

from iot.selectors import list_assets, list_readings, list_sensors
from iot.models import Asset, Reading, Sensor
from ops.models import Alert


@login_required
def water_quality_page_view(request):
	now = timezone.now()
	since_24h = now - timedelta(hours=24)

	def latest_value(kind: str, fallback: float) -> float:
		latest = (
			Reading.objects.filter(sensor__kind=kind)
			.order_by("-timestamp")
			.values_list("value", flat=True)
			.first()
		)
		return float(latest) if latest is not None else fallback

	ph_value = latest_value(Sensor.SensorKind.PH, 7.2)
	turbidity_value = latest_value(Sensor.SensorKind.TURBIDITY, 0.8)
	tds_value = latest_value(Sensor.SensorKind.TDS, 250.0)
	temperature_value = latest_value(Sensor.SensorKind.TEMPERATURE, 22.0)

	quality_alerts = Alert.objects.filter(
		alert_type=Alert.AlertType.QUALITY_EXCEEDANCE,
		ended_at__isnull=True,
	).count()

	def build_trend(kind: str, fallback_values: list[float]) -> dict:
		rows = list(
			Reading.objects.filter(sensor__kind=kind, timestamp__gte=since_24h)
			.annotate(hour=TruncHour("timestamp"))
			.values("hour")
			.annotate(avg_value=Avg("value"))
			.order_by("hour")
		)
		if not rows:
			labels = ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00"]
			return {"labels": labels, "values": fallback_values}

		labels = [item["hour"].strftime("%H:%M") for item in rows]
		values = [round(float(item["avg_value"]), 3) for item in rows]
		return {"labels": labels, "values": values}

	ph_trend = build_trend(Sensor.SensorKind.PH, [7.3, 7.15, 7.1, 7.12, 7.28, 7.08, 7.14])
	turbidity_trend = build_trend(Sensor.SensorKind.TURBIDITY, [0.25, 0.22, 0.2, 0.35, 0.26, 0.31, 0.46])

	quality_assets = Asset.objects.filter(asset_type=Asset.AssetType.QUALITY_POINT).select_related("hostel")[:8]
	table_rows: list[dict] = []
	for asset in quality_assets:
		def sensor_latest_for_asset(kind: str, fallback: float) -> float:
			value = (
				Reading.objects.filter(sensor__device__asset=asset, sensor__kind=kind)
				.order_by("-timestamp")
				.values_list("value", flat=True)
				.first()
			)
			return float(value) if value is not None else fallback

		row_ph = sensor_latest_for_asset(Sensor.SensorKind.PH, ph_value)
		row_turbidity = sensor_latest_for_asset(Sensor.SensorKind.TURBIDITY, turbidity_value)
		row_tds = sensor_latest_for_asset(Sensor.SensorKind.TDS, tds_value)
		row_temp = sensor_latest_for_asset(Sensor.SensorKind.TEMPERATURE, temperature_value)

		is_compliant = (
			7.0 <= row_ph <= 7.6
			and row_turbidity <= 1.0
			and row_tds <= 500
			and 12 <= row_temp <= 35
		)

		table_rows.append(
			{
				"hostel": asset.hostel.name,
				"asset": asset.name,
				"ph": round(row_ph, 2),
				"turbidity": round(row_turbidity, 2),
				"tds": round(row_tds, 1),
				"temperature": round(row_temp, 1),
				"status": "Compliance" if is_compliant else "Warning",
			}
		)

	overall_status = "Optimal" if quality_alerts == 0 else "Attention"

	context = {
		"page_title": "Water Quality Dashboard",
		"overall_status": overall_status,
		"ph_value": round(ph_value, 2),
		"turbidity_value": round(turbidity_value, 2),
		"tds_value": round(tds_value, 1),
		"temperature_value": round(temperature_value, 1),
		"quality_alerts": quality_alerts,
		"table_rows": table_rows,
		"ph_trend_json": json.dumps(ph_trend),
		"turbidity_trend_json": json.dumps(turbidity_trend),
	}
	return render(request, "iot/water_quality_page.html", context)


@login_required
def asset_list_api_view(request):
	hostel_id = request.GET.get("hostel_id")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	assets = list_assets(hostel_id=parsed_hostel_id)
	data = [
		{
			"id": asset.id,
			"name": asset.name,
			"code": asset.code,
			"asset_type": asset.asset_type,
			"hostel": {"id": asset.hostel_id, "name": asset.hostel.name, "code": asset.hostel.code},
			"unit": {"id": asset.unit_id, "name": asset.unit.name} if asset.unit_id else None,
		}
		for asset in assets
	]
	return JsonResponse({"results": data})


@login_required
def sensor_list_api_view(request):
	hostel_id = request.GET.get("hostel_id")
	parsed_hostel_id = int(hostel_id) if hostel_id and hostel_id.isdigit() else None
	kind = request.GET.get("kind")
	sensors = list_sensors(hostel_id=parsed_hostel_id, kind=kind)

	data = [
		{
			"id": sensor.id,
			"name": sensor.name,
			"code": sensor.code,
			"kind": sensor.kind,
			"unit_symbol": sensor.unit_symbol,
			"status": sensor.status,
			"device": {
				"id": sensor.device_id,
				"name": sensor.device.name,
				"serial_number": sensor.device.serial_number,
			},
			"asset": {
				"id": sensor.device.asset_id,
				"name": sensor.device.asset.name,
				"hostel": sensor.device.asset.hostel.name,
			},
		}
		for sensor in sensors
	]
	return JsonResponse({"results": data})


@login_required
def reading_list_api_view(request):
	sensor_id = request.GET.get("sensor_id")
	parsed_sensor_id = int(sensor_id) if sensor_id and sensor_id.isdigit() else None
	start_at = parse_datetime(request.GET.get("start_at", "")) if request.GET.get("start_at") else None
	end_at = parse_datetime(request.GET.get("end_at", "")) if request.GET.get("end_at") else None

	readings = list_readings(sensor_id=parsed_sensor_id, start_at=start_at, end_at=end_at)[:1000]
	data = [
		{
			"id": reading.id,
			"sensor_id": reading.sensor_id,
			"sensor_code": reading.sensor.code,
			"timestamp": reading.timestamp.isoformat(),
			"value": str(reading.value),
			"ingest_source": reading.ingest_source,
		}
		for reading in readings
	]
	return JsonResponse({"results": data})
