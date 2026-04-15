from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum, OuterRef, Subquery
from django.utils import timezone

from iot.models import Reading, Sensor
from ops.models import Alert, ForecastRun
from orgs.models import Hostel, Unit


def get_campus_overview_metrics() -> dict:
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_used_today = (
        Reading.objects.filter(sensor__kind=Sensor.SensorKind.FLOW, timestamp__gte=today_start).aggregate(v=Sum("value"))["v"]
        or 0
    )
    active_hostels = Hostel.objects.filter(is_active=True).count()
    total_hostels = Hostel.objects.count()
    unack_alerts = Alert.objects.filter(acknowledged_at__isnull=True, ended_at__isnull=True).count()
    offline_sensors = Sensor.objects.filter(status=Sensor.SensorStatus.OFFLINE, is_active=True).count()
    latest_level_subquery = (
        Reading.objects.filter(
            sensor_id=OuterRef("pk"),
            timestamp__gte=now - timedelta(hours=12),
        )
        .order_by("-timestamp")
        .values("value")[:1]
    )
    low_tank_sensors = (
        Sensor.objects.filter(
            kind=Sensor.SensorKind.LEVEL,
            is_active=True,
            device__is_active=True,
            device__asset__is_active=True,
        )
        .annotate(latest_level=Subquery(latest_level_subquery))
        .filter(latest_level__isnull=False, latest_level__lte=35)
        .count()
    )

    return {
        "total_used_today": float(total_used_today),
        "active_hostels": active_hostels,
        "total_hostels": total_hostels,
        "unacknowledged_alerts": unack_alerts,
        "offline_sensors": offline_sensors,
        "low_tanks": low_tank_sensors,
    }


def get_hostel_comparison_rows() -> list[dict]:
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tank_since = now - timedelta(hours=6)
    rows: list[dict] = []

    for hostel in Hostel.objects.filter(is_active=True).order_by("name"):
        today_usage = (
            Reading.objects.filter(
                sensor__kind=Sensor.SensorKind.FLOW,
                sensor__device__asset__hostel=hostel,
                timestamp__gte=today_start,
            ).aggregate(v=Sum("value"))["v"]
            or 0
        )

        active_alerts = Alert.objects.filter(hostel=hostel, ended_at__isnull=True).order_by("-started_at")
        alert_count = active_alerts.count()
        critical_count = active_alerts.filter(severity=Alert.Severity.CRITICAL).count()
        alert_details = [
            {
                "severity": alert.get_severity_display(),
                "alert_type": alert.get_alert_type_display(),
                "message": alert.message,
                "started_at": alert.started_at,
            }
            for alert in active_alerts[:8]
        ]

        tank_level = (
            Reading.objects.filter(
                sensor__kind=Sensor.SensorKind.LEVEL,
                sensor__device__asset__hostel=hostel,
                timestamp__gte=tank_since,
            ).aggregate(v=Avg("value"))["v"]
            or 0
        )

        latest_hostel_forecast = (
            ForecastRun.objects.filter(scope_type=ForecastRun.ScopeType.HOSTEL, hostel=hostel)
            .order_by("-generated_at")
            .first()
        )
        predicted_next_24h = 0.0
        if latest_hostel_forecast:
            predicted_next_24h = float(
                latest_hostel_forecast.points.aggregate(v=Sum("predicted_value"))["v"] or 0
            )

        rows.append(
            {
                "hostel_id": hostel.id,
                "hostel_name": hostel.name,
                "hostel_code": hostel.code,
                "today_usage": float(today_usage),
                "predicted_next_24h": predicted_next_24h,
                "alerts": alert_count,
                "critical_alerts": critical_count,
                "tank_level_percentage": float(tank_level),
                "alert_details": alert_details,
            }
        )
    return rows


def get_unit_leaderboard(hostel_id: int, top_n: int = 10) -> list[dict]:
    now = timezone.now()
    since = now - timedelta(hours=24)

    units = Unit.objects.filter(hostel_id=hostel_id, is_active=True)
    rows = []
    for unit in units:
        usage_24h = (
            Reading.objects.filter(
                sensor__kind=Sensor.SensorKind.FLOW,
                sensor__device__asset__unit=unit,
                timestamp__gte=since,
            ).aggregate(v=Sum("value"))["v"]
            or 0
        )

        latest_unit_forecast = (
            ForecastRun.objects.filter(scope_type=ForecastRun.ScopeType.UNIT, unit=unit)
            .order_by("-generated_at")
            .first()
        )
        predicted = 0.0
        if latest_unit_forecast:
            predicted = float(latest_unit_forecast.points.aggregate(v=Sum("predicted_value"))["v"] or 0)

        rows.append(
            {
                "unit_id": unit.id,
                "unit_name": unit.name,
                "unit_type": unit.unit_type,
                "usage_24h": float(usage_24h),
                "predicted_next_24h": predicted,
                "alerts": Alert.objects.filter(unit=unit, ended_at__isnull=True).count(),
            }
        )

    rows.sort(key=lambda row: row["usage_24h"], reverse=True)
    return rows[:top_n]


def get_quality_status_summary() -> dict:
    now = timezone.now()
    latest_quality = Reading.objects.filter(
        sensor__kind__in=[Sensor.SensorKind.PH, Sensor.SensorKind.TURBIDITY, Sensor.SensorKind.TDS],
        timestamp__gte=now - timedelta(hours=6),
    ).values("sensor__kind").annotate(avg_value=Avg("value"), count=Count("id"))

    result = {"PH": None, "TURBIDITY": None, "TDS": None}
    for item in latest_quality:
        result[item["sensor__kind"]] = {
            "avg_value": float(item["avg_value"]),
            "samples": item["count"],
        }
    return result