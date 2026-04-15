from django.contrib import admin

from orgs.models import Hostel, Unit


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
	list_display = ("name", "code", "campus_name", "is_active", "updated_at")
	list_filter = ("campus_name", "is_active")
	search_fields = ("name", "code", "campus_name")
	ordering = ("name",)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
	list_display = ("name", "code", "hostel", "unit_type", "is_active", "updated_at")
	list_filter = ("unit_type", "is_active", "hostel")
	search_fields = ("name", "code", "hostel__name", "hostel__code")
	ordering = ("hostel__name", "unit_type", "name")
