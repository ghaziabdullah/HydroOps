import math
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from iot.models import Asset, Device, Reading, Sensor
from ops.models import Alert, ForecastPoint, ForecastRun, ThresholdRule
from ops.services import generate_baseline_forecast, run_rule_based_alerts
from orgs.models import Hostel, Unit


class Command(BaseCommand):
    help = "Seed HydroOps demo data for hostels, units, sensors, readings, alerts, and forecasts."

    HOSTELS = [
        ("Hajveri", "hajveri"),
        ("Rehmat", "rehmat"),
        ("Razi", "razi"),
        ("Liaquat", "liaquat"),
        ("Attar", "attar"),
        ("Ghazali", "ghazali"),
        ("Beruni", "beruni"),
        ("Zakaria", "zakaria"),
    ]

    INTEGRATION_HOSTEL_CODE = "hajveri"
    INTEGRATION_UNIT_CODE = "f04-cluster-b"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing HydroOps operational data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)

        if options["reset"]:
            self._reset_data()

        self._ensure_threshold_rules()

        hostels: list[Hostel] = []
        for name, code in self.HOSTELS:
            hostels.append(self._create_hostel_with_structure(name, code))

        for index, hostel in enumerate(hostels):
            self._seed_readings_for_hostel(hostel=hostel, hostel_index=index)

        self._mark_offline_sensors(hostels)

        created_alerts = run_rule_based_alerts()
        generate_baseline_forecast(scope_type=ForecastRun.ScopeType.CAMPUS, horizon_hours=24)
        for hostel in hostels:
            generate_baseline_forecast(scope_type=ForecastRun.ScopeType.HOSTEL, hostel_id=hostel.id, horizon_hours=24)

        sample_units = Unit.objects.filter(hostel__in=hostels, is_active=True).order_by("hostel_id", "name")[:8]
        for sample_unit in sample_units:
            generate_baseline_forecast(
                scope_type=ForecastRun.ScopeType.UNIT,
                unit_id=sample_unit.id,
                hostel_id=sample_unit.hostel_id,
                horizon_hours=24,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed completed for {len(hostels)} hostels x 12 units. Alerts created/updated: {len(created_alerts)}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Integration-ready lane reserved at Hajveri / Floor 4 Cluster B: last 48h of synthetic meter readings are omitted."
            )
        )

    def _reset_data(self):
        Alert.objects.all().delete()
        ForecastPoint.objects.all().delete()
        ForecastRun.objects.all().delete()
        Reading.objects.all().delete()
        Sensor.objects.all().delete()
        Device.objects.all().delete()
        Asset.objects.all().delete()
        Unit.objects.all().delete()
        Hostel.objects.all().delete()

    def _ensure_threshold_rules(self):
        defaults = [
            (ThresholdRule.RuleType.NIGHT_CONTINUOUS_FLOW, 3.0, 8.0, "L/min"),
            (ThresholdRule.RuleType.BLOCKAGE_PATTERN, 2.0, 4.0, "index"),
            (ThresholdRule.RuleType.TANK_LOW, 30.0, 20.0, "%"),
            (ThresholdRule.RuleType.TANK_OVERFLOW_RISK, 90.0, 95.0, "%"),
            (ThresholdRule.RuleType.QUALITY_PH, 8.0, 8.5, "pH"),
            (ThresholdRule.RuleType.QUALITY_TURBIDITY, 3.0, 5.0, "NTU"),
            (ThresholdRule.RuleType.QUALITY_TDS, 300.0, 500.0, "ppm"),
            (ThresholdRule.RuleType.SENSOR_OFFLINE_MINUTES, 20.0, 45.0, "minutes"),
            (ThresholdRule.RuleType.CAMPUS_INLET_DIFF_PERCENT, 3.0, 7.0, "%"),
        ]
        for rule_type, warn, critical, unit_symbol in defaults:
            ThresholdRule.objects.get_or_create(
                hostel=None,
                rule_type=rule_type,
                defaults={
                    "warning_value": warn,
                    "critical_value": critical,
                    "unit_symbol": unit_symbol,
                    "is_active": True,
                },
            )

    def _create_hostel_with_structure(self, name: str, code: str) -> Hostel:
        hostel, _ = Hostel.objects.get_or_create(
            code=code,
            defaults={"name": name, "campus_name": "Main Campus", "is_active": True},
        )

        floor_units = []
        for floor_no in range(1, 5):
            unit, _ = Unit.objects.get_or_create(
                hostel=hostel,
                code=f"floor-{floor_no:02d}",
                defaults={
                    "name": f"Floor {floor_no}",
                    "unit_type": Unit.UnitType.FLOOR,
                    "is_active": True,
                },
            )
            floor_units.append(unit)

        cluster_units = []
        for floor_no in range(1, 5):
            for suffix in ["A", "B"]:
                unit, _ = Unit.objects.get_or_create(
                    hostel=hostel,
                    code=f"f{floor_no:02d}-cluster-{suffix.lower()}",
                    defaults={
                        "name": f"Floor {floor_no} Washroom Cluster {suffix}",
                        "unit_type": Unit.UnitType.CLUSTER,
                        "is_active": True,
                    },
                )
                cluster_units.append(unit)

        self._create_asset_stack(hostel, floor_units + cluster_units)
        return hostel

    def _create_asset_stack(self, hostel: Hostel, units: list[Unit]):
        main_inlet, _ = Asset.objects.get_or_create(
            hostel=hostel,
            code="main-inlet",
            defaults={"name": "Main Inlet", "asset_type": Asset.AssetType.MAIN_INLET, "is_active": True},
        )
        self._create_device_with_sensor(main_inlet, "Inlet Flow Device", "FLOW", "L/min")

        tank_asset, _ = Asset.objects.get_or_create(
            hostel=hostel,
            code="tank-1",
            defaults={"name": "Main Water Tank", "asset_type": Asset.AssetType.TANK, "is_active": True},
        )
        self._create_device_with_sensor(tank_asset, "Tank Level Device", "LEVEL", "%")

        pipeline_asset, _ = Asset.objects.get_or_create(
            hostel=hostel,
            code="pipeline-main",
            defaults={"name": "Main Pipeline", "asset_type": Asset.AssetType.PIPELINE, "is_active": True},
        )
        self._create_device_with_sensor(pipeline_asset, "Pressure Device", "PRESSURE", "bar")

        quality_asset, _ = Asset.objects.get_or_create(
            hostel=hostel,
            code="quality-node",
            defaults={"name": "Quality Node", "asset_type": Asset.AssetType.QUALITY_POINT, "is_active": True},
        )
        quality_device = self._create_device(quality_asset, "Quality Device")
        self._create_sensor(quality_device, "pH Sensor", "ph", Sensor.SensorKind.PH, "pH")
        self._create_sensor(quality_device, "Turbidity Sensor", "turbidity", Sensor.SensorKind.TURBIDITY, "NTU")
        self._create_sensor(quality_device, "TDS Sensor", "tds", Sensor.SensorKind.TDS, "ppm")
        self._create_sensor(
            quality_device,
            "Temperature Sensor",
            "temperature",
            Sensor.SensorKind.TEMPERATURE,
            "C",
        )

        for unit in units:
            asset, _ = Asset.objects.get_or_create(
                hostel=hostel,
                unit=unit,
                code=f"meter-{unit.code}",
                defaults={
                    "name": f"Meter {unit.name}",
                    "asset_type": Asset.AssetType.UNIT_METER,
                    "is_active": True,
                },
            )
            self._create_device_with_sensor(asset, f"Meter Device {unit.code}", "FLOW", "L/min")

    def _create_device(self, asset: Asset, name: str) -> Device:
        serial = f"{asset.hostel.code}-{asset.code}-{name.lower().replace(' ', '-')[:16]}"
        device, _ = Device.objects.get_or_create(
            serial_number=serial,
            defaults={
                "asset": asset,
                "name": name,
                "firmware_version": "1.0.0",
                "last_seen_at": timezone.now() - timedelta(minutes=random.randint(1, 10)),
                "is_active": True,
            },
        )
        return device

    def _create_sensor(self, device: Device, name: str, code: str, kind: str, unit_symbol: str) -> Sensor:
        sensor, _ = Sensor.objects.get_or_create(
            device=device,
            code=code,
            defaults={
                "name": name,
                "kind": kind,
                "unit_symbol": unit_symbol,
                "status": Sensor.SensorStatus.ONLINE,
                "is_active": True,
            },
        )
        return sensor

    def _create_device_with_sensor(self, asset: Asset, device_name: str, kind: str, unit_symbol: str):
        device = self._create_device(asset, device_name)
        sensor_code = kind.lower()
        if asset.unit_id:
            sensor_code = f"{sensor_code}-{asset.unit.code}"
        self._create_sensor(device, f"{asset.name} {kind.title()} Sensor", sensor_code, kind, unit_symbol)

    def _seed_readings_for_hostel(self, hostel: Hostel, hostel_index: int):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        start = now - timedelta(days=14)
        total_window_seconds = (now - start).total_seconds() or 1

        sensors = Sensor.objects.filter(device__asset__hostel=hostel).select_related(
            "device",
            "device__asset",
            "device__asset__unit",
        )

        readings: list[Reading] = []
        for sensor in sensors:
            timestamp = start
            while timestamp <= now:
                progress = (timestamp - start).total_seconds() / total_window_seconds
                value = self._sensor_value(
                    sensor=sensor,
                    timestamp=timestamp,
                    now=now,
                    hostel_index=hostel_index,
                    drift_progress=progress,
                )

                if value is not None:
                    readings.append(
                        Reading(
                            sensor=sensor,
                            timestamp=timestamp,
                            value=Decimal(str(round(value, 3))),
                            ingest_source="simulated_seed",
                        )
                    )

                if len(readings) >= 6000:
                    Reading.objects.bulk_create(readings, batch_size=2000, ignore_conflicts=True)
                    readings = []

                timestamp += timedelta(minutes=15)

        if readings:
            Reading.objects.bulk_create(readings, batch_size=2000, ignore_conflicts=True)

    def _sensor_value(
        self,
        *,
        sensor: Sensor,
        timestamp,
        now,
        hostel_index: int,
        drift_progress: float,
    ) -> float | None:
        asset = sensor.device.asset
        unit = asset.unit
        hour_fraction = timestamp.hour + (timestamp.minute / 60.0)
        is_weekend = timestamp.weekday() >= 5
        day_of_year = timestamp.timetuple().tm_yday

        # Leave a real-data handoff lane for one unit by skipping recent synthetic samples.
        if (
            sensor.kind == Sensor.SensorKind.FLOW
            and sensor.device.asset.hostel.code == self.INTEGRATION_HOSTEL_CODE
            and unit is not None
            and unit.code == self.INTEGRATION_UNIT_CODE
            and timestamp >= now - timedelta(days=2)
        ):
            return None

        if sensor.kind == Sensor.SensorKind.FLOW:
            return self._flow_value(
                sensor=sensor,
                timestamp=timestamp,
                hostel_index=hostel_index,
                hour_fraction=hour_fraction,
                is_weekend=is_weekend,
                day_of_year=day_of_year,
                drift_progress=drift_progress,
            )

        if sensor.kind == Sensor.SensorKind.LEVEL:
            return self._level_value(sensor=sensor, timestamp=timestamp, now=now, hour_fraction=hour_fraction)

        if sensor.kind == Sensor.SensorKind.PRESSURE:
            return self._pressure_value(sensor=sensor, timestamp=timestamp)

        if sensor.kind in {Sensor.SensorKind.PH, Sensor.SensorKind.TURBIDITY, Sensor.SensorKind.TDS}:
            return self._quality_value(sensor=sensor, timestamp=timestamp, now=now)

        if sensor.kind == Sensor.SensorKind.TEMPERATURE:
            temp = 24.0 + 3.5 * math.sin(((hour_fraction - 14) / 24.0) * 2 * math.pi)
            return temp + random.uniform(-0.35, 0.35)

        return 0.0

    def _flow_value(
        self,
        *,
        sensor: Sensor,
        timestamp,
        hostel_index: int,
        hour_fraction: float,
        is_weekend: bool,
        day_of_year: int,
        drift_progress: float,
    ) -> float:
        asset = sensor.device.asset
        unit = asset.unit

        baseline = 3.5
        morning_peak = math.exp(-((hour_fraction - 8.1) ** 2) / (2 * 1.4**2))
        evening_peak = math.exp(-((hour_fraction - 19.1) ** 2) / (2 * 1.8**2))
        daily_wave = baseline + (13.0 * morning_peak) + (10.5 * evening_peak)

        weekday_factor = 0.82 if is_weekend else 1.0
        seasonal = 1.0 + (0.05 * math.sin((day_of_year / 365.0) * 2 * math.pi))
        drift_factor = 1.0 + (0.12 * drift_progress)  # gradual increase over 2 weeks

        if unit is None:
            # Main inlet / aggregation sensors carry larger values.
            value = daily_wave * 5.2 * weekday_factor * seasonal * drift_factor
        else:
            try:
                unit_num = int(unit.code.split("-")[-1])
            except ValueError:
                unit_num = (sum(ord(char) for char in unit.code) % 9) + 1
            unit_scale = 0.55 + ((unit_num % 5) * 0.08) + (hostel_index * 0.015)
            value = daily_wave * unit_scale * weekday_factor * seasonal * drift_factor

            # Leak signature: persistent night trickle in selected units.
            if (sensor.device.asset.hostel.code, unit.code) in {
                ("hajveri", "f02-cluster-a"),
                ("razi", "f03-cluster-b"),
                ("ghazali", "f01-cluster-a"),
            } and (0 <= timestamp.hour <= 4):
                value = max(value, 4.2 + random.uniform(-0.3, 0.4))

        # Event-driven spikes (sports day, exams week, etc.).
        if random.random() < 0.008:
            value *= random.uniform(1.35, 1.8)

        if sensor.device.asset.hostel.code in {"liaquat", "attar"}:
            if timestamp.weekday() == 3 and 19 <= timestamp.hour <= 22:
                value *= 1.28

        # Small measurement noise.
        value += random.uniform(-0.45, 0.45)
        return max(0.05, value)

    def _level_value(self, *, sensor: Sensor, timestamp, now, hour_fraction: float) -> float:
        hostel_code = sensor.device.asset.hostel.code
        refill_wave = 63.0 + (17.0 * math.sin(((hour_fraction - 4) / 24.0) * 2 * math.pi))
        value = refill_wave + random.uniform(-2.0, 2.0)

        # Keep a few hostels low for low-tank alerts.
        if hostel_code in {"rehmat", "beruni", "zakaria", "liaquat"} and timestamp >= now - timedelta(days=3):
            value = min(value, random.uniform(14.0, 28.0))

        # Add acute low-level entries in the latest 18h for dashboard KPI visibility.
        if hostel_code in {"rehmat", "zakaria"} and timestamp >= now - timedelta(hours=18):
            value = min(value, random.uniform(9.0, 19.0))

        # Overflow trend in one hostel to exercise overflow-related UI paths.
        if hostel_code == "attar" and timestamp.weekday() == 2 and 9 <= timestamp.hour <= 12:
            value = max(value, random.uniform(88.0, 96.0))

        return max(5.0, min(99.0, value))

    def _pressure_value(self, *, sensor: Sensor, timestamp) -> float:
        hostel_code = sensor.device.asset.hostel.code
        value = 3.1 + random.uniform(-0.22, 0.22)

        # Blockage-like pressure drop window.
        if hostel_code == "ghazali" and timestamp.weekday() == 1 and 10 <= timestamp.hour <= 13:
            value = random.uniform(0.95, 1.35)

        # Pump overshoot pattern.
        if hostel_code == "razi" and timestamp.weekday() == 4 and 6 <= timestamp.hour <= 8:
            value = random.uniform(4.2, 4.9)

        return max(0.4, value)

    def _quality_value(self, *, sensor: Sensor, timestamp, now) -> float:
        hostel_code = sensor.device.asset.hostel.code

        profile = {
            "hajveri": "good",
            "rehmat": "good",
            "razi": "moderate",
            "liaquat": "moderate",
            "attar": "good",
            "ghazali": "risky",
            "beruni": "moderate",
            "zakaria": "good",
        }[hostel_code]

        if sensor.kind == Sensor.SensorKind.PH:
            ranges = {
                "good": (6.9, 7.6),
                "moderate": (6.7, 7.9),
                "risky": (6.3, 8.7),
            }
            lo, hi = ranges[profile]
            value = random.uniform(lo, hi)
            if hostel_code == "ghazali" and timestamp >= now - timedelta(days=2) and 14 <= timestamp.hour <= 18:
                value = random.uniform(8.6, 9.0)
            return value

        if sensor.kind == Sensor.SensorKind.TURBIDITY:
            ranges = {
                "good": (0.4, 2.0),
                "moderate": (1.0, 3.5),
                "risky": (2.6, 6.8),
            }
            lo, hi = ranges[profile]
            value = random.uniform(lo, hi)
            if hostel_code in {"ghazali", "beruni"} and random.random() < 0.02:
                value = random.uniform(5.6, 7.4)
            return value

        # TDS
        ranges = {
            "good": (170.0, 290.0),
            "moderate": (260.0, 430.0),
            "risky": (420.0, 640.0),
        }
        lo, hi = ranges[profile]
        value = random.uniform(lo, hi)
        if hostel_code == "ghazali" and timestamp >= now - timedelta(days=1):
            value = max(value, random.uniform(520.0, 690.0))
        return value

    def _mark_offline_sensors(self, hostels: list[Hostel]):
        # Keep a few sensors explicitly offline for dashboard KPI checks.
        offline_targets = [
            ("rehmat", Asset.AssetType.QUALITY_POINT),
            ("ghazali", Asset.AssetType.PIPELINE),
            ("beruni", Asset.AssetType.UNIT_METER),
        ]

        for hostel_code, asset_type in offline_targets:
            sensor = (
                Sensor.objects.select_related("device", "device__asset", "device__asset__hostel")
                .filter(device__asset__hostel__code=hostel_code, device__asset__asset_type=asset_type)
                .order_by("id")
                .first()
            )
            if not sensor:
                continue

            sensor.status = Sensor.SensorStatus.OFFLINE
            sensor.save(update_fields=["status"])

            sensor.device.last_seen_at = timezone.now() - timedelta(hours=4, minutes=random.randint(0, 40))
            sensor.device.save(update_fields=["last_seen_at"])

        # Keep integration lane sensor online/recent so live data can replace synthetic smoothly.
        integration_sensor = (
            Sensor.objects.select_related("device", "device__asset", "device__asset__unit", "device__asset__hostel")
            .filter(
                device__asset__hostel__code=self.INTEGRATION_HOSTEL_CODE,
                device__asset__unit__code=self.INTEGRATION_UNIT_CODE,
                kind=Sensor.SensorKind.FLOW,
            )
            .first()
        )
        if integration_sensor:
            integration_sensor.status = Sensor.SensorStatus.ONLINE
            integration_sensor.save(update_fields=["status"])
            integration_sensor.device.last_seen_at = timezone.now() - timedelta(minutes=2)
            integration_sensor.device.save(update_fields=["last_seen_at"])