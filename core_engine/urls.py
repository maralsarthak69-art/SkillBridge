from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="health-check"),
    path("profile/", views.user_profile, name="user-profile"),
    path("cv/parse/", views.parse_cv_view, name="cv-parse"),
    path("cv/<int:cv_id>/", views.get_parsed_cv, name="cv-detail"),
    path("skills/decay/analyze/", views.analyze_decay_view, name="decay-analyze"),
    path("skills/decay/", views.get_decay_report_view, name="decay-report"),
    path("gap/analyze/", views.analyze_gap_view, name="gap-analyze"),
    path("gap/<int:report_id>/", views.get_gap_report_view, name="gap-detail"),
    path("gap/", views.list_gap_reports_view, name="gap-list"),
    path("curriculum/generate/", views.generate_curriculum_view, name="curriculum-generate"),
    path("curriculum/<int:path_id>/", views.get_learning_path_view, name="curriculum-detail"),
    path("curriculum/", views.list_learning_paths_view, name="curriculum-list"),
    path("capstone/generate/", views.generate_capstone_view, name="capstone-generate"),
    path("capstone/<int:capstone_id>/review/", views.review_capstone_view, name="capstone-review"),
    path("capstone/<int:capstone_id>/", views.get_capstone_view, name="capstone-detail"),
    path("capstone/", views.list_capstones_view, name="capstone-list"),
]
