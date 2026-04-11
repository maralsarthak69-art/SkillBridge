from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from core_engine.auth import EmailTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path("api/core/", include("core_engine.urls")),
    path("api/v1/",   include("core_engine.v1.urls")),

    # JWT Auth — kept here for backwards compat (/api/auth/token/)
    path("api/auth/token/",         EmailTokenObtainPairView.as_view(),  name="token-obtain"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(),          name="token-refresh"),
    path("api/auth/token/verify/",  TokenVerifyView.as_view(),           name="token-verify"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=getattr(settings, "MEDIA_ROOT", ""))
