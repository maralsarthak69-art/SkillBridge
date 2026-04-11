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
    queryset         = Skill.objects.select_related("category").all()
    serializer_class = SkillSerializer

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
        serializer.save(user=self.request.user)


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


# ── Soft Skills Analysis ──────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_soft_skills_view(request):
    """
    POST /api/core/soft-skills/analyze/
    Body: { "text": "resume or bio text here..." }

    Uses the existing Groq AI engine (same client as alignment_engine.py)
    to extract and analyze soft skills from any professional text.

    Returns:
        soft_skills:      list of skills with confidence, evidence, development tip
        top_strengths:    top 3 strongest soft skills
        areas_to_develop: up to 3 skills to work on
        overall_profile:  2-sentence summary
    """
    serializer = SoftSkillsInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = analyze_soft_skills(serializer.validated_data["text"])
    except ValueError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as e:
        return Response(
            {"error": f"Soft skills analysis failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(SoftSkillsAnalysisSerializer(result).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def correct_grammar_view(request):
    """
    POST /api/core/soft-skills/grammar/
    Body: { "text": "...", "request_type": "soft_skills" }

    If request_type is "soft_skills":
      - Uses the existing Groq AI engine with a grammar coach system prompt
      - Saves the full transcript and corrections to soft_skill_sessions in NeonDB
      - Returns AI feedback as JSON

    Always returns:
        corrected_text:    the improved version of the text
        changes:           list of {original, corrected, reason}
        improvement_score: 0-100
        readability_level: entry | mid | senior | executive
        session_id:        NeonDB session id (only when request_type=soft_skills)
    """
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
        return Response(
            {"error": f"Grammar correction failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ── Soft Skills path: save transcript to NeonDB ───────────────────────────
    if request_type == "soft_skills":
        try:
            from .logic.neon_client import save_soft_skill_session
            session_id = save_soft_skill_session(
                user_id=request.user.id,
                original_text=text,
                result=result,
            )
            result["session_id"]   = session_id
            result["request_type"] = "soft_skills"
        except Exception as e:
            # Non-fatal — still return the AI result even if NeonDB save fails
            result["session_id"]    = None
            result["neon_error"]    = f"Session save failed: {str(e)}"
            result["request_type"]  = "soft_skills"

    return Response(GrammarCorrectionResultSerializer(result).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def soft_skill_sessions_view(request):
    """
    GET /api/core/soft-skills/sessions/
    Returns all past soft skills grammar coaching sessions for the user from NeonDB.
    """
    try:
        from .logic.neon_client import get_soft_skill_sessions
        sessions = get_soft_skill_sessions(request.user.id)
    except Exception as e:
        return Response(
            {"error": f"Could not fetch sessions: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({"sessions": sessions, "count": len(sessions)}, status=status.HTTP_200_OK)


# ── Gemini AI Chatbot ─────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bot_chat_view(request):
    """
    POST /api/core/bot/chat/
    Body: { "mode": "english_coach|interview_coach|conflict_coach", "message": "...", "reset": false }

    Three coaching modes:

    english_coach:
        - Corrects grammar and vocabulary in real-time
        - Encourages and asks follow-up questions to keep the user practicing
        - Returns: reply, corrections, encouragement, follow_up

    interview_coach:
        - Acts as a hiring manager conducting a behavioral interview
        - Evaluates answers using the STARR method
        - Returns: reply, starr_evaluation, overall_score, strength, improvement, next_question

    conflict_coach:
        - Roleplays as a difficult boss or client
        - Trains professional diplomacy and negotiation
        - Returns: in_character_reply, coach_feedback, scenario_escalation, diplomacy_score

    Set "reset": true to start a fresh conversation in any mode.
    Conversation history is persisted in NeonDB per user per mode.
    """
    serializer = BotChatInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = gemini_chat(
            user_id=request.user.id,
            mode=serializer.validated_data["mode"],
            user_message=serializer.validated_data["message"],
            reset=serializer.validated_data["reset"],
        )
    except RuntimeError as e:
        return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(
            {"error": f"Bot error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(BotChatResponseSerializer(result).data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def bot_reset_view(request, mode):
    """
    DELETE /api/core/bot/reset/<mode>/
    Clears conversation history for the given mode so the user can start fresh.
    """
    from .gemini_bot import _reset_session, BOT_MODES
    if mode not in BOT_MODES:
        return Response(
            {"error": f"Invalid mode. Choose from: {', '.join(BOT_MODES)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        _reset_session(request.user.id, mode)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"detail": f"{mode} conversation reset successfully."}, status=status.HTTP_200_OK)
