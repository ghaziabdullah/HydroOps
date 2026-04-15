from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, QuerySet
from django.utils import timezone

from iot.models import Device, Reading, Sensor
from ops.models import Alert, ForecastPoint, ForecastRun, ThresholdRule


def _get_rule(
    rule_type: str,
    hostel_id: int | None = None,
) -> ThresholdRule | None:
    scoped = ThresholdRule.objects.filter(rule_type=rule_type, hostel_id=hostel_id, is_active=True).first()
    if scoped:
        return scoped
    return ThresholdRule.objects.filter(rule_type=rule_type, hostel__isnull=True, is_active=True).first()


def _get_threshold(rule_type: str, level: str, hostel_id: int | None = None, fallback: float = 0.0) -> float:
    rule = _get_rule(rule_type=rule_type, hostel_id=hostel_id)
    if rule is None:
        return fallback
    if level == "critical":
        return float(rule.critical_value)
    return float(rule.warning_value)


@transaction.atomic
def acknowledge_alert(alert: Alert, user) -> Alert:
    if alert.acknowledged_at is None:
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = user
        alert.save(update_fields=["acknowledged_at", "acknowledged_by"])
    return alert


def create_alert_if_missing(
    *,
    alert_type: str,
    severity: str,
    message: str,
    hostel_id: int | None = None,
    unit_id: int | None = None,
    asset_id: int | None = None,
    sensor_id: int | None = None,
    metadata: dict | None = None,
) -> Alert:
    existing = (
        Alert.objects.filter(
            alert_type=alert_type,
            hostel_id=hostel_id,
            unit_id=unit_id,
            asset_id=asset_id,
            sensor_id=sensor_id,
            acknowledged_at__isnull=True,
            ended_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )
    if existing:
        return existing

    return Alert.objects.create(
        alert_type=alert_type,
        severity=severity,
        message=message,
        hostel_id=hostel_id,
        unit_id=unit_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        started_at=timezone.now(),
        metadata=metadata or {},
    )


def run_rule_based_alerts(hostel_id: int | None = None) -> list[Alert]:
    created_alerts: list[Alert] = []
    now = timezone.now()

    sensors = Sensor.objects.select_related("device", "device__asset", "device__asset__hostel", "device__asset__unit")
    if hostel_id is not None:
        sensors = sensors.filter(device__asset__hostel_id=hostel_id)

    for sensor in sensors:
        if sensor.kind == Sensor.SensorKind.LEVEL:
            latest = sensor.readings.order_by("-timestamp").first()
            if latest:
                low_threshold = _get_threshold(
                    ThresholdRule.RuleType.TANK_LOW,
                    level="warning",
                    hostel_id=sensor.device.asset.hostel_id,
                    fallback=25.0,
                )
                if float(latest.value) <= low_threshold:
                    created_alerts.append(
                        create_alert_if_missing(
                            alert_type=Alert.AlertType.TANK_LOW,
                            severity=Alert.Severity.WARN,
                            message=f"Tank level low on {sensor.device.asset.name}: {latest.value}",
                            hostel_id=sensor.device.asset.hostel_id,
                            unit_id=sensor.device.asset.unit_id,
                            asset_id=sensor.device.asset_id,
                            sensor_id=sensor.id,
                            metadata={"observed_value": str(latest.value)},
                        )
                    )

        if sensor.kind in {Sensor.SensorKind.PH, Sensor.SensorKind.TURBIDITY, Sensor.SensorKind.TDS}:
            latest = sensor.readings.order_by("-timestamp").first()
            if latest is None:
                continue

            rule_map = {
                Sensor.SensorKind.PH: ThresholdRule.RuleType.QUALITY_PH,
                Sensor.SensorKind.TURBIDITY: ThresholdRule.RuleType.QUALITY_TURBIDITY,
                Sensor.SensorKind.TDS: ThresholdRule.RuleType.QUALITY_TDS,
            }
            default_critical = {Sensor.SensorKind.PH: 8.5, Sensor.SensorKind.TURBIDITY: 5.0, Sensor.SensorKind.TDS: 500.0}
            critical = _get_threshold(
                rule_map[sensor.kind],
                level="critical",
                hostel_id=sensor.device.asset.hostel_id,
                fallback=default_critical[sensor.kind],
            )
            observed = float(latest.value)
            breach = observed > critical
            if sensor.kind == Sensor.SensorKind.PH:
                breach = observed > critical or observed < 6.5

            if breach:
                created_alerts.append(
                    create_alert_if_missing(
                        alert_type=Alert.AlertType.QUALITY_EXCEEDANCE,
                        severity=Alert.Severity.CRITICAL,
                        message=f"Quality exceedance for {sensor.name}: {latest.value} {sensor.unit_symbol}",
                        hostel_id=sensor.device.asset.hostel_id,
                        unit_id=sensor.device.asset.unit_id,
                        asset_id=sensor.device.asset_id,
                        sensor_id=sensor.id,
                        metadata={"observed_value": str(latest.value), "sensor_kind": sensor.kind},
                    )
                )

    devices: QuerySet[Device] = Device.objects.select_related("asset", "asset__hostel", "asset__unit")
    if hostel_id is not None:
        devices = devices.filter(asset__hostel_id=hostel_id)

    for device in devices:
        offline_minutes = _get_threshold(
            ThresholdRule.RuleType.SENSOR_OFFLINE_MINUTES,
            level="warning",
            hostel_id=device.asset.hostel_id,
            fallback=30,
        )
        if device.last_seen_at is None or (now - device.last_seen_at) > timedelta(minutes=offline_minutes):
            created_alerts.append(
                create_alert_if_missing(
                    alert_type=Alert.AlertType.SENSOR_OFFLINE,
                    severity=Alert.Severity.WARN,
                    message=f"Device offline: {device.name}",
                    hostel_id=device.asset.hostel_id,
                    unit_id=device.asset.unit_id,
                    asset_id=device.asset_id,
                    metadata={"last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None},
                )
            )

    return created_alerts


@transaction.atomic
def generate_baseline_forecast(
    *,
    scope_type: str,
    hostel_id: int | None = None,
    unit_id: int | None = None,
    horizon_hours: int = 24,
) -> ForecastRun:
    now = timezone.now()
    since = now - timedelta(days=7)

    flow_readings = Reading.objects.filter(
        sensor__kind=Sensor.SensorKind.FLOW,
        timestamp__gte=since,
    )
    if scope_type == ForecastRun.ScopeType.HOSTEL and hostel_id is not None:
        flow_readings = flow_readings.filter(sensor__device__asset__hostel_id=hostel_id)
    if scope_type == ForecastRun.ScopeType.UNIT and unit_id is not None:
        flow_readings = flow_readings.filter(sensor__device__asset__unit_id=unit_id)

    avg_by_hour: dict[int, float] = defaultdict(float)
    for hour in range(24):
        avg = flow_readings.filter(timestamp__hour=hour).aggregate(v=Avg("value"))["v"]
        avg_by_hour[hour] = float(avg) if avg is not None else 0.0

    run = ForecastRun.objects.create(
        scope_type=scope_type,
        hostel_id=hostel_id,
        unit_id=unit_id,
        method=ForecastRun.Method.BASELINE,
        horizon_hours=horizon_hours,
        notes="Baseline hourly average over last 7 days.",
    )

    points = []
    for offset in range(1, horizon_hours + 1):
        ts = now + timedelta(hours=offset)
        predicted = Decimal(str(round(avg_by_hour[ts.hour], 3)))
        lower = predicted * Decimal("0.9")
        upper = predicted * Decimal("1.1")
        points.append(
            ForecastPoint(
                forecast_run=run,
                timestamp=ts,
                predicted_value=predicted,
                lower_bound=lower,
                upper_bound=upper,
            )
        )

    ForecastPoint.objects.bulk_create(points)
    return run