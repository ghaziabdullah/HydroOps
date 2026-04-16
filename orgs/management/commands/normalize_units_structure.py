from django.core.management.base import BaseCommand
from django.db import transaction

from orgs.models import Hostel, Unit


class Command(BaseCommand):
    help = "Normalize each hostel to 4 floors and 2 washroom clusters per floor."

    @transaction.atomic
    def handle(self, *args, **options):
        hostels = Hostel.objects.all().order_by("name")
        updated_hostels = 0

        for hostel in hostels:
            self._normalize_hostel_units(hostel)
            updated_hostels += 1

        self.stdout.write(self.style.SUCCESS(f"Normalized unit structure for {updated_hostels} hostel(s)."))

    def _normalize_hostel_units(self, hostel: Hostel):
        existing_units = list(
            Unit.objects.filter(hostel=hostel).order_by("unit_type", "id")
        )

        # Stage existing codes to avoid unique constraint conflicts during reassignment.
        for unit in existing_units:
            unit.code = f"legacy-{unit.id}"
            unit.save(update_fields=["code"])

        floor_units = [u for u in existing_units if u.unit_type == Unit.UnitType.FLOOR]
        cluster_units = [u for u in existing_units if u.unit_type == Unit.UnitType.CLUSTER]

        target_floors = [
            {"code": f"floor-{index:02d}", "name": f"Floor {index}"}
            for index in range(1, 5)
        ]
        target_clusters = [
            {
                "code": f"f{floor_no:02d}-cluster-{suffix.lower()}",
                "name": f"Floor {floor_no} Washroom Cluster {suffix}",
            }
            for floor_no in range(1, 5)
            for suffix in ["A", "B"]
        ]

        active_ids: set[int] = set()

        for index, target in enumerate(target_floors):
            if index < len(floor_units):
                unit = floor_units[index]
                unit.code = target["code"]
                unit.name = target["name"]
                unit.is_active = True
                unit.unit_type = Unit.UnitType.FLOOR
                unit.save(update_fields=["code", "name", "is_active", "unit_type"])
            else:
                unit = Unit.objects.create(
                    hostel=hostel,
                    code=target["code"],
                    name=target["name"],
                    unit_type=Unit.UnitType.FLOOR,
                    is_active=True,
                )
            active_ids.add(unit.id)

        for index, target in enumerate(target_clusters):
            if index < len(cluster_units):
                unit = cluster_units[index]
                unit.code = target["code"]
                unit.name = target["name"]
                unit.is_active = True
                unit.unit_type = Unit.UnitType.CLUSTER
                unit.save(update_fields=["code", "name", "is_active", "unit_type"])
            else:
                unit = Unit.objects.create(
                    hostel=hostel,
                    code=target["code"],
                    name=target["name"],
                    unit_type=Unit.UnitType.CLUSTER,
                    is_active=True,
                )
            active_ids.add(unit.id)

        Unit.objects.filter(hostel=hostel).exclude(id__in=active_ids).update(is_active=False)
