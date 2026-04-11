"""
v1/roadmap_views.py — Roadmap Dashboard API

GET  /api/v1/roadmap/                       → week-by-week plan for the user
PATCH /api/v1/roadmap/week/<week>/status/   → update a single week's status
"""

from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core_engine.models import RoadmapWeek


# ── Serializer ────────────────────────────────────────────────────────────────

class RoadmapWeekSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RoadmapWeek
        fields = ["week", "title", "skill", "level", "trending", "resources", "task", "status"]


# ── View 1: GET /api/v1/roadmap/ ──────────────────────────────────────────────

class RoadmapView(generics.ListAPIView):
    """Returns all weeks for the authenticated user, ordered by week number."""
    serializer_class   = RoadmapWeekSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RoadmapWeek.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        return Response({"weeks": self.get_serializer(qs, many=True).data})


# ── View 2: PATCH /api/v1/roadmap/week/<week>/status/ ────────────────────────

class WeekStatusUpdateView(APIView):
    """Updates the status of a single week. Returns 204 on success."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, week):
        status_val = request.data.get("status")
        valid = {"not_started", "in_progress", "completed"}

        if status_val not in valid:
            return Response(
                {"detail": f"status must be one of {sorted(valid)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = RoadmapWeek.objects.filter(
            user=request.user, week=week
        ).update(status=status_val)

        if not updated:
            return Response(
                {"detail": "Week not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
