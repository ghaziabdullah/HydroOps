from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render

from accounts.selectors import list_users


@login_required
def profile_page_view(request):
	profile = getattr(request.user, "profile", None)
	return render(request, "accounts/profile_page.html", {"page_title": "User Profile", "profile": profile})


@login_required
def me_api_view(request):
	profile = getattr(request.user, "profile", None)
	return JsonResponse(
		{
			"id": request.user.id,
			"username": request.user.username,
			"email": request.user.email,
			"role": profile.role if profile else None,
			"is_active_operator": profile.is_active_operator if profile else False,
		}
	)


@login_required
@user_passes_test(lambda user: user.is_staff)
def user_list_api_view(request):
	users = list_users()
	data = [
		{
			"id": user.id,
			"username": user.username,
			"email": user.email,
			"is_staff": user.is_staff,
			"is_active": user.is_active,
			"role": user.profile.role if hasattr(user, "profile") else None,
		}
		for user in users
	]
	return JsonResponse({"results": data})
