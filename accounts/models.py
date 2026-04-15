from django.conf import settings
from django.db import models


class UserProfile(models.Model):
	class Role(models.TextChoices):
		ADMIN = "ADMIN", "Admin"
		OPERATOR = "OPERATOR", "Operator"
		VIEWER = "VIEWER", "Viewer"

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
	role = models.CharField(max_length=12, choices=Role.choices, default=Role.OPERATOR)
	phone = models.CharField(max_length=30, blank=True)
	is_active_operator = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["user__username"]
		indexes = [
			models.Index(fields=["role"]),
			models.Index(fields=["is_active_operator"]),
		]

	def __str__(self) -> str:
		return f"{self.user.username} ({self.role})"
