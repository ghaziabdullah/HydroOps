from django.db.models import QuerySet

from orgs.models import Hostel, Unit


def list_hostels(active_only: bool = True) -> QuerySet[Hostel]:
    queryset = Hostel.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def get_hostel_or_none(hostel_id: int) -> Hostel | None:
    return Hostel.objects.filter(id=hostel_id).first()


def list_units(hostel_id: int | None = None, active_only: bool = True) -> QuerySet[Unit]:
    queryset = Unit.objects.select_related("hostel")
    if active_only:
        queryset = queryset.filter(is_active=True)
    if hostel_id is not None:
        queryset = queryset.filter(hostel_id=hostel_id)
    return queryset.order_by("hostel__name", "unit_type", "name")


def get_unit_or_none(unit_id: int) -> Unit | None:
    return Unit.objects.select_related("hostel").filter(id=unit_id).first()