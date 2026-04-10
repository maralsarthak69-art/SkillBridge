from django.urls import path
from . import views

urlpatterns = [
    # Health
    path("health/",                             views.health_check,                name="health-check"),

    # Auth
    path("auth/register/",                      views.RegisterView.as_view(),       name="register"),
    path("auth/me/",                            views.MeView.as_view(),             name="me"),

    # Skill Categories
    path("categories/",                         views.SkillCategoryListCreateView.as_view(), name="categories"),

    # Skills
    path("skills/",                             views.SkillListCreateView.as_view(),  name="skills-list"),
    path("skills/<int:pk>/",                    views.SkillDetailView.as_view(),      name="skills-detail"),

    # User Skill Progress
    path("my-skills/",                          views.UserSkillListCreateView.as_view(),  name="my-skills"),
    path("my-skills/<int:pk>/",                 views.UserSkillDetailView.as_view(),      name="my-skills-detail"),

    # Badges
    path("my-badges/",                          views.BadgeListView.as_view(),            name="my-badges"),
    path("badges/verify/<uuid:verification_hash>/", views.verify_badge,                  name="verify-badge"),

    # Resume
    path("resume/upload/",                      views.ResumeUploadView.as_view(),         name="resume-upload"),
    path("resume/parse/",                       views.ResumeParseView.as_view(),          name="resume-parse"),

    # Tests
    path("tests/generate/",                     views.GenerateTestView.as_view(),         name="test-generate"),
    path("tests/<int:test_id>/submit/",         views.SubmitTestView.as_view(),           name="test-submit"),
    path("tests/my-attempts/",                  views.MyAttemptsView.as_view(),           name="my-attempts"),

    # Learning Resources
    path("resources/",                          views.ResourceListView.as_view(),         name="resources"),
    path("resources/refresh/",                  views.ResourceRefreshView.as_view(),      name="resources-refresh"),
    path("resources/recommended/",              views.RecommendedResourcesView.as_view(), name="resources-recommended"),

    # Portfolio
    path("portfolio/generate/",                 views.PortfolioGenerateView.as_view(),    name="portfolio-generate"),
    path("portfolio/me/",                       views.MyPortfolioView.as_view(),          name="portfolio-me"),
    path("portfolio/<slug:slug>/",              views.PortfolioPublicView.as_view(),      name="portfolio-public"),
    path("portfolio/<slug:slug>/export/",       views.PortfolioExportView.as_view(),      name="portfolio-export"),
]
