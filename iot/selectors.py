from datetime import datetime

from django.db.models import QuerySet

from iot.models import Asset, Reading, Sensor


def list_assets(hostel_id: int | None = None) -> QuerySet[Asset]:
    queryset = Asset.objects.select_related("hostel", "unit").filter(is_active=True)
    if hostel_id is not None:
        queryset = queryset.filter(hostel_id=hostel_id)
    return queryset.order_by("hostel__name", "name")


def list_sensors(hostel_id: int | None = None, kind: str | None = None) -> QuerySet[Sensor]:
    queryset = Sensor.objects.select_related("device", "device__asset", "device__asset__hostel").filter(
        is_active=True
    )
    if hostel_id is not None:
        queryset = queryset.filter(device__asset__hostel_id=hostel_id)
    if kind:
        queryset = queryset.filter(kind=kind)
    return queryset.order_by("device__asset__hostel__name", "kind", "name")


def list_readings(
    sensor_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> QuerySet[Reading]:
    queryset = Reading.objects.select_related("sensor", "sensor__device", "sensor__device__asset")
    if sensor_id is not None:
        queryset = queryset.filter(sensor_id=sensor_id)
    if start_at is not None:
        queryset = queryset.filter(timestamp__gte=start_at)
    if end_at is not None:
        queryset = queryset.filter(timestamp__lte=end_at)
    return queryset.order_by("-timestamp")