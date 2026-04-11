"""
v1/serializers.py — API v1 serializers for Rutuja's orchestration layer

Handles:
    - CV file upload + SkillMap output
    - Target JD alignment input/output
    - Curriculum roadmap input/output
"""
from rest_framework import serializers
from core_engine.models import ParsedCV, SkillSnapshot, GapReport


# ── CV Intake ─────────────────────────────────────────────────────────────────

class CVUploadV1Serializer(serializers.Serializer):
    """
    Accepts either a PDF/DOCX file upload OR raw CV text.
    File takes priority if both are provided.
    """
    file = serializers.FileField(
        required=False,
        help_text="PDF or DOCX resume file (max 5MB)"
    )
    text = serializers.CharField(
        required=False,
        allow_blank=False,
        help_text="Raw CV text if no file is available"
    )

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("text"):
            raise serializers.ValidationError(
                "Provide either a resume file (PDF/DOCX) or raw CV text."
            )
        return attrs


class SkillItemSerializer(serializers.Serializer):
    skill = serializers.CharField()
    years = serializers.FloatField(allow_null=True)


class SkillMapSerializer(serializers.Serializer):
    """The structured SkillMap output from Sarthak's CV parser."""
    technical_skills = SkillItemSerializer(many=True)
    soft_skills      = serializers.ListField(child=serializers.CharField())
    roles            = serializers.ListField(child=serializers.DictField())
    pii_detected     = serializers.BooleanField()


class CVIntakeResponseSerializer(serializers.Serializer):
    """Response from POST /api/v1/intake/"""
    cv_id        = serializers.IntegerField()
    skill_map    = SkillMapSerializer()
    pii_flagged  = serializers.BooleanField()
    uploaded_at  = serializers.DateTimeField()
    message      = serializers.CharField()


# ── Target Alignment ──────────────────────────────────────────────────────────

class TargetAlignmentInputSerializer(serializers.Serializer):
    """Input for POST /api/v1/align/"""
    jd_text     = serializers.CharField(
        min_length=50,
        help_text="Raw Job Description text"
    )
    cv_id       = serializers.IntegerField(
        required=False,
        help_text="Specific CV ID to align against (defaults to latest)"
    )


class GapItemV1Serializer(serializers.Serializer):
    gap_type       = serializers.CharField()
    skill          = serializers.CharField()
    universal_name = serializers.CharField()
    priority       = serializers.CharField()
    gap_severity   = serializers.CharField()
    demand_score   = serializers.IntegerField()
    growth_rate    = serializers.FloatField()
    bridge_hint    = serializers.CharField()


class TargetAlignmentResponseSerializer(serializers.Serializer):
    """Response from POST /api/v1/align/"""
    role_title             = serializers.CharField()
    industry_context       = serializers.CharField()
    overall_overlap_pct    = serializers.IntegerField()
    gap_score              = serializers.IntegerField()
    critical_gaps          = serializers.IntegerField()
    total_jd_requirements  = serializers.IntegerField()
    transferable_strengths = serializers.ListField(child=serializers.CharField())
    gaps                   = GapItemV1Serializer(many=True)


# ── Curriculum ────────────────────────────────────────────────────────────────

class CurriculumInputSerializer(serializers.Serializer):
    """Input for POST /api/v1/curriculum/"""
    jd_text            = serializers.CharField(
        min_length=50,
        help_text="Raw Job Description text"
    )
    path_preference    = serializers.ChoiceField(
        choices=["hacker", "certified", "both"],
        default="both",
        help_text="Which learning path to generate"
    )
    generate_capstones = serializers.BooleanField(
        default=True,
        help_text="Generate unique mini-capstone tasks per skill gap"
    )
    cv_id              = serializers.IntegerField(
        required=False,
        help_text="Specific CV ID (defaults to latest)"
    )


class ResourceV1Serializer(serializers.Serializer):
    title           = serializers.CharField()
    url             = serializers.CharField()
    type            = serializers.CharField()
    estimated_hours = serializers.FloatField()
    source_hook     = serializers.CharField()
    api_enriched    = serializers.BooleanField()


class CapstoneV1Serializer(serializers.Serializer):
    task_title           = serializers.CharField()
    problem_statement    = serializers.CharField()
    specific_constraint  = serializers.CharField()
    deliverable          = serializers.CharField()
    proof_of_work_format = serializers.CharField()
    estimated_days       = serializers.IntegerField()
    difficulty           = serializers.CharField()
    rubric               = serializers.ListField(child=serializers.DictField())


class LearningUnitV1Serializer(serializers.Serializer):
    skill          = serializers.CharField()
    gap_severity   = serializers.CharField()
    priority       = serializers.CharField()
    bridge_hint    = serializers.CharField()
    hacker_path    = serializers.DictField()
    certified_path = serializers.DictField()
    mini_capstone  = CapstoneV1Serializer(allow_null=True)


class CurriculumResponseSerializer(serializers.Serializer):
    """Response from POST /api/v1/curriculum/"""
    roadmap_id             = serializers.IntegerField(required=False)
    role_title             = serializers.CharField()
    industry_context       = serializers.CharField()
    overall_overlap_pct    = serializers.IntegerField()
    transferable_strengths = serializers.ListField(child=serializers.CharField())
    roadmap                = LearningUnitV1Serializer(many=True)
    development_notes      = serializers.ListField(child=serializers.DictField())
    summary                = serializers.DictField()


# ── Capstone Review ───────────────────────────────────────────────────────────

class CapstoneReviewV1InputSerializer(serializers.Serializer):
    """Input for POST /api/v1/curriculum/review/"""
    capstone_task = serializers.DictField(
        help_text="The mini_capstone dict from the curriculum response"
    )
    proof_of_work = serializers.CharField(
        min_length=10,
        help_text="GitHub URL or description of what was built"
    )


class CapstoneReviewV1ResponseSerializer(serializers.Serializer):
    verdict          = serializers.CharField()
    total_score      = serializers.IntegerField()
    criterion_scores = serializers.ListField(child=serializers.DictField())
    overall_feedback = serializers.CharField()
    strengths        = serializers.ListField(child=serializers.CharField())
    improvements     = serializers.ListField(child=serializers.CharField())
    next_steps       = serializers.CharField()
