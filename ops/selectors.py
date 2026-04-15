from django.db.models import QuerySet

from ops.models import Alert, ForecastRun, ThresholdRule


def list_threshold_rules(hostel_id: int | None = None) -> QuerySet[ThresholdRule]:
    queryset = ThresholdRule.objects.filter(is_active=True)
    if hostel_id is not None:
        queryset = queryset.filter(hostel_id=hostel_id)
    return queryset.order_by("rule_type", "hostel__name")


def list_alerts(
    hostel_id: int | None = None,
    unit_id: int | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    acknowledged: bool | None = None,
) -> QuerySet[Alert]:
    queryset = Alert.objects.select_related("hostel", "unit", "asset", "sensor", "acknowledged_by")
    if hostel_id is not None:
        queryset = queryset.filter(hostel_id=hostel_id)
    if unit_id is not None:
        queryset = queryset.filter(unit_id=unit_id)
    if severity:
        queryset = queryset.filter(severity=severity)
    if alert_type:
        queryset = queryset.filter(alert_type=alert_type)
    if acknowledged is True:
        queryset = queryset.exclude(acknowledged_at__isnull=True)
    if acknowledged is False:
        queryset = queryset.filter(acknowledged_at__isnull=True)
    return queryset.order_by("-started_at")


def latest_forecast_for_scope(
    scope_type: str,
    hostel_id: int | None = None,
    unit_id: int | None = None,
) -> ForecastRun | None:
    queryset = ForecastRun.objects.prefetch_related("points").filter(scope_type=scope_type)
    if hostel_id is not None:
        queryset = queryset.filter(hostel_id=hostel_id)
    if unit_id is not None:
        queryset = queryset.filter(unit_id=unit_id)
    return queryset.first()