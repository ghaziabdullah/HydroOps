from django.db import models


class Asset(models.Model):
	class AssetType(models.TextChoices):
		MAIN_INLET = "MAIN_INLET", "Main Inlet"
		TANK = "TANK", "Tank"
		UNIT_METER = "UNIT_METER", "Unit Meter"
		PIPELINE = "PIPELINE", "Pipeline"
		QUALITY_POINT = "QUALITY_POINT", "Quality Point"

	hostel = models.ForeignKey("orgs.Hostel", on_delete=models.CASCADE, related_name="assets")
	unit = models.ForeignKey(
		"orgs.Unit",
		on_delete=models.SET_NULL,
		related_name="assets",
		null=True,
		blank=True,
	)
	name = models.CharField(max_length=120)
	code = models.SlugField(max_length=40)
	asset_type = models.CharField(max_length=20, choices=AssetType.choices)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["hostel__name", "name"]
		constraints = [
			models.UniqueConstraint(fields=["hostel", "code"], name="unique_asset_code_per_hostel"),
		]
		indexes = [
			models.Index(fields=["hostel", "asset_type"]),
			models.Index(fields=["unit"]),
			models.Index(fields=["is_active"]),
		]

	def __str__(self) -> str:
		return f"{self.hostel.code} - {self.name}"


class Device(models.Model):
	asset = models.ForeignKey("iot.Asset", on_delete=models.CASCADE, related_name="devices")
	name = models.CharField(max_length=120)
	serial_number = models.CharField(max_length=80, unique=True)
	firmware_version = models.CharField(max_length=40, blank=True)
	last_seen_at = models.DateTimeField(null=True, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["asset__hostel__name", "name"]
		indexes = [
			models.Index(fields=["asset", "is_active"]),
			models.Index(fields=["last_seen_at"]),
		]

	def __str__(self) -> str:
		return f"{self.name} ({self.serial_number})"


class Sensor(models.Model):
	class SensorKind(models.TextChoices):
		FLOW = "FLOW", "Flow"
		LEVEL = "LEVEL", "Level"
		PRESSURE = "PRESSURE", "Pressure"
		PH = "PH", "pH"
		TURBIDITY = "TURBIDITY", "Turbidity"
		TDS = "TDS", "TDS"
		TEMPERATURE = "TEMPERATURE", "Temperature"

	class SensorStatus(models.TextChoices):
		ONLINE = "ONLINE", "Online"
		OFFLINE = "OFFLINE", "Offline"
		UNKNOWN = "UNKNOWN", "Unknown"

	device = models.ForeignKey("iot.Device", on_delete=models.CASCADE, related_name="sensors")
	name = models.CharField(max_length=120)
	code = models.SlugField(max_length=40)
	kind = models.CharField(max_length=20, choices=SensorKind.choices)
	unit_symbol = models.CharField(max_length=20)
	status = models.CharField(max_length=10, choices=SensorStatus.choices, default=SensorStatus.UNKNOWN)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["device__asset__hostel__name", "kind", "name"]
		constraints = [
			models.UniqueConstraint(fields=["device", "code"], name="unique_sensor_code_per_device"),
		]
		indexes = [
			models.Index(fields=["kind", "status"]),
			models.Index(fields=["is_active"]),
		]

	def __str__(self) -> str:
		return f"{self.name} ({self.kind})"


class Reading(models.Model):
	sensor = models.ForeignKey("iot.Sensor", on_delete=models.CASCADE, related_name="readings")
	timestamp = models.DateTimeField()
	value = models.DecimalField(max_digits=12, decimal_places=3)
	ingest_source = models.CharField(max_length=40, default="simulated")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-timestamp"]
		constraints = [
			models.UniqueConstraint(fields=["sensor", "timestamp"], name="unique_sensor_timestamp_reading"),
		]
		indexes = [
			models.Index(fields=["sensor", "timestamp"]),
			models.Index(fields=["timestamp"]),
		]

	def __str__(self) -> str:
		return f"{self.sensor.code} @ {self.timestamp:%Y-%m-%d %H:%M}"
