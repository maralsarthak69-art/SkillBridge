from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
from django.contrib.auth.models import User
from .models import UserProfile, SkillCategory, Skill, UserSkill, SkillBadge, ResumeParseResult, SkillTest, TestAttempt, LearningResource, Portfolio, PortfolioSkillEntry
from .serializers import (
    UserSerializer, RegisterSerializer, UserProfileSerializer,
    SkillCategorySerializer, SkillSerializer,
    UserSkillSerializer, SkillBadgeSerializer,
    ResumeUploadSerializer, ResumeParseResultSerializer,
    SkillTestSerializer, TestSubmitSerializer, TestAttemptSerializer,
    LearningResourceSerializer, PortfolioSerializer,
)
from .resume_service import validate_resume_file, extract_text_from_resume, extract_skills_with_ai
from .test_service import generate_skill_questions, score_answers
from .resource_service import fetch_and_store_resources
from .portfolio_service import generate_portfolio, generate_portfolio_pdf


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health_check(request):
    return Response({"status": "ok", "app": "core_engine"})


# ──────────────────────────────────────────────
# Auth — Register & Profile
# ──────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """POST /api/core/auth/register/ — create a new user"""
    queryset         = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/core/auth/me/ — view or update own profile"""
    serializer_class   = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        # Allow partial update of nested UserProfile fields
        profile_data = request.data.get("profile", {})
        if profile_data:
            profile = request.user.profile
            serializer = UserProfileSerializer(profile, data=profile_data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return super().patch(request, *args, **kwargs)


# ──────────────────────────────────────────────
# Skill Categories
# ──────────────────────────────────────────────

class SkillCategoryListCreateView(generics.ListCreateAPIView):
    """GET /api/core/categories/ — list all | POST — create (admin only)"""
    queryset           = SkillCategory.objects.all()
    serializer_class   = SkillCategorySerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]


# ──────────────────────────────────────────────
# Skills
# ──────────────────────────────────────────────

class SkillListCreateView(generics.ListCreateAPIView):
    """GET /api/core/skills/ — list all | POST — create (admin only)"""
    queryset         = Skill.objects.select_related("category").all()
    serializer_class = SkillSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        category   = self.request.query_params.get("category")
        difficulty = self.request.query_params.get("difficulty")
        search     = self.request.query_params.get("search")
        if category:
            qs = qs.filter(category__name__icontains=category)
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class SkillDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/core/skills/<id>/"""
    queryset         = Skill.objects.select_related("category").all()
    serializer_class = SkillSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]


# ──────────────────────────────────────────────
# User Skills (Progress)
# ──────────────────────────────────────────────

class UserSkillListCreateView(generics.ListCreateAPIView):
    """GET /api/core/my-skills/ — list enrolled skills | POST — enroll in a skill"""
    serializer_class   = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserSkill.objects.filter(user=self.request.user).select_related("skill")

    def perform_create(self, serializer):
        skill = serializer.validated_data.get("skill")
        if UserSkill.objects.filter(user=self.request.user, skill=skill).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": "You are already enrolled in this skill."})
        serializer.save(user=self.request.user)


class UserSkillDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/core/my-skills/<id>/"""
    serializer_class   = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserSkill.objects.filter(user=self.request.user)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        # Prevent downgrading a verified skill
        new_status = request.data.get("status")
        if instance.status == "verified" and new_status in ("enrolled", "in_progress"):
            return Response(
                {"detail": "Cannot downgrade a verified skill."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().patch(request, *args, **kwargs)


# ──────────────────────────────────────────────
# Badges
# ──────────────────────────────────────────────

class BadgeListView(generics.ListAPIView):
    """GET /api/core/my-badges/ — list all earned badges"""
    serializer_class   = SkillBadgeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SkillBadge.objects.filter(user=self.request.user).select_related("skill")


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def verify_badge(request, verification_hash):
    """GET /api/core/badges/verify/<uuid>/ — public badge verification"""
    try:
        badge = SkillBadge.objects.select_related("user", "skill").get(verification_hash=verification_hash)
        return Response({
            "valid":      True,
            "username":   badge.user.username,
            "skill":      badge.skill.name,
            "score":      badge.score,
            "awarded_at": badge.awarded_at,
        })
    except SkillBadge.DoesNotExist:
        return Response({"valid": False, "detail": "Badge not found."}, status=status.HTTP_404_NOT_FOUND)


# ──────────────────────────────────────────────
# Resume Upload & Parse
# ──────────────────────────────────────────────

class ResumeUploadView(generics.GenericAPIView):
    """
    POST /api/core/resume/upload/
    Accepts a PDF or DOCX file, validates it, uploads to S3 (or local media),
    and saves the URL back to the user's profile.
    """
    serializer_class   = ResumeUploadSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data["resume"]

        # Validate type and size
        try:
            validate_resume_file(file)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Save file — django-storages will auto-route to S3 if configured,
        # otherwise saves to MEDIA_ROOT locally
        profile = request.user.profile
        filename = f"resumes/{request.user.id}_{file.name}"

        from django.core.files.storage import default_storage
        saved_path = default_storage.save(filename, file)
        file_url   = default_storage.url(saved_path)

        # Persist URL on profile
        profile.resume_url = file_url
        profile.save(update_fields=["resume_url"])

        return Response({
            "detail":     "Resume uploaded successfully.",
            "resume_url": file_url,
        }, status=status.HTTP_200_OK)


class ResumeParseView(generics.GenericAPIView):
    """
    POST /api/core/resume/parse/
    Reads the user's uploaded resume, extracts text, sends to Groq AI,
    and returns + stores the list of detected skills.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = ResumeParseResultSerializer

    def post(self, request, *args, **kwargs):
        profile = request.user.profile

        if not profile.resume_url:
            return Response(
                {"detail": "No resume uploaded yet. Please upload a resume first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch the file for text extraction
        from django.core.files.storage import default_storage
        import re

        # Derive storage path from URL
        url = profile.resume_url
        # Strip domain/media prefix to get relative storage path
        media_prefix = getattr(settings, "MEDIA_URL", "/media/")
        if media_prefix in url:
            storage_path = url.split(media_prefix)[-1]
        else:
            # S3 URL — extract path after bucket domain
            storage_path = re.sub(r'^https?://[^/]+/', '', url)

        try:
            with default_storage.open(storage_path, "rb") as f:
                resume_text = extract_text_from_resume(f)
        except Exception as e:
            return Response(
                {"detail": f"Could not read resume file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not resume_text.strip():
            return Response(
                {"detail": "Could not extract text from resume. Ensure the file is not scanned/image-only."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # AI extraction
        extracted_skills = extract_skills_with_ai(resume_text)

        # Persist result
        parse_result, _ = ResumeParseResult.objects.update_or_create(
            user=request.user,
            defaults={"raw_text": resume_text, "extracted_skills": extracted_skills},
        )

        return Response({
            "detail":           "Resume parsed successfully.",
            "extracted_skills": extracted_skills,
            "parsed_at":        parse_result.parsed_at,
        }, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────
# Test Generation
# ──────────────────────────────────────────────

class GenerateTestView(generics.GenericAPIView):
    """
    POST /api/core/tests/generate/
    Body: { "skill_id": 1 } OR { "skill_name": "Python" }
    Generates an AI test for the given skill and returns questions (without answers).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = SkillTestSerializer

    def post(self, request, *args, **kwargs):
        skill_id   = request.data.get("skill_id")
        skill_name = request.data.get("skill_name")

        if not skill_id and not skill_name:
            return Response({"detail": "skill_id or skill_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if skill_id:
                skill = Skill.objects.get(id=skill_id)
            else:
                skill = Skill.objects.get(name__iexact=skill_name)
        except Skill.DoesNotExist:
            return Response({"detail": "Skill not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            questions = generate_skill_questions(skill.name, skill.difficulty)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        if not questions:
            return Response(
                {"detail": "AI could not generate valid questions. Try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        skill_test = SkillTest.objects.create(
            skill=skill,
            questions=questions,
            generated_by=request.user,
        )

        serializer = SkillTestSerializer(skill_test)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────
# Test Submission & Scoring (Steps 3.4 + 3.5)
# ──────────────────────────────────────────────

class SubmitTestView(generics.GenericAPIView):
    """
    POST /api/core/tests/<test_id>/submit/
    Body: { "answers": {"0": 2, "1": 0, "2": 3, ...} }
    Scores the attempt, updates UserSkill status if passed.
    """
    serializer_class   = TestSubmitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, test_id, *args, **kwargs):
        # Fetch the test
        try:
            skill_test = SkillTest.objects.select_related("skill").get(id=test_id)
        except SkillTest.DoesNotExist:
            return Response({"detail": "Test not found."}, status=status.HTTP_404_NOT_FOUND)

        # Validate submitted answers
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data["answers"]

        # Score the attempt
        result = score_answers(skill_test.questions, answers)

        # Save the attempt
        attempt = TestAttempt.objects.create(
            user=request.user,
            skill_test=skill_test,
            answers=answers,
            score=result["score"],
            passed=result["passed"],
        )

        # ── Step 3.5: Auto-update UserSkill status on pass ──
        skill_verified = False
        badge_hash     = None
        if result["passed"]:
            user_skill, created = UserSkill.objects.get_or_create(
                user=request.user,
                skill=skill_test.skill,
                defaults={"status": "enrolled"},
            )
            # Only upgrade — never downgrade a previously verified skill
            if user_skill.status != "verified" or (user_skill.score or 0) < result["score"]:
                user_skill.status       = "verified"
                user_skill.score        = result["score"]
                user_skill.completed_at = timezone.now()
                user_skill.save(update_fields=["status", "score", "completed_at"])
            skill_verified = True

            # ── Step 3.6: Auto Badge Awarding ──
            badge, badge_created = SkillBadge.objects.get_or_create(
                user=request.user,
                skill=skill_test.skill,
                defaults={"score": result["score"]},
            )
            # If badge already exists but user scored higher, update the score
            if not badge_created and result["score"] > badge.score:
                badge.score = result["score"]
                badge.save(update_fields=["score"])

            badge_hash = str(badge.verification_hash)

        return Response({
            "attempt_id":         attempt.id,
            "skill":              skill_test.skill.name,
            "score":              result["score"],
            "passed":             result["passed"],
            "skill_verified":     skill_verified,
            "badge_hash":         badge_hash,
            "correct":            result["correct"],
            "total":              result["total"],
            "breakdown":          result["breakdown"],
            "message":            "Congratulations! Skill verified and badge awarded." if result["passed"] else f"Score {result['score']}% — need 70% to pass. Try again!",
        }, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────
# Test Attempt History
# ──────────────────────────────────────────────

class MyAttemptsView(generics.ListAPIView):
    """GET /api/core/tests/my-attempts/ — list all past test attempts"""
    serializer_class   = TestAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TestAttempt.objects.filter(
            user=self.request.user
        ).select_related("skill_test__skill")


# ──────────────────────────────────────────────
# Learning Resources
# ──────────────────────────────────────────────

class ResourceListView(generics.ListAPIView):
    """
    GET /api/core/resources/?skill_id=1
    Returns stored resources for a skill. Fetches fresh ones from APIs if none exist.
    """
    serializer_class   = LearningResourceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        skill_id = self.request.query_params.get("skill_id")
        if not skill_id:
            return LearningResource.objects.none()
        return LearningResource.objects.filter(skill_id=skill_id).select_related("skill")

    def list(self, request, *args, **kwargs):
        skill_id = request.query_params.get("skill_id")
        if not skill_id:
            return Response({"detail": "skill_id query param is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            skill = Skill.objects.get(id=skill_id)
        except Skill.DoesNotExist:
            return Response({"detail": "Skill not found."}, status=status.HTTP_404_NOT_FOUND)

        # If no resources stored yet, fetch from APIs now
        if not LearningResource.objects.filter(skill=skill).exists():
            fetch_and_store_resources(skill)

        return super().list(request, *args, **kwargs)


class ResourceRefreshView(generics.GenericAPIView):
    """
    POST /api/core/resources/refresh/
    Body: { "skill_id": 1 }
    Force re-fetches resources from YouTube and Udemy for a skill.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LearningResourceSerializer

    def post(self, request, *args, **kwargs):
        skill_id = request.data.get("skill_id")
        if not skill_id:
            return Response({"detail": "skill_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            skill = Skill.objects.get(id=skill_id)
        except Skill.DoesNotExist:
            return Response({"detail": "Skill not found."}, status=status.HTTP_404_NOT_FOUND)

        new_count = fetch_and_store_resources(skill)
        total     = LearningResource.objects.filter(skill=skill).count()

        return Response({
            "detail":     f"Fetched {new_count} new resources.",
            "total":      total,
            "skill":      skill.name,
        }, status=status.HTTP_200_OK)


class RecommendedResourcesView(generics.ListAPIView):
    """
    GET /api/core/resources/recommended/
    Returns resources for all skills the authenticated user is enrolled in.
    """
    serializer_class   = LearningResourceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        enrolled_skill_ids = UserSkill.objects.filter(
            user=self.request.user
        ).values_list("skill_id", flat=True)

        return LearningResource.objects.filter(
            skill_id__in=enrolled_skill_ids
        ).select_related("skill").order_by("skill__name", "source")


# ──────────────────────────────────────────────
# Portfolio
# ──────────────────────────────────────────────

class PortfolioGenerateView(generics.GenericAPIView):
    """
    POST /api/core/portfolio/generate/
    Generates or regenerates the authenticated user's portfolio
    from all their verified skills and badges.
    """
    serializer_class   = PortfolioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        verified_count = UserSkill.objects.filter(
            user=request.user, status="verified"
        ).count()

        if verified_count == 0:
            return Response(
                {"detail": "You have no verified skills yet. Pass at least one skill test to generate a portfolio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        portfolio  = generate_portfolio(request.user)
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PortfolioPublicView(generics.RetrieveAPIView):
    """
    GET /api/core/portfolio/<slug>/
    Public endpoint — no authentication required.
    Returns the full portfolio for sharing.
    """
    serializer_class   = PortfolioSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field       = "slug"

    def get_queryset(self):
        return Portfolio.objects.filter(is_public=True).select_related("user", "user__profile")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class PortfolioExportView(generics.GenericAPIView):
    """
    GET /api/core/portfolio/<slug>/export/
    Public endpoint — returns a downloadable PDF of the portfolio.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class   = PortfolioSerializer

    def get(self, request, slug, *args, **kwargs):
        try:
            portfolio = Portfolio.objects.get(slug=slug, is_public=True)
        except Portfolio.DoesNotExist:
            return Response({"detail": "Portfolio not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            pdf_bytes = generate_portfolio_pdf(portfolio)
        except Exception as e:
            return Response(
                {"detail": f"PDF generation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="skillbridge-{slug}.pdf"'
        return response


class MyPortfolioView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/core/portfolio/me/
    View or update own portfolio settings (e.g. toggle is_public).
    """
    serializer_class   = PortfolioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        try:
            return Portfolio.objects.get(user=self.request.user)
        except Portfolio.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Portfolio not found. Generate it first via POST /api/core/portfolio/generate/")
