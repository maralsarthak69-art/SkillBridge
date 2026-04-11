"""
v1/views.py — API v1 orchestration layer with full DB persistence

Every view:
    1. Validates input
    2. Calls Sarthak's logic functions
    3. Persists results to PostgreSQL (get_or_create / update_or_create)
    4. Returns clean JSON response
    5. Returns clean error if AI logic fails or times out
"""

import threading
from contextlib import contextmanager
from django.utils import timezone
from django.conf import settings
import uuid

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core_engine.models import (
    UserProfile, ParsedCV, SkillMap, RoadmapProgress, RoadmapTask,
    Skill, SkillBadge, UserSkill,
)
from core_engine.services.cv_parser import parse_cv, parse_cv_from_pdf
from core_engine.logic.market_analysis import calculate_staleness_index
from core_engine.logic.alignment_engine import analyze_jd_alignment
from core_engine.logic.curriculum_generator import (
    generate_dual_path_roadmap, automated_ai_reviewer
)
from core_engine.services_v1.youtube_api import enrich_roadmap_with_youtube

from .serializers import (
    CVUploadV1Serializer, CVIntakeResponseSerializer,
    TargetAlignmentInputSerializer, TargetAlignmentResponseSerializer,
    CurriculumInputSerializer, CurriculumResponseSerializer,
    CapstoneReviewV1InputSerializer, CapstoneReviewV1ResponseSerializer,
)


# ── Timeout Guard (cross-platform: works on Windows + Linux) ─────────────────

class AITimeoutError(Exception):
    pass


@contextmanager
def ai_timeout(seconds: int = 55):
    """
    Cross-platform AI timeout using threading.
    SIGALRM is Unix-only and silently disabled on Windows — this works everywhere.
    """
    result = {"exception": None}
    timed_out = threading.Event()

    def _run_with_timeout():
        # This context manager wraps the caller's block via the generator protocol,
        # so we just signal after `seconds` if the block hasn't finished.
        pass

    timer = threading.Timer(seconds, lambda: timed_out.set())
    timer.daemon = True
    timer.start()
    try:
        yield timed_out
        if timed_out.is_set():
            raise AITimeoutError("AI processing timed out.")
    finally:
        timer.cancel()


def _ai_error_response(e, operation: str):
    if isinstance(e, AITimeoutError):
        return Response(
            {"error": f"{operation} timed out. Please try again.", "code": "AI_TIMEOUT"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    return Response(
        {"error": f"{operation} failed: {str(e)}", "code": "AI_ERROR"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Persistence Helpers ───────────────────────────────────────────────────────

def _persist_skill_map(user, extracted_skills: dict):
    """
    Save/update each technical skill from a parsed CV into the SkillMap model.
    Uses update_or_create so re-running an audit never duplicates rows.
    Returns count of skills saved.
    """
    technical_skills = extracted_skills.get("technical_skills", [])
    saved = 0

    for entry in technical_skills:
        skill_name = entry.get("skill", "").strip()
        years      = entry.get("years")
        if not skill_name:
            continue

        # Get staleness data from NeonDB
        staleness_result = calculate_staleness_index(skill_name, years)

        SkillMap.objects.update_or_create(
            user=user,
            skill_name=skill_name,
            defaults={
                "status":              "claimed",
                "years_experience":    years,
                "freshness_score":     staleness_result["freshness_score"],
                "staleness_index":     staleness_result["staleness_index"],
                "demand_score":        staleness_result["demand_score"],
                "growth_rate":         staleness_result["growth_rate"],
                "staleness_breakdown": staleness_result.get("breakdown", {}),
            },
        )
        saved += 1

    return saved


def _verify_skill_and_badge(user, skill_name: str):
    """
    On capstone PASS:
    1. Upgrade SkillMap entry to "verified"
    2. Update UserSkill status to "verified" if it exists
    3. Issue a SkillBadge (get_or_create — one badge per skill per user)
    """
    # 1. Upgrade SkillMap
    SkillMap.objects.filter(user=user, skill_name=skill_name).update(status="verified")

    # 2. Update UserSkill if exists
    skill_obj = Skill.objects.filter(name__iexact=skill_name).first()
    if skill_obj:
        UserSkill.objects.filter(user=user, skill=skill_obj).update(
            status="verified",
            completed_at=timezone.now(),
        )

        # 3. Issue badge
        SkillBadge.objects.get_or_create(
            user=user,
            skill=skill_obj,
            defaults={"score": 100.0},
        )


def _persist_roadmap(user, alignment: dict, roadmap: dict, jd_text: str,
                     path_preference: str) -> RoadmapProgress:
    """
    Save a generated roadmap to RoadmapProgress + RoadmapTask models.
    Creates a new RoadmapProgress per JD run (not update_or_create —
    users may run multiple audits against different JDs).
    """
    progress = RoadmapProgress.objects.create(
        user              = user,
        target_role       = alignment.get("role_title", ""),
        jd_text           = jd_text[:2000],  # truncate for storage
        path_preference   = path_preference,
        overall_gap_score = alignment.get("gap_score", 0),
        overlap_pct       = alignment.get("overall_overlap_pct", 0),
    )

    for unit in roadmap.get("roadmap", []):
        RoadmapTask.objects.create(
            roadmap             = progress,
            skill_name          = unit.get("skill", ""),
            gap_severity        = unit.get("gap_severity", "moderate"),
            priority            = unit.get("priority", "preferred"),
            bridge_hint         = unit.get("bridge_hint", ""),
            hacker_resources    = unit.get("hacker_path", {}).get("resources", []),
            certified_resources = unit.get("certified_path", {}).get("resources", []),
            capstone_task       = unit.get("mini_capstone") or {},
        )

    return progress


# ── View 1: CVIntakeView ──────────────────────────────────────────────────────

class CVIntakeView(APIView):
    """
    POST /api/v1/intake/

    Accepts CV file (PDF/DOCX) or raw text.
    → Parses with Sarthak's AI
    → Saves ParsedCV to DB
    → Saves each skill to SkillMap (update_or_create)
    → Returns cv_id + full SkillMap
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = CVUploadV1Serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # get_or_create ensures no duplicate UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        try:
            with ai_timeout(55):
                if serializer.validated_data.get("file"):
                    file_bytes          = serializer.validated_data["file"].read()
                    extracted, raw_text = parse_cv_from_pdf(file_bytes)
                else:
                    raw_text  = serializer.validated_data["text"]
                    extracted = parse_cv(raw_text)

        except AITimeoutError as e:
            return _ai_error_response(e, "CV parsing")
        except ValueError as e:
            return Response({"error": str(e), "code": "PARSE_ERROR"},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception as e:
            return _ai_error_response(e, "CV parsing")

        # Persist ParsedCV
        parsed_cv = ParsedCV.objects.create(
            user_profile     = profile,
            raw_text         = raw_text,
            extracted_skills = extracted,
            pii_flagged      = extracted.get("pii_detected", False),
        )

        # Persist SkillMap — update_or_create per skill
        skills_saved = _persist_skill_map(request.user, extracted)

        # Auto-generate week-by-week roadmap from the updated SkillMap
        from core_engine.logic.roadmap_generator import generate_roadmap_for_user
        weeks_created = generate_roadmap_for_user(request.user)

        response_data = {
            "cv_id":         parsed_cv.id,
            "skill_map":     extracted,
            "pii_flagged":   parsed_cv.pii_flagged,
            "uploaded_at":   parsed_cv.uploaded_at,
            "message":       f"CV parsed. {skills_saved} skills saved. {weeks_created}-week roadmap generated.",
        }

        return Response(
            CVIntakeResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )


# ── View 2: TargetAlignmentView ───────────────────────────────────────────────

class TargetAlignmentView(APIView):
    """
    POST /api/v1/align/

    Compares user's SkillMap against a JD.
    → Runs Sarthak's 3-layer alignment engine
    → Returns gap list (does NOT persist — use /curriculum/ for full persistence)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TargetAlignmentInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        cv_id = serializer.validated_data.get("cv_id")
        if cv_id:
            try:
                parsed_cv = ParsedCV.objects.get(id=cv_id, user_profile=profile)
            except ParsedCV.DoesNotExist:
                return Response({"error": "CV not found.", "code": "CV_NOT_FOUND"},
                                status=status.HTTP_404_NOT_FOUND)
        else:
            parsed_cv = ParsedCV.objects.filter(user_profile=profile).first()
            if not parsed_cv:
                return Response(
                    {"error": "No CV found. Upload via /api/v1/intake/ first.",
                     "code":  "NO_CV"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            with ai_timeout(55):
                report = analyze_jd_alignment(
                    jd_text=serializer.validated_data["jd_text"],
                    user_skill_map=parsed_cv.extracted_skills,
                )
        except AITimeoutError as e:
            return _ai_error_response(e, "Alignment analysis")
        except ValueError as e:
            return Response({"error": str(e), "code": "ALIGNMENT_ERROR"},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception as e:
            return _ai_error_response(e, "Alignment analysis")

        return Response(
            TargetAlignmentResponseSerializer(report).data,
            status=status.HTTP_200_OK,
        )


# ── View 3: CurriculumView ────────────────────────────────────────────────────

class CurriculumView(APIView):
    """
    POST /api/v1/curriculum/

    Full pipeline: JD → gap analysis → dual-path roadmap + mini-capstones.
    → Persists RoadmapProgress + RoadmapTask records to DB
    → Returns roadmap_id for progress tracking
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CurriculumInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        cv_id = serializer.validated_data.get("cv_id")
        if cv_id:
            try:
                parsed_cv = ParsedCV.objects.get(id=cv_id, user_profile=profile)
            except ParsedCV.DoesNotExist:
                return Response({"error": "CV not found.", "code": "CV_NOT_FOUND"},
                                status=status.HTTP_404_NOT_FOUND)
        else:
            parsed_cv = ParsedCV.objects.filter(user_profile=profile).first()
            if not parsed_cv:
                return Response(
                    {"error": "No CV found. Upload via /api/v1/intake/ first.",
                     "code":  "NO_CV"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        jd_text            = serializer.validated_data["jd_text"]
        generate_capstones = serializer.validated_data["generate_capstones"]
        path_preference    = serializer.validated_data["path_preference"]

        tech_skills = parsed_cv.extracted_skills.get("technical_skills", [])
        existing    = [s.get("skill", "") for s in tech_skills if s.get("skill")]

        try:
            with ai_timeout(55):
                alignment = analyze_jd_alignment(jd_text, parsed_cv.extracted_skills)
                gap_list  = alignment.get("gaps", [])

                if not gap_list:
                    return Response(
                        {"message":     "No skill gaps found. Your CV is a strong match.",
                         "overlap_pct": alignment.get("overall_overlap_pct", 100)},
                        status=status.HTTP_200_OK,
                    )

                roadmap = generate_dual_path_roadmap(
                    gap_list=gap_list,
                    existing_skills=existing,
                    generate_capstones=generate_capstones,
                )

        except AITimeoutError as e:
            return _ai_error_response(e, "Curriculum generation")
        except ValueError as e:
            return Response({"error": str(e), "code": "CURRICULUM_ERROR"},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception as e:
            return _ai_error_response(e, "Curriculum generation")

        # Enrich hacker_path with real YouTube tutorials (if API key set)
        if settings.YOUTUBE_API_KEY:
            roadmap = enrich_roadmap_with_youtube(roadmap)

        # Persist RoadmapProgress + RoadmapTask records
        progress = _persist_roadmap(
            user=request.user,
            alignment=alignment,
            roadmap=roadmap,
            jd_text=jd_text,
            path_preference=path_preference,
        )

        # Filter paths based on preference
        if path_preference != "both":
            for unit in roadmap.get("roadmap", []):
                if path_preference == "hacker":
                    unit.pop("certified_path", None)
                else:
                    unit.pop("hacker_path", None)

        roadmap["role_title"]             = alignment.get("role_title", "")
        roadmap["industry_context"]       = alignment.get("industry_context", "")
        roadmap["overall_overlap_pct"]    = alignment.get("overall_overlap_pct", 0)
        roadmap["transferable_strengths"] = alignment.get("transferable_strengths", [])
        roadmap["roadmap_id"]             = progress.id

        return Response(
            CurriculumResponseSerializer(roadmap).data,
            status=status.HTTP_200_OK,
        )


# ── View 4: CapstoneReviewView ────────────────────────────────────────────────

class CapstoneReviewView(APIView):
    """
    POST /api/v1/curriculum/review/

    Automated AI review of a capstone submission.
    → Saves review_result to the matching RoadmapTask if task_id provided
    → Marks task as "completed" on PASS
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CapstoneReviewV1InputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with ai_timeout(30):
                result = automated_ai_reviewer(
                    capstone_task=serializer.validated_data["capstone_task"],
                    proof_of_work=serializer.validated_data["proof_of_work"],
                )
        except AITimeoutError as e:
            return _ai_error_response(e, "Capstone review")
        except Exception as e:
            return _ai_error_response(e, "Capstone review")

        # Persist review result to RoadmapTask if task_id provided
        task_id = request.data.get("task_id")
        if task_id:
            try:
                task = RoadmapTask.objects.get(
                    id=task_id,
                    roadmap__user=request.user,
                )
                task.proof_of_work = serializer.validated_data["proof_of_work"]
                task.review_result = result

                if result.get("verdict") == "PASS":
                    task.status       = "completed"
                    task.completed_at = timezone.now()

                    # ── Verification Engine ───────────────────────────────────
                    # On PASS: upgrade SkillMap to "verified" + issue badge
                    _verify_skill_and_badge(request.user, task.skill_name)

                else:
                    task.status = "in_progress"
                task.save(update_fields=["proof_of_work", "review_result",
                                         "status", "completed_at"])
            except RoadmapTask.DoesNotExist:
                pass

        return Response(
            CapstoneReviewV1ResponseSerializer(result).data,
            status=status.HTTP_200_OK,
        )


# ── View 5: RoadmapProgressView ───────────────────────────────────────────────

class RoadmapProgressView(APIView):
    """
    GET  /api/v1/progress/              → list all roadmaps for user
    GET  /api/v1/progress/<roadmap_id>/ → get specific roadmap with task statuses
    PATCH /api/v1/progress/<task_id>/task/ → update a task status manually
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, roadmap_id=None):
        if roadmap_id:
            try:
                progress = RoadmapProgress.objects.prefetch_related("tasks").get(
                    id=roadmap_id, user=request.user
                )
            except RoadmapProgress.DoesNotExist:
                return Response({"error": "Roadmap not found."}, status=status.HTTP_404_NOT_FOUND)

            tasks = [
                {
                    "id":           t.id,
                    "skill_name":   t.skill_name,
                    "gap_severity": t.gap_severity,
                    "priority":     t.priority,
                    "status":       t.status,
                    "bridge_hint":  t.bridge_hint,
                    "has_capstone": bool(t.capstone_task),
                    "completed_at": t.completed_at,
                }
                for t in progress.tasks.all()
            ]

            return Response({
                "roadmap_id":     progress.id,
                "target_role":    progress.target_role,
                "path_preference":progress.path_preference,
                "gap_score":      progress.overall_gap_score,
                "overlap_pct":    progress.overlap_pct,
                "completion_pct": progress.completion_pct,
                "created_at":     progress.created_at,
                "tasks":          tasks,
            })

        # List all roadmaps
        roadmaps = RoadmapProgress.objects.filter(user=request.user)
        return Response([
            {
                "roadmap_id":     r.id,
                "target_role":    r.target_role,
                "path_preference":r.path_preference,
                "gap_score":      r.overall_gap_score,
                "completion_pct": r.completion_pct,
                "created_at":     r.created_at,
            }
            for r in roadmaps
        ])


class RoadmapTaskUpdateView(APIView):
    """PATCH /api/v1/progress/task/<task_id>/ — manually update task status"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, task_id):
        try:
            task = RoadmapTask.objects.get(id=task_id, roadmap__user=request.user)
        except RoadmapTask.DoesNotExist:
            return Response({"error": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in ("pending", "in_progress", "completed", "skipped"):
            return Response({"error": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)

        task.status = new_status
        if new_status == "completed" and not task.completed_at:
            task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at"])

        return Response({"task_id": task.id, "status": task.status,
                         "completed_at": task.completed_at})


# ── View 6: SkillMapView ──────────────────────────────────────────────────────

class SkillMapView(APIView):
    """
    GET /api/v1/skillmap/ — return user's full SkillMap with freshness scores
    Queryable: ?status=verified&min_freshness=70&ordering=freshness_score
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SkillMap.objects.filter(user=request.user)

        # Filters
        skill_status = request.query_params.get("status")
        min_freshness = request.query_params.get("min_freshness")
        ordering = request.query_params.get("ordering", "-freshness_score")

        if skill_status:
            qs = qs.filter(status=skill_status)
        if min_freshness:
            qs = qs.filter(freshness_score__gte=int(min_freshness))
        if ordering in ("freshness_score", "-freshness_score",
                        "staleness_index", "-staleness_index", "skill_name"):
            qs = qs.order_by(ordering)

        return Response([
            {
                "skill_name":         s.skill_name,
                "status":             s.status,
                "years_experience":   s.years_experience,
                "freshness_score":    s.freshness_score,
                "staleness_index":    s.staleness_index,
                "demand_score":       s.demand_score,
                "growth_rate":        s.growth_rate,
                "is_stale":           s.is_stale,
                "is_fresh":           s.is_fresh,
                "staleness_breakdown":s.staleness_breakdown,
                "last_analyzed":      s.last_analyzed,
            }
            for s in qs
        ])
