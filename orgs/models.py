from django.db import models


class Hostel(models.Model):
	name = models.CharField(max_length=120)
	code = models.SlugField(max_length=40, unique=True)
	campus_name = models.CharField(max_length=120, default="Main Campus")
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["name"]
		indexes = [
			models.Index(fields=["is_active"]),
			models.Index(fields=["campus_name"]),
		]

	def __str__(self) -> str:
		return f"{self.name} ({self.code})"


class Unit(models.Model):
	class UnitType(models.TextChoices):
		FLOOR = "FLOOR", "Floor"
		CLUSTER = "CLUSTER", "Cluster"

	hostel = models.ForeignKey("orgs.Hostel", on_delete=models.CASCADE, related_name="units")
	name = models.CharField(max_length=120)
	code = models.SlugField(max_length=40)
	unit_type = models.CharField(max_length=12, choices=UnitType.choices)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["hostel__name", "unit_type", "name"]
		constraints = [
			models.UniqueConstraint(fields=["hostel", "code"], name="unique_unit_code_per_hostel"),
		]
		indexes = [
			models.Index(fields=["hostel", "unit_type"]),
			models.Index(fields=["is_active"]),
		]

	def __str__(self) -> str:
		return f"{self.hostel.code} - {self.name}"
