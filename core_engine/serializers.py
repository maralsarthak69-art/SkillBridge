from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    UserProfile, ParsedCV, SkillSnapshot, GapReport, SkillGap,
    LearningPath, LearningStep, Capstone, CapstoneReview,
    SkillCategory, Skill, UserSkill, SkillBadge, ResumeParseResult,
    SkillTest, TestAttempt, LearningResource, Portfolio, PortfolioSkillEntry,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email    = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model  = UserProfile
        fields = ["id", "username", "email", "preferred_path", "target_role",
                  "bio", "avatar_url", "resume_url", "created_at"]
        read_only_fields = ["id", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model  = User
        fields = ["id", "username", "email", "first_name", "last_name", "profile"]


class RegisterSerializer(serializers.ModelSerializer):
    name     = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, min_length=8)
    
    # Return JWT tokens + username after registration
    access   = serializers.CharField(read_only=True)
    refresh  = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True)

    class Meta:
        model  = User
        fields = ["email", "password", "name", "username", "access", "refresh"]
        extra_kwargs = {
            "email": {"required": True},
        }

    def validate_email(self, value):
        """Check for duplicate email"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return value

    def validate(self, attrs):
        # If 'name' is provided, split it into first_name and last_name
        if "name" in attrs:
            name_parts = attrs.pop("name").strip().split(maxsplit=1)
            attrs["first_name"] = name_parts[0]
            attrs["last_name"] = name_parts[1] if len(name_parts) > 1 else ""
        
        # If username explicitly provided, validate uniqueness
        if "username" in self.initial_data:
            requested_username = self.initial_data["username"]
            if User.objects.filter(username=requested_username).exists():
                raise serializers.ValidationError(
                    {"username": "A user with this username already exists."}
                )
            attrs["username"] = requested_username
        else:
            # Auto-generate username from email
            email = attrs.get("email", "")
            username = email.split("@")[0]
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            attrs["username"] = username
        
        return attrs

    def create(self, validated_data):
        from rest_framework_simplejwt.tokens import RefreshToken
        
        user = User.objects.create_user(**validated_data)
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        # Add tokens to the instance for serialization
        user.access = str(refresh.access_token)
        user.refresh = str(refresh)
        
        return user


# ── Sarthak's AI Serializers ──────────────────────────────────────────────────

class ParsedCVSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ParsedCV
        fields = ["id", "user_profile", "raw_text", "extracted_skills", "pii_flagged", "uploaded_at"]
        read_only_fields = ["id", "extracted_skills", "pii_flagged", "uploaded_at"]


class CVUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    text = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("text"):
            raise serializers.ValidationError("Provide either a PDF file or raw CV text.")
        return attrs


class CVResultSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ParsedCV
        fields = ["id", "extracted_skills", "pii_flagged", "uploaded_at"]


class SkillSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SkillSnapshot
        fields = ["id", "skill_name", "years_experience", "freshness_score",
                  "staleness_index", "demand_score", "growth_rate", "decay_reason", "analyzed_at"]
        read_only_fields = ["id", "skill_name", "years_experience", "freshness_score",
                            "staleness_index", "demand_score", "growth_rate", "decay_reason", "analyzed_at"]


class SkillDecayReportSerializer(serializers.Serializer):
    overall_freshness = serializers.IntegerField()
    overall_staleness = serializers.IntegerField()
    fresh_count       = serializers.IntegerField()
    relevant_count    = serializers.IntegerField()
    stale_count       = serializers.IntegerField()
    total_skills      = serializers.IntegerField()
    skills            = SkillSnapshotSerializer(many=True)


class SkillGapSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SkillGap
        fields = ["id", "skill_name", "priority", "reason", "user_has_it"]
        read_only_fields = ["id", "skill_name", "priority", "reason", "user_has_it"]


class GapReportSerializer(serializers.ModelSerializer):
    gaps                 = SkillGapSerializer(many=True, read_only=True)
    total_gaps           = serializers.SerializerMethodField()
    missing_skills       = serializers.SerializerMethodField()
    high_priority_gaps   = serializers.SerializerMethodField()
    medium_priority_gaps = serializers.SerializerMethodField()
    low_priority_gaps    = serializers.SerializerMethodField()

    class Meta:
        model  = GapReport
        fields = ["id", "target_role", "created_at", "total_gaps", "missing_skills",
                  "high_priority_gaps", "medium_priority_gaps", "low_priority_gaps", "gaps"]
        read_only_fields = ["id", "target_role", "created_at"]

    def get_total_gaps(self, obj):           return obj.gaps.count()
    def get_missing_skills(self, obj):       return obj.gaps.filter(user_has_it=False).count()
    def get_high_priority_gaps(self, obj):   return obj.gaps.filter(priority="high", user_has_it=False).count()
    def get_medium_priority_gaps(self, obj): return obj.gaps.filter(priority="medium", user_has_it=False).count()
    def get_low_priority_gaps(self, obj):    return obj.gaps.filter(priority="low", user_has_it=False).count()


class GapAnalyzeInputSerializer(serializers.Serializer):
    jd_text     = serializers.CharField(min_length=50)
    target_role = serializers.CharField(required=False, allow_blank=True, default="")


class LearningStepSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LearningStep
        fields = ["id", "skill_name", "step_order", "title", "description",
                  "resource_url", "resource_type", "estimated_hours"]
        read_only_fields = ["id", "skill_name", "step_order", "title", "description",
                            "resource_url", "resource_type", "estimated_hours"]


class LearningPathSerializer(serializers.ModelSerializer):
    steps       = LearningStepSerializer(many=True, read_only=True)
    total_steps = serializers.SerializerMethodField()
    total_hours = serializers.SerializerMethodField()

    class Meta:
        model  = LearningPath
        fields = ["id", "path_type", "target_role", "created_at", "total_steps", "total_hours", "steps"]
        read_only_fields = ["id", "path_type", "target_role", "created_at"]

    def get_total_steps(self, obj): return obj.steps.count()
    def get_total_hours(self, obj): return round(sum(s.estimated_hours for s in obj.steps.all()), 1)


class CurriculumGenerateInputSerializer(serializers.Serializer):
    gap_report_id = serializers.IntegerField()
    path_type     = serializers.ChoiceField(choices=["hacker", "certified"])


class CapstoneReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CapstoneReview
        fields = ["id", "github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]
        read_only_fields = ["id", "github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]


class CapstoneSerializer(serializers.ModelSerializer):
    review = CapstoneReviewSerializer(read_only=True)

    class Meta:
        model  = Capstone
        fields = ["id", "title", "description", "tech_stack", "deliverables",
                  "evaluation_rubric", "difficulty", "target_role", "created_at", "review"]
        read_only_fields = ["id", "title", "description", "tech_stack", "deliverables",
                            "evaluation_rubric", "difficulty", "target_role", "created_at"]


class CapstoneGenerateInputSerializer(serializers.Serializer):
    gap_report_id = serializers.IntegerField()


class CapstoneReviewInputSerializer(serializers.Serializer):
    github_url = serializers.URLField()


# ── Rutuja's Infrastructure Serializers ──────────────────────────────────────

class SkillCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = SkillCategory
        fields = ["id", "name", "description"]


class SkillSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model  = Skill
        fields = ["id", "name", "category", "category_name", "description", "difficulty", "created_at"]
        read_only_fields = ["created_at"]


class UserSkillSerializer(serializers.ModelSerializer):
    skill_name       = serializers.CharField(source="skill.name", read_only=True)
    skill_difficulty = serializers.CharField(source="skill.difficulty", read_only=True)
    skill_category   = serializers.CharField(source="skill.category.name", read_only=True)

    class Meta:
        model  = UserSkill
        fields = ["id", "skill", "skill_name", "skill_difficulty", "skill_category",
                  "status", "score", "started_at", "completed_at"]
        read_only_fields = ["started_at", "completed_at"]


class SkillBadgeSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)

    class Meta:
        model  = SkillBadge
        fields = ["id", "skill", "skill_name", "score", "verification_hash", "awarded_at"]
        read_only_fields = ["verification_hash", "awarded_at"]


class ResumeUploadSerializer(serializers.Serializer):
    resume = serializers.FileField()


class ResumeParseResultSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ResumeParseResult
        fields = ["extracted_skills", "parsed_at"]
        read_only_fields = ["extracted_skills", "parsed_at"]


class SkillTestSerializer(serializers.ModelSerializer):
    skill_name           = serializers.CharField(source="skill.name", read_only=True)
    questions_for_client = serializers.SerializerMethodField()

    class Meta:
        model  = SkillTest
        fields = ["id", "skill", "skill_name", "questions_for_client", "generated_at"]

    def get_questions_for_client(self, obj):
        return [
            {"index": i, "question": q.get("question"), "options": q.get("options")}
            for i, q in enumerate(obj.questions)
        ]


class TestSubmitSerializer(serializers.Serializer):
    answers = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=3))


class TestAttemptSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill_test.skill.name", read_only=True)
    test_id    = serializers.IntegerField(source="skill_test.id", read_only=True)

    class Meta:
        model  = TestAttempt
        fields = ["id", "test_id", "skill_name", "score", "passed", "attempted_at"]


class LearningResourceSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)

    class Meta:
        model  = LearningResource
        fields = ["id", "skill", "skill_name", "source", "title", "url",
                  "thumbnail", "channel", "duration", "fetched_at"]
        read_only_fields = ["fetched_at"]


class PortfolioSkillEntrySerializer(serializers.ModelSerializer):
    skill_name       = serializers.CharField(source="skill.name", read_only=True)
    skill_difficulty = serializers.CharField(source="skill.difficulty", read_only=True)
    badge_hash       = serializers.SerializerMethodField()
    resources        = LearningResourceSerializer(many=True, read_only=True)

    class Meta:
        model  = PortfolioSkillEntry
        fields = ["skill", "skill_name", "skill_difficulty", "score", "badge_hash", "resources"]

    def get_badge_hash(self, obj):
        return str(obj.badge.verification_hash) if obj.badge else None


class PortfolioSerializer(serializers.ModelSerializer):
    username      = serializers.CharField(source="user.username", read_only=True)
    full_name     = serializers.SerializerMethodField()
    skill_entries = PortfolioSkillEntrySerializer(many=True, read_only=True)

    class Meta:
        model  = Portfolio
        fields = ["slug", "username", "full_name", "bio_snapshot", "is_public",
                  "skill_entries", "created_at", "updated_at"]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


# ── Alignment Engine Serializers ──────────────────────────────────────────────

class AlignmentGapItemSerializer(serializers.Serializer):
    gap_type       = serializers.CharField()
    skill          = serializers.CharField()
    universal_name = serializers.CharField()
    priority       = serializers.CharField()
    gap_severity   = serializers.CharField()
    demand_score   = serializers.IntegerField()
    growth_rate    = serializers.FloatField()
    bridge_hint    = serializers.CharField()


class AlignmentReportSerializer(serializers.Serializer):
    role_title              = serializers.CharField()
    industry_context        = serializers.CharField()
    gap_score               = serializers.IntegerField()
    overall_overlap_pct     = serializers.IntegerField()
    critical_gaps           = serializers.IntegerField()
    total_jd_requirements   = serializers.IntegerField()
    transferable_strengths  = serializers.ListField(child=serializers.CharField())
    gaps                    = AlignmentGapItemSerializer(many=True)


class AlignmentInputSerializer(serializers.Serializer):
    jd_text = serializers.CharField(min_length=50)


# ── Curriculum Generator Serializers (imported from module) ──────────────────
from .serializers_curriculum import (  # noqa: E402
    ResourceSlotSerializer, PathSerializer, RubricItemSerializer,
    MiniCapstoneSerializer, LearningUnitSerializer, RoadmapSummarySerializer,
    DevelopmentNoteSerializer, DualPathRoadmapSerializer,
    RoadmapInputSerializer, CriterionScoreSerializer,
    ReviewResultSerializer, ReviewInputSerializer,
)


# ── Soft Skills ───────────────────────────────────────────────────────────────

class SoftSkillItemSerializer(serializers.Serializer):
    skill           = serializers.CharField()
    confidence      = serializers.FloatField()
    evidence        = serializers.CharField()
    development_tip = serializers.CharField()


class SoftSkillsAnalysisSerializer(serializers.Serializer):
    soft_skills      = SoftSkillItemSerializer(many=True)
    top_strengths    = serializers.ListField(child=serializers.CharField())
    areas_to_develop = serializers.ListField(child=serializers.CharField())
    overall_profile  = serializers.CharField()


class SoftSkillsInputSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=20)


class GrammarCorrectionInputSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=10)


class GrammarChangeSerializer(serializers.Serializer):
    original  = serializers.CharField()
    corrected = serializers.CharField()
    reason    = serializers.CharField()


class GrammarCorrectionResultSerializer(serializers.Serializer):
    corrected_text    = serializers.CharField()
    changes           = GrammarChangeSerializer(many=True)
    improvement_score = serializers.IntegerField()
    readability_level = serializers.CharField()
    session_id        = serializers.IntegerField(required=False, allow_null=True)
    request_type      = serializers.CharField(required=False, default="grammar")
    neon_error        = serializers.CharField(required=False, allow_null=True)


# ── Gemini Bot ────────────────────────────────────────────────────────────────

class BotChatInputSerializer(serializers.Serializer):
    mode    = serializers.ChoiceField(choices=["english_coach", "interview_coach", "conflict_coach"])
    message = serializers.CharField(min_length=1, max_length=3000)
    reset   = serializers.BooleanField(default=False)


class CorrectionSerializer(serializers.Serializer):
    original  = serializers.CharField()
    corrected = serializers.CharField()
    tip       = serializers.CharField(required=False, default="", allow_null=True)


class StarrItemSerializer(serializers.Serializer):
    present  = serializers.BooleanField()
    feedback = serializers.CharField(allow_blank=True, default="")


class StarrEvaluationSerializer(serializers.Serializer):
    situation  = StarrItemSerializer()
    task       = StarrItemSerializer()
    action     = StarrItemSerializer()
    result     = StarrItemSerializer()
    reflection = StarrItemSerializer()


class CoachFeedbackSerializer(serializers.Serializer):
    tone_assessment  = serializers.CharField(allow_blank=True, default="")
    what_worked      = serializers.CharField(allow_blank=True, default="")
    what_to_improve  = serializers.CharField(allow_blank=True, default="")
    suggested_phrase = serializers.CharField(allow_blank=True, default="")

    def to_representation(self, instance):
        if instance is None:
            return None
        if isinstance(instance, dict) and isinstance(instance.get("tone_assessment"), (int, float)):
            instance = dict(instance)
            instance["tone_assessment"] = str(instance["tone_assessment"])
        return super().to_representation(instance)


class BotChatResponseSerializer(serializers.Serializer):
    mode       = serializers.CharField()
    session_id = serializers.IntegerField()
    turn_count = serializers.IntegerField()

    # english_coach
    reply         = serializers.CharField(required=False, allow_null=True, default="")
    corrections   = CorrectionSerializer(many=True, required=False, default=[])
    encouragement = serializers.CharField(required=False, allow_null=True, default="")
    follow_up     = serializers.CharField(required=False, allow_null=True, default="")

    # interview_coach
    starr_evaluation = StarrEvaluationSerializer(required=False, allow_null=True)
    overall_score    = serializers.FloatField(required=False, allow_null=True, default=0)
    strength         = serializers.CharField(required=False, allow_null=True, default="")
    improvement      = serializers.CharField(required=False, allow_null=True, default="")
    next_question    = serializers.CharField(required=False, allow_null=True, default="")

    # conflict_coach
    in_character_reply  = serializers.CharField(required=False, allow_null=True, default="")
    coach_feedback      = CoachFeedbackSerializer(required=False, allow_null=True)
    scenario_escalation = serializers.CharField(required=False, allow_null=True, default="slight")
    diplomacy_score     = serializers.FloatField(required=False, allow_null=True, default=0)
