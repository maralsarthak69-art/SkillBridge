from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/core/", include("core_engine.urls")),
    path("api-auth/", include("rest_framework.urls")),       # browsable API login

    # JWT Auth
    path("api/auth/token/",         TokenObtainPairView.as_view(),  name="token-obtain"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(),     name="token-refresh"),
    path("api/auth/token/verify/",  TokenVerifyView.as_view(),      name="token-verify"),
]

# Serve media files locally in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=getattr(settings, "MEDIA_ROOT", ""))
