from django.contrib import admin

from accounts.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "role", "is_active_operator", "updated_at")
	list_filter = ("role", "is_active_operator")
	search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
	ordering = ("user__username",)
