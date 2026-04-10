from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import UserProfile, ParsedCV, SkillSnapshot, GapReport, LearningPath, Capstone
from .serializers import (
    CVUploadSerializer, CVResultSerializer, UserProfileSerializer,
    SkillSnapshotSerializer, SkillDecayReportSerializer,
    GapAnalyzeInputSerializer, GapReportSerializer,
    CurriculumGenerateInputSerializer, LearningPathSerializer,
    CapstoneGenerateInputSerializer, CapstoneReviewInputSerializer, CapstoneSerializer,
)
from .services.cv_parser import parse_cv, parse_cv_from_pdf
from .services.skill_decay import analyze_skill_decay, calculate_overall_health
from .services.gap_mapper import analyze_gap
from .services.curriculum import build_learning_path
from .services.capstone import create_capstone, review_capstone_submission


# ── Health Check ──────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "app": "core_engine"})


# ── User Profile ──────────────────────────────────────────────────────────────

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def user_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "GET":
        return Response(UserProfileSerializer(profile).data)

    serializer = UserProfileSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── CV Parse ──────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def parse_cv_view(request):
    """
    POST /api/core/cv/parse/
    Accepts: multipart file upload (key: 'file') OR JSON body with 'text' key.
    Returns: structured skill extraction result.
    """
    serializer = CVUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        if serializer.validated_data.get("file"):
            file_bytes = serializer.validated_data["file"].read()
            extracted, raw_text = parse_cv_from_pdf(file_bytes)
        else:
            raw_text = serializer.validated_data["text"]
            extracted = parse_cv(raw_text)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response({"error": f"Parsing failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    parsed_cv = ParsedCV.objects.create(
        user_profile=profile,
        raw_text=raw_text,
        extracted_skills=extracted,
        pii_flagged=extracted.get("pii_detected", False),
    )

    return Response(CVResultSerializer(parsed_cv).data, status=status.HTTP_201_CREATED)


# ── CV Retrieve ───────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_parsed_cv(request, cv_id):
    """
    GET /api/core/cv/<cv_id>/
    Returns a previously parsed CV result. Only accessible by the owner.
    """
    try:
        parsed_cv = ParsedCV.objects.get(id=cv_id, user_profile__user=request.user)
    except ParsedCV.DoesNotExist:
        return Response({"error": "CV not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(CVResultSerializer(parsed_cv).data)


# ── Skill Decay ───────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_decay_view(request):
    """
    POST /api/core/skills/decay/analyze/
    Runs decay analysis on the user's latest parsed CV.
    Returns a full decay report with per-skill freshness scores.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    latest_cv = ParsedCV.objects.filter(user_profile=profile).first()
    if not latest_cv:
        return Response(
            {"error": "No parsed CV found. Please upload and parse a CV first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        snapshots = analyze_skill_decay(latest_cv)
    except Exception as e:
        return Response({"error": f"Decay analysis failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    overall = calculate_overall_health(snapshots)

    report = {
        "overall_health_score": overall,
        "total_skills": len(snapshots),
        "fresh_skills": sum(1 for s in snapshots if s.freshness_score >= 85),
        "relevant_skills": sum(1 for s in snapshots if 70 <= s.freshness_score < 85),
        "stale_skills": sum(1 for s in snapshots if s.freshness_score < 70),
        "skills": snapshots,
    }

    return Response(SkillDecayReportSerializer(report).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_decay_report_view(request):
    """
    GET /api/core/skills/decay/
    Returns the most recent decay report for the authenticated user.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    snapshots = SkillSnapshot.objects.filter(user_profile=profile)
    if not snapshots.exists():
        return Response(
            {"error": "No decay report found. Run /skills/decay/analyze/ first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get only the latest batch (most recent analyzed_at date)
    latest_date = snapshots.first().analyzed_at.date()
    latest_snapshots = [s for s in snapshots if s.analyzed_at.date() == latest_date]

    overall = calculate_overall_health(latest_snapshots)

    report = {
        "overall_health_score": overall,
        "total_skills": len(latest_snapshots),
        "fresh_skills": sum(1 for s in latest_snapshots if s.freshness_score >= 85),
        "relevant_skills": sum(1 for s in latest_snapshots if 70 <= s.freshness_score < 85),
        "stale_skills": sum(1 for s in latest_snapshots if s.freshness_score < 70),
        "skills": latest_snapshots,
    }

    return Response(SkillDecayReportSerializer(report).data)


# ── Gap Analysis ──────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_gap_view(request):
    """
    POST /api/core/gap/analyze/
    Body: { "jd_text": "...", "target_role": "..." (optional) }
    Extracts required skills from JD, diffs against user CV, returns gap report.
    """
    serializer = GapAnalyzeInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        report = analyze_gap(
            user_profile=profile,
            jd_text=serializer.validated_data["jd_text"],
            target_role=serializer.validated_data.get("target_role", ""),
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response({"error": f"Gap analysis failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(GapReportSerializer(report).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_gap_report_view(request, report_id):
    """
    GET /api/core/gap/<report_id>/
    Returns a specific gap report. Owner-only.
    """
    try:
        report = GapReport.objects.get(id=report_id, user_profile__user=request.user)
    except GapReport.DoesNotExist:
        return Response({"error": "Gap report not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(GapReportSerializer(report).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_gap_reports_view(request):
    """
    GET /api/core/gap/
    Lists all gap reports for the authenticated user, most recent first.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    reports = GapReport.objects.filter(user_profile=profile)
    return Response(GapReportSerializer(reports, many=True).data)


# ── Curriculum ────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_curriculum_view(request):
    """
    POST /api/core/curriculum/generate/
    Body: { "gap_report_id": int, "path_type": "hacker" | "certified" }
    Generates a full ordered learning path from a gap report.
    """
    serializer = CurriculumGenerateInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        learning_path = build_learning_path(
            user_profile=profile,
            gap_report_id=serializer.validated_data["gap_report_id"],
            path_type=serializer.validated_data["path_type"],
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": f"Curriculum generation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(LearningPathSerializer(learning_path).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_learning_path_view(request, path_id):
    """
    GET /api/core/curriculum/<path_id>/
    Returns a specific learning path. Owner-only.
    """
    try:
        learning_path = LearningPath.objects.get(id=path_id, user_profile__user=request.user)
    except LearningPath.DoesNotExist:
        return Response({"error": "Learning path not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(LearningPathSerializer(learning_path).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_learning_paths_view(request):
    """
    GET /api/core/curriculum/
    Lists all learning paths for the authenticated user, most recent first.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    paths = LearningPath.objects.filter(user_profile=profile)
    return Response(LearningPathSerializer(paths, many=True).data)


# ── Capstone ──────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_capstone_view(request):
    """
    POST /api/core/capstone/generate/
    Body: { "gap_report_id": int }
    Generates a unique capstone project brief from a gap report.
    """
    serializer = CapstoneGenerateInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        capstone = create_capstone(
            user_profile=profile,
            gap_report_id=serializer.validated_data["gap_report_id"],
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": f"Capstone generation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(CapstoneSerializer(capstone).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_capstone_view(request, capstone_id):
    """
    POST /api/core/capstone/<capstone_id>/review/
    Body: { "github_url": "https://github.com/..." }
    Runs LLM review of the submission against the capstone rubric.
    """
    serializer = CapstoneReviewInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        capstone = Capstone.objects.get(id=capstone_id, user_profile__user=request.user)
    except Capstone.DoesNotExist:
        return Response({"error": "Capstone not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        review_capstone_submission(capstone, serializer.validated_data["github_url"])
    except Exception as e:
        return Response({"error": f"Review failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Refresh from DB so the nested review is included in the response
    capstone.refresh_from_db()
    return Response(CapstoneSerializer(capstone).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_capstone_view(request, capstone_id):
    """
    GET /api/core/capstone/<capstone_id>/
    Returns a specific capstone with its review if available.
    """
    try:
        capstone = Capstone.objects.get(id=capstone_id, user_profile__user=request.user)
    except Capstone.DoesNotExist:
        return Response({"error": "Capstone not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(CapstoneSerializer(capstone).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_capstones_view(request):
    """
    GET /api/core/capstone/
    Lists all capstones for the authenticated user.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capstones = Capstone.objects.filter(user_profile=profile)
    return Response(CapstoneSerializer(capstones, many=True).data)
