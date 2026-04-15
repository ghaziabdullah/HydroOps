from django.contrib import admin

from iot.models import Asset, Device, Reading, Sensor


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
	list_display = ("name", "code", "asset_type", "hostel", "unit", "is_active")
	list_filter = ("asset_type", "is_active", "hostel")
	search_fields = ("name", "code", "hostel__name", "unit__name")
	ordering = ("hostel__name", "name")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
	list_display = ("name", "serial_number", "asset", "last_seen_at", "is_active")
	list_filter = ("is_active", "asset__hostel")
	search_fields = ("name", "serial_number", "asset__name")
	ordering = ("asset__hostel__name", "name")


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
	list_display = ("name", "code", "kind", "status", "device", "is_active")
	list_filter = ("kind", "status", "is_active", "device__asset__hostel")
	search_fields = ("name", "code", "device__name", "device__asset__name")
	ordering = ("device__asset__hostel__name", "kind", "name")


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
	list_display = ("sensor", "timestamp", "value", "ingest_source")
	list_filter = ("sensor__kind", "ingest_source", "sensor__device__asset__hostel")
	search_fields = ("sensor__name", "sensor__code", "sensor__device__name")
	ordering = ("-timestamp",)
