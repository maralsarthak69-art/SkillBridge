from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CVIntakeView,
    TargetAlignmentView,
    CurriculumView,
    CapstoneReviewView,
    RoadmapProgressView,
    RoadmapTaskUpdateView,
    SkillMapView,
)
from .assessment_views import (
    AssessmentGenerateView,
    AssessmentSubmitView,
    AssessmentSkillsView,
)
from .roadmap_views import RoadmapView, WeekStatusUpdateView
from ..views import dashboard_view, RegisterView, get_decay_report_view
from ..auth import EmailTokenObtainPairView

urlpatterns = [
    # Dashboard
    path("dashboard/", dashboard_view, name="v1-dashboard"),

    # Auth
    path("auth/register/",        RegisterView.as_view(),              name="v1-register"),
    path("auth/token/",           EmailTokenObtainPairView.as_view(),  name="v1-token-obtain"),
    path("auth/token/refresh/",   TokenRefreshView.as_view(),          name="v1-token-refresh"),

    # Skill decay
    path("skills/decay/",         get_decay_report_view,               name="v1-decay-report"),

    # Core pipeline
    path("intake/",               CVIntakeView.as_view(),              name="v1-intake"),
    path("align/",                TargetAlignmentView.as_view(),       name="v1-align"),
    path("curriculum/",           CurriculumView.as_view(),            name="v1-curriculum"),
    path("curriculum/review/",    CapstoneReviewView.as_view(),        name="v1-curriculum-review"),

    # Progress tracking (AI roadmap tasks)
    path("progress/",                    RoadmapProgressView.as_view(),   name="v1-progress-list"),
    path("progress/<int:roadmap_id>/",   RoadmapProgressView.as_view(),   name="v1-progress-detail"),
    path("progress/task/<int:task_id>/", RoadmapTaskUpdateView.as_view(), name="v1-task-update"),

    # SkillMap
    path("skillmap/",             SkillMapView.as_view(),              name="v1-skillmap"),

    # Assessment (CV-based, randomised)
    path("assessment/skills/",    AssessmentSkillsView.as_view(),      name="v1-assessment-skills"),
    path("assessment/generate/",  AssessmentGenerateView.as_view(),    name="v1-assessment-generate"),
    path("assessment/submit/",    AssessmentSubmitView.as_view(),      name="v1-assessment-submit"),

    # Roadmap Dashboard (week-by-week plan)
    path("roadmap/",                          RoadmapView.as_view(),            name="v1-roadmap-list"),
    path("roadmap/week/<int:week>/status/",   WeekStatusUpdateView.as_view(),   name="v1-roadmap-week-status"),
]
