from django.urls import path
from . import views

urlpatterns = [
    # Health
    path("health/", views.health_check, name="health-check"),

    # Auth
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/me/",        views.MeView.as_view(),       name="me"),
    path("profile/",        views.user_profile,           name="user-profile"),

    # Sarthak — CV & AI
    path("cv/parse/",                           views.parse_cv_view,             name="cv-parse"),
    path("cv/<int:cv_id>/",                     views.get_parsed_cv,             name="cv-detail"),
    path("skills/decay/analyze/",               views.analyze_decay_view,        name="decay-analyze"),
    path("skills/decay/",                       views.get_decay_report_view,     name="decay-report"),
    path("gap/analyze/",                        views.analyze_gap_view,          name="gap-analyze"),
    path("gap/<int:report_id>/",                views.get_gap_report_view,       name="gap-detail"),
    path("gap/",                                views.list_gap_reports_view,     name="gap-list"),
    path("curriculum/generate/",                views.generate_curriculum_view,  name="curriculum-generate"),
    path("curriculum/<int:path_id>/",           views.get_learning_path_view,    name="curriculum-detail"),
    path("curriculum/",                         views.list_learning_paths_view,  name="curriculum-list"),
    path("capstone/generate/",                  views.generate_capstone_view,    name="capstone-generate"),
    path("capstone/<int:capstone_id>/review/",  views.review_capstone_view,      name="capstone-review"),
    path("capstone/<int:capstone_id>/",         views.get_capstone_view,         name="capstone-detail"),
    path("capstone/",                           views.list_capstones_view,       name="capstone-list"),

    # Alignment Engine (Phase 2)
    path("alignment/analyze/",                  views.analyze_alignment_view,    name="alignment-analyze"),

    # Dual-Path Curriculum Generator (Phase 3)
    path("curriculum/roadmap/",                 views.generate_roadmap_view,             name="roadmap-generate"),
    path("curriculum/review/",                  views.review_capstone_submission_view,   name="capstone-ai-review"),

    # Rutuja — Skill Infrastructure
    path("categories/",                             views.SkillCategoryListCreateView.as_view(), name="categories"),
    path("skills/",                                 views.SkillListCreateView.as_view(),         name="skills-list"),
    path("skills/<int:pk>/",                        views.SkillDetailView.as_view(),             name="skills-detail"),
    path("my-skills/",                              views.UserSkillListCreateView.as_view(),     name="my-skills"),
    path("my-badges/",                              views.BadgeListView.as_view(),               name="my-badges"),
    path("badges/verify/<uuid:verification_hash>/", views.verify_badge,                         name="verify-badge"),

    # Soft Skills & Grammar (shared AI engine)
    path("soft-skills/analyze/",                    views.analyze_soft_skills_view,             name="soft-skills-analyze"),
    path("soft-skills/grammar/",                    views.correct_grammar_view,                 name="soft-skills-grammar"),
]
