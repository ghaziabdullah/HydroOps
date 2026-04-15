from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.core.serializers.json import DjangoJSONEncoder
import json

from dashboard.selectors import (
	get_campus_overview_metrics,
	get_hostel_comparison_rows,
	get_quality_status_summary,
	get_unit_leaderboard,
)
from ops.models import Alert
from ops.selectors import list_alerts


@login_required
def overview_page_view(request):
	kpis = get_campus_overview_metrics()
	quality = get_quality_status_summary()
	hostel_rows = get_hostel_comparison_rows()
	active_alerts = list_alerts(acknowledged=False).filter(
		severity__in=[Alert.Severity.CRITICAL, Alert.Severity.WARN]
	)[:6]
	
	# Convert alerts to JSON-serializable format
	alerts_json = json.dumps([
		{
			"id": alert.id,
			"message": alert.message,
			"severity": alert.severity,
			"severity_display": alert.get_severity_display(),
			"alert_type": alert.alert_type,
			"hostel_id": alert.hostel_id,
			"started_at": alert.started_at,
		}
		for alert in active_alerts
	], cls=DjangoJSONEncoder)
	
	# Convert quality summary to JSON
	quality_json = json.dumps(quality, cls=DjangoJSONEncoder)
	
	# Convert hostel rows to JSON
	hostel_rows_json = json.dumps(hostel_rows, cls=DjangoJSONEncoder)
	
	# Convert KPIs to JSON
	kpis_json = json.dumps(kpis, cls=DjangoJSONEncoder)
	
	context = {
		"page_title": "Campus Overview Dashboard",
		"kpis": kpis,
		"quality_summary": quality,
		"hostel_rows": hostel_rows,
		"critical_alerts": active_alerts,
		"critical_alerts_json": alerts_json,
		"kpis_json": kpis_json,
		"hostel_rows_json": hostel_rows_json,
		"quality_summary_json": quality_json,
	}
	return render(request, "dashboard/overview_page.html", context)


@login_required
def hostels_page_view(request):
	rows = get_hostel_comparison_rows()
	avg_tank = sum(row["tank_level_percentage"] for row in rows) / len(rows) if rows else 0
	total_alerts = sum(row["alerts"] for row in rows)
	critical_alerts = sum(row["critical_alerts"] for row in rows)

	context = {
		"page_title": "Main Campus Hostels List / Comparison",
		"rows": rows,
		"summary": {
			"hostels": len(rows),
			"avg_tank": avg_tank,
			"open_alerts": total_alerts,
			"critical_alerts": critical_alerts,
		},
	}
	return render(request, "dashboard/hostels_page.html", context)


@login_required
def campus_overview_api_view(request):
	return JsonResponse(
		{
			"kpis": get_campus_overview_metrics(),
			"quality_summary": get_quality_status_summary(),
		}
	)


@login_required
def hostels_comparison_api_view(request):
	return JsonResponse({"results": get_hostel_comparison_rows()})


@login_required
def hostel_units_leaderboard_api_view(request, hostel_id: int):
	top_n = request.GET.get("top_n")
	parsed_top_n = int(top_n) if top_n and top_n.isdigit() else 10
	return JsonResponse({"results": get_unit_leaderboard(hostel_id=hostel_id, top_n=parsed_top_n)})
