from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import (
    UserProfile, ParsedCV, SkillSnapshot, GapReport, LearningPath, Capstone,
    Skill, SkillCategory, UserSkill, SkillBadge,
)
from .serializers import (
    UserSerializer, RegisterSerializer, UserProfileSerializer,
    CVUploadSerializer, CVResultSerializer,
    SkillSnapshotSerializer, SkillDecayReportSerializer,
    GapAnalyzeInputSerializer, GapReportSerializer,
    CurriculumGenerateInputSerializer, LearningPathSerializer,
    CapstoneGenerateInputSerializer, CapstoneReviewInputSerializer, CapstoneSerializer,
    SkillCategorySerializer, SkillSerializer, UserSkillSerializer, SkillBadgeSerializer,
    AlignmentInputSerializer, AlignmentReportSerializer,
    DualPathRoadmapSerializer, RoadmapInputSerializer,
    ReviewResultSerializer, ReviewInputSerializer,
)
from .services.cv_parser import parse_cv, parse_cv_from_pdf
from .services.skill_decay import analyze_skill_decay, calculate_overall_health
from .services.gap_mapper import analyze_gap
from .services.curriculum import build_learning_path
from .services.capstone import create_capstone, review_capstone_submission
from .logic.alignment_engine import analyze_jd_alignment
from .logic.curriculum_generator import generate_dual_path_roadmap, automated_ai_reviewer
from .soft_skills_service import analyze_soft_skills, correct_grammar
from .serializers import (
    SoftSkillsInputSerializer, SoftSkillsAnalysisSerializer,
    GrammarCorrectionInputSerializer, GrammarCorrectionResultSerializer,
)
from .gemini_bot import chat as gemini_chat
from .serializers import BotChatInputSerializer, BotChatResponseSerializer


# ── Health Check ──────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "app": "core_engine"})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_view(request):
    """
    GET /api/v1/dashboard/
    
    Returns aggregated dashboard data for the authenticated user:
    - Overall skill health score
    - Active/declining skills count
    - Market demand score
    - List of stale skills with trends
    
    Reads from SkillMap (v1 persistence model) instead of SkillSnapshot.
    """
    from django.utils import timezone
    from datetime import timedelta
    from core_engine.models import SkillMap
    
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    # Get all skills from SkillMap
    skill_map = SkillMap.objects.filter(user=request.user).order_by('-freshness_score')
    
    if not skill_map.exists():
        # Return empty dashboard for new users
        return Response({
            "score": 0,
            "status": "Moderate",
            "stats": {
                "active_skills": 0,
                "declining_skills": 0,
                "last_updated": timezone.now().isoformat(),
                "market_demand": 50,
            },
            "stale_skills": [],
            "ai_insight": "Upload your CV to get started with skill analysis."
        })
    
    # Calculate stats
    total_skills = skill_map.count()
    declining_skills = skill_map.filter(staleness_index__gte=60).count()
    active_skills = total_skills - declining_skills
    
    # Calculate overall score (average freshness)
    from django.db.models import Avg
    avg_freshness = skill_map.aggregate(Avg('freshness_score'))['freshness_score__avg'] or 0
    
    # Determine status based on avg_freshness
    if avg_freshness >= 85:
        status_label = "Excellent"
    elif avg_freshness >= 60:
        status_label = "Moderate"
    else:
        status_label = "Critical"
    
    # Calculate average market demand
    avg_demand = skill_map.aggregate(Avg('demand_score'))['demand_score__avg'] or 50
    
    # Get latest update time
    latest_skill = skill_map.first()
    last_updated = latest_skill.last_analyzed if latest_skill else timezone.now()
    
    # Build stale skills list
    stale_skills = []
    for skill in skill_map[:10]:  # Top 10 skills
        # Determine skill status
        if skill.staleness_index < 30:
            skill_status = "Stable"
        elif skill.staleness_index < 60:
            skill_status = "Declining"
        else:
            skill_status = "Critical"
        
        # Calculate trend (use growth_rate as proxy)
        trend = skill.growth_rate
        
        # Format last_used
        days_ago = (timezone.now().date() - skill.last_analyzed.date()).days
        if days_ago == 0:
            last_used = "today"
        elif days_ago == 1:
            last_used = "yesterday"
        elif days_ago < 7:
            last_used = f"{days_ago} days ago"
        elif days_ago < 30:
            last_used = f"{days_ago // 7} weeks ago"
        else:
            last_used = f"{days_ago // 30} months ago"
        
        stale_skills.append({
            "name": skill.skill_name,
            "status": skill_status,
            "trend": round(trend, 2),
            "last_used": last_used,
        })
    
    # Generate AI insight
    if declining_skills > total_skills * 0.5:
        ai_insight = f"Over half of your skills are declining. Consider updating {declining_skills} skills to stay competitive."
    elif declining_skills > 0:
        ai_insight = f"You have {declining_skills} declining skills. Focus on refreshing these to maintain your edge."
    else:
        ai_insight = "Great job! Your skills are up-to-date and market-relevant."
    
    return Response({
        "score": round(avg_freshness),
        "status": status_label,
        "stats": {
            "active_skills": active_skills,
            "declining_skills": declining_skills,
            "last_updated": last_updated.isoformat(),
            "market_demand": round(avg_demand),
        },
        "stale_skills": stale_skills,
        "ai_insight": ai_insight,
    })


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    from django.contrib.auth.models import User
    queryset           = User.objects.all()
    serializer_class   = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class   = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def partial_update(self, request, *args, **kwargs):
        # Support nested profile patch: { "profile": { "bio": "..." } }
        profile_data = request.data.get("profile")
        if profile_data and isinstance(profile_data, dict):
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile_serializer = UserProfileSerializer(profile, data=profile_data, partial=True)
            if profile_serializer.is_valid():
                profile_serializer.save()
            else:
                return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return super().partial_update(request, *args, **kwargs)


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
    serializer = CVUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        if serializer.validated_data.get("file"):
            file_bytes = serializer.validated_data["file"].read()
            extracted, raw_text = parse_cv_from_pdf(file_bytes)
        else:
            raw_text  = serializer.validated_data["text"]
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_parsed_cv(request, cv_id):
    try:
        parsed_cv = ParsedCV.objects.get(id=cv_id, user_profile__user=request.user)
    except ParsedCV.DoesNotExist:
        return Response({"error": "CV not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(CVResultSerializer(parsed_cv).data)


# ── Skill Decay ───────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_decay_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    latest_cv  = ParsedCV.objects.filter(user_profile=profile).first()
    if not latest_cv:
        return Response({"error": "No parsed CV found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        snapshots = analyze_skill_decay(latest_cv)
    except Exception as e:
        return Response({"error": f"Decay analysis failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    health = calculate_overall_health(snapshots)
    report = {**health, "total_skills": len(snapshots), "skills": snapshots}
    return Response(SkillDecayReportSerializer(report).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_decay_report_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    snapshots  = SkillSnapshot.objects.filter(user_profile=profile)
    if not snapshots.exists():
        return Response({"error": "No decay report found."}, status=status.HTTP_404_NOT_FOUND)

    latest_date      = snapshots.first().analyzed_at.date()
    latest_snapshots = [s for s in snapshots if s.analyzed_at.date() == latest_date]
    health           = calculate_overall_health(latest_snapshots)
    report           = {**health, "total_skills": len(latest_snapshots), "skills": latest_snapshots}
    return Response(SkillDecayReportSerializer(report).data)


# ── Gap Analysis ──────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_gap_view(request):
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
    try:
        report = GapReport.objects.get(id=report_id, user_profile__user=request.user)
    except GapReport.DoesNotExist:
        return Response({"error": "Gap report not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(GapReportSerializer(report).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_gap_reports_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    reports    = GapReport.objects.filter(user_profile=profile)
    return Response(GapReportSerializer(reports, many=True).data)


# ── Curriculum ────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_curriculum_view(request):
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
    try:
        learning_path = LearningPath.objects.get(id=path_id, user_profile__user=request.user)
    except LearningPath.DoesNotExist:
        return Response({"error": "Learning path not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(LearningPathSerializer(learning_path).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_learning_paths_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    paths      = LearningPath.objects.filter(user_profile=profile)
    return Response(LearningPathSerializer(paths, many=True).data)


# ── Capstone ──────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_capstone_view(request):
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

    capstone.refresh_from_db()
    return Response(CapstoneSerializer(capstone).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_capstone_view(request, capstone_id):
    try:
        capstone = Capstone.objects.get(id=capstone_id, user_profile__user=request.user)
    except Capstone.DoesNotExist:
        return Response({"error": "Capstone not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(CapstoneSerializer(capstone).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_capstones_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capstones  = Capstone.objects.filter(user_profile=profile)
    return Response(CapstoneSerializer(capstones, many=True).data)


# ── Rutuja's Infrastructure Views (stubs — to be implemented by Rutuja) ───────

class SkillCategoryListCreateView(generics.ListCreateAPIView):
    queryset         = SkillCategory.objects.all()
    serializer_class = SkillCategorySerializer

    def get_permissions(self):
        return [permissions.IsAdminUser()] if self.request.method == "POST" else [permissions.AllowAny()]


class SkillListCreateView(generics.ListCreateAPIView):
    serializer_class = SkillSerializer

    def get_queryset(self):
        qs = Skill.objects.select_related("category").all()
        difficulty = self.request.query_params.get("difficulty")
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        return qs

    def get_permissions(self):
        return [permissions.IsAdminUser()] if self.request.method == "POST" else [permissions.AllowAny()]


class SkillDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset         = Skill.objects.select_related("category").all()
    serializer_class = SkillSerializer

    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == "GET" else [permissions.IsAdminUser()]


class UserSkillListCreateView(generics.ListCreateAPIView):
    serializer_class   = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserSkill.objects.filter(user=self.request.user).select_related("skill")

    def perform_create(self, serializer):
        from django.db import IntegrityError
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"skill": "You are already enrolled in this skill."})


class BadgeListView(generics.ListAPIView):
    serializer_class   = SkillBadgeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SkillBadge.objects.filter(user=self.request.user).select_related("skill")


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_badge(request, verification_hash):
    try:
        badge = SkillBadge.objects.select_related("user", "skill").get(verification_hash=verification_hash)
        return Response({"valid": True, "username": badge.user.username,
                         "skill": badge.skill.name, "score": badge.score, "awarded_at": badge.awarded_at})
    except SkillBadge.DoesNotExist:
        return Response({"valid": False}, status=status.HTTP_404_NOT_FOUND)


# ── Alignment Engine ──────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_alignment_view(request):
    """
    POST /api/core/alignment/analyze/
    Body: { "jd_text": "..." }

    Compares user's CV SkillMap against a JD using 3-layer industry-agnostic analysis:
        - Explicit skills (tools, tech)
        - Functional skills (what they do)
        - Hidden talents (transferable competencies)

    Returns a precise gap list with bridge hints and transferable strengths.
    """
    serializer = AlignmentInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    latest_cv  = ParsedCV.objects.filter(user_profile=profile).first()

    if not latest_cv:
        return Response(
            {"error": "No parsed CV found. Please upload and parse your CV first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        report = analyze_jd_alignment(
            jd_text=serializer.validated_data["jd_text"],
            user_skill_map=latest_cv.extracted_skills,
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response(
            {"error": f"Alignment analysis failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(AlignmentReportSerializer(report).data, status=status.HTTP_200_OK)


# ── Dual-Path Curriculum Generator ───────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_roadmap_view(request):
    """
    POST /api/core/curriculum/roadmap/
    Body: { "jd_text": "...", "generate_capstones": true }

    Full pipeline:
        1. Parse JD → extract 3-layer skills
        2. Compare against user CV → identify precise gaps
        3. Generate dual-path roadmap (hacker + certified) per gap
        4. Generate unique mini-capstone per critical/moderate gap
    """
    serializer = RoadmapInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    latest_cv  = ParsedCV.objects.filter(user_profile=profile).first()

    if not latest_cv:
        return Response(
            {"error": "No parsed CV found. Please upload and parse your CV first."},
            status=status.HTTP_404_NOT_FOUND,
        )

    jd_text            = serializer.validated_data["jd_text"]
    generate_capstones = serializer.validated_data["generate_capstones"]

    # Get user's existing skills for capstone personalization
    tech_skills = latest_cv.extracted_skills.get("technical_skills", [])
    existing    = [s.get("skill", "") for s in tech_skills if s.get("skill")]

    try:
        # Step 1: Full alignment analysis
        alignment = analyze_jd_alignment(jd_text, latest_cv.extracted_skills)
        gap_list  = alignment.get("gaps", [])

        if not gap_list:
            return Response(
                {"message": "No skill gaps found. Your CV is a strong match for this JD.",
                 "overlap_pct": alignment.get("overall_overlap_pct", 100)},
                status=status.HTTP_200_OK,
            )

        # Step 2: Generate dual-path roadmap
        roadmap = generate_dual_path_roadmap(
            gap_list=gap_list,
            existing_skills=existing,
            generate_capstones=generate_capstones,
        )
        roadmap["role_title"]       = alignment.get("role_title", "")
        roadmap["industry_context"] = alignment.get("industry_context", "")
        roadmap["overall_overlap_pct"] = alignment.get("overall_overlap_pct", 0)
        roadmap["transferable_strengths"] = alignment.get("transferable_strengths", [])

    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response(
            {"error": f"Roadmap generation failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(DualPathRoadmapSerializer(roadmap).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_capstone_submission_view(request):
    """
    POST /api/core/curriculum/review/
    Body: { "capstone_task": {...}, "proof_of_work": "https://github.com/..." }

    Runs automated AI review of a capstone submission.
    Returns PASS/FAIL verdict with detailed criterion scores.
    """
    serializer = ReviewInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = automated_ai_reviewer(
            capstone_task=serializer.validated_data["capstone_task"],
            proof_of_work=serializer.validated_data["proof_of_work"],
        )
    except Exception as e:
        return Response(
            {"error": f"Review failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(ReviewResultSerializer(result).data, status=status.HTTP_200_OK)




# ── Soft Skills Analysis (Rutuja) ─────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_soft_skills_view(request):
    """POST /api/core/soft-skills/analyze/ — extract soft skills from text."""
    serializer = SoftSkillsInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    try:
        result = analyze_soft_skills(serializer.validated_data["text"])
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        return Response({"error": f"Soft skills analysis failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(SoftSkillsAnalysisSerializer(result).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def correct_grammar_view(request):
    """POST /api/core/soft-skills/grammar/ — grammar correction with optional NeonDB session save."""
    serializer = GrammarCorrectionInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    text         = serializer.validated_data["text"]
    request_type = request.data.get("request_type", "grammar")

    try:
        result = correct_grammar(text)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        return Response({"error": f"Grammar correction failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if request_type == "soft_skills":
        try:
            from .logic.neon_client import save_soft_skill_session
            session_id = save_soft_skill_session(user_id=request.user.id, original_text=text, result=result)
            result["session_id"]   = session_id
            result["request_type"] = "soft_skills"
        except Exception as e:
            result["session_id"]   = None
            result["neon_error"]   = f"Session save failed: {str(e)}"
            result["request_type"] = "soft_skills"

    return Response(GrammarCorrectionResultSerializer(result).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def soft_skill_sessions_view(request):
    """GET /api/core/soft-skills/sessions/ — past coaching sessions from NeonDB."""
    try:
        from .logic.neon_client import get_soft_skill_sessions
        sessions = get_soft_skill_sessions(request.user.id)
    except Exception as e:
        return Response({"error": f"Could not fetch sessions: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({"sessions": sessions, "count": len(sessions)}, status=status.HTTP_200_OK)


# ── Gemini AI Chatbot (Rutuja) ────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bot_chat_view(request):
    """POST /api/core/bot/chat/ — chat with the Gemini AI bot."""
    from .gemini_bot import BOT_MODES
    serializer = BotChatInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    mode = serializer.validated_data["mode"]
    if mode not in BOT_MODES:
        return Response(
            {"error": f"Invalid mode '{mode}'. Choose from: {', '.join(sorted(BOT_MODES))}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        result = gemini_chat(
            user_id=request.user.id,
            mode=mode,
            user_message=serializer.validated_data["message"],
            reset=serializer.validated_data["reset"],
        )
    except RuntimeError as e:
        return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Bot error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(BotChatResponseSerializer(result).data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def bot_reset_view(request, mode):
    """DELETE /api/core/bot/reset/<mode>/ — clear conversation history."""
    from .gemini_bot import _reset_session, BOT_MODES
    if mode not in BOT_MODES:
        return Response(
            {"error": f"Invalid mode '{mode}'. Choose from: {', '.join(sorted(BOT_MODES))}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        deleted = _reset_session(request.user.id, mode)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({"detail": f"{mode} conversation reset successfully.", "cleared": deleted}, status=status.HTTP_200_OK)


# ── Skill Tests ───────────────────────────────────────────────────────────────

from .models import SkillTest, TestAttempt
from .serializers import SkillTestSerializer, TestSubmitSerializer, TestAttemptSerializer
from .test_service import generate_skill_questions, score_answers
from django.db import IntegrityError


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_skill_test_view(request):
    """POST /api/core/tests/generate/ — generate a SkillTest for a given skill."""
    skill_id = request.data.get("skill_id")
    if not skill_id:
        return Response({"error": "skill_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        skill = Skill.objects.get(id=skill_id)
    except Skill.DoesNotExist:
        return Response({"error": "Skill not found."}, status=status.HTTP_404_NOT_FOUND)
    try:
        questions = generate_skill_questions(skill.name, skill.difficulty, num_questions=5)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    skill_test = SkillTest.objects.create(skill=skill, generated_by=request.user, questions=questions)
    return Response(SkillTestSerializer(skill_test).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_skill_test_view(request, test_id):
    """POST /api/core/tests/<test_id>/submit/ — submit answers and get scored result."""
    try:
        skill_test = SkillTest.objects.get(id=test_id)
    except SkillTest.DoesNotExist:
        return Response({"error": "Test not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = TestSubmitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    result = score_answers(skill_test.questions, serializer.validated_data["answers"])
    attempt = TestAttempt.objects.create(
        user=request.user, skill_test=skill_test,
        answers=serializer.validated_data["answers"],
        score=result["score"], passed=result["passed"],
    )

    skill_verified = False
    badge_hash     = None

    if result["passed"]:
        from django.utils import timezone as tz
        user_skill, created = UserSkill.objects.get_or_create(
            user=request.user, skill=skill_test.skill,
            defaults={"status": "verified", "score": result["score"], "completed_at": tz.now()},
        )
        if not created:
            user_skill.status = "verified"
            user_skill.score  = result["score"]
            user_skill.completed_at = tz.now()
            user_skill.save(update_fields=["status", "score", "completed_at"])
        badge, _ = SkillBadge.objects.get_or_create(
            user=request.user, skill=skill_test.skill,
            defaults={"score": result["score"]},
        )
        skill_verified = True
        badge_hash     = str(badge.verification_hash)

    return Response({**result, "attempt_id": attempt.id, "skill_verified": skill_verified, "badge_hash": badge_hash}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_attempts_view(request):
    """GET /api/core/tests/my-attempts/ — list all test attempts for the user."""
    attempts = TestAttempt.objects.filter(user=request.user).select_related("skill_test__skill")
    return Response(TestAttemptSerializer(attempts, many=True).data)


# ── Resources ─────────────────────────────────────────────────────────────────

from .models import LearningResource
from .serializers import LearningResourceSerializer
from .resource_service import fetch_and_store_resources


@api_view(["GET"])
@permission_classes([AllowAny])
def resources_view(request):
    """GET /api/core/resources/?skill_id=<id> — list resources for a skill."""
    skill_id = request.query_params.get("skill_id")
    if not skill_id:
        return Response({"error": "skill_id query param is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        skill = Skill.objects.get(id=skill_id)
    except Skill.DoesNotExist:
        return Response({"error": "Skill not found."}, status=status.HTTP_404_NOT_FOUND)
    resources = LearningResource.objects.filter(skill=skill)
    return Response(LearningResourceSerializer(resources, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommended_resources_view(request):
    """GET /api/core/resources/recommended/ — resources for the user's enrolled skills."""
    user_skill_ids = UserSkill.objects.filter(user=request.user).values_list("skill_id", flat=True)
    resources = LearningResource.objects.filter(skill_id__in=user_skill_ids).select_related("skill")[:20]
    return Response(LearningResourceSerializer(resources, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_resources_view(request, skill_id=None):
    """POST /api/core/resources/refresh/ — fetch fresh resources from APIs."""
    if skill_id is None:
        skill_id = request.data.get("skill_id")
    if not skill_id:
        return Response({"error": "skill_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        skill = Skill.objects.get(id=skill_id)
    except Skill.DoesNotExist:
        return Response({"error": "Skill not found."}, status=status.HTTP_404_NOT_FOUND)
    count = fetch_and_store_resources(skill)
    return Response({"added": count, "skill": skill.name})


# ── Portfolio ─────────────────────────────────────────────────────────────────

from .models import Portfolio
from .serializers import PortfolioSerializer
from .portfolio_service import generate_portfolio


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def portfolio_generate_view(request):
    """POST /api/core/portfolio/generate/ — build/rebuild the user's portfolio."""
    has_verified = UserSkill.objects.filter(user=request.user, status="verified").exists()
    if not has_verified:
        return Response({"error": "You need at least one verified skill to generate a portfolio."}, status=status.HTTP_400_BAD_REQUEST)
    portfolio = generate_portfolio(request.user)
    return Response(PortfolioSerializer(portfolio).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def portfolio_me_view(request):
    """GET /api/core/portfolio/me/ — get the authenticated user's portfolio."""
    try:
        portfolio = Portfolio.objects.get(user=request.user)
    except Portfolio.DoesNotExist:
        return Response({"error": "Portfolio not found. Generate it first."}, status=status.HTTP_404_NOT_FOUND)
    return Response(PortfolioSerializer(portfolio).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def portfolio_public_view(request, slug):
    """GET /api/core/portfolio/<slug>/ — public portfolio view."""
    try:
        portfolio = Portfolio.objects.get(slug=slug, is_public=True)
    except Portfolio.DoesNotExist:
        return Response({"error": "Portfolio not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(PortfolioSerializer(portfolio).data)
