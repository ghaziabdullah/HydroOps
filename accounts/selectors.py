from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from accounts.models import UserProfile

User = get_user_model()


def list_users() -> QuerySet[User]:
    return User.objects.select_related("profile").order_by("username")


def get_user_profile(user_id: int) -> UserProfile | None:
    return UserProfile.objects.select_related("user").filter(user_id=user_id).first()