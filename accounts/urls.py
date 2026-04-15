from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
	path("profile/", views.profile_page_view, name="profile-page"),
	path("api/me/", views.me_api_view, name="me-api"),
	path("api/users/", views.user_list_api_view, name="user-list-api"),
]
