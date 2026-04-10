from rest_framework import serializers
from .models import UserProfile, ParsedCV, SkillSnapshot, GapReport, SkillGap, LearningPath, LearningStep, Capstone, CapstoneReview


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "username", "email", "preferred_path", "target_role", "created_at"]
        read_only_fields = ["id", "created_at"]


class ParsedCVSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParsedCV
        fields = ["id", "user_profile", "raw_text", "extracted_skills", "pii_flagged", "uploaded_at"]
        read_only_fields = ["id", "extracted_skills", "pii_flagged", "uploaded_at"]


class CVUploadSerializer(serializers.Serializer):
    """Used for the upload endpoint — accepts either a file or raw text."""
    file = serializers.FileField(required=False)
    text = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("text"):
            raise serializers.ValidationError("Provide either a PDF file or raw CV text.")
        return attrs


class CVResultSerializer(serializers.ModelSerializer):
    """Read-only serializer for returning parsed CV results."""
    class Meta:
        model = ParsedCV
        fields = ["id", "extracted_skills", "pii_flagged", "uploaded_at"]


class SkillSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillSnapshot
        fields = ["id", "skill_name", "years_experience", "freshness_score", "decay_reason", "analyzed_at"]
        read_only_fields = fields


class SkillDecayReportSerializer(serializers.Serializer):
    """Aggregated decay report for a user — not a model serializer."""
    overall_health_score = serializers.IntegerField()
    total_skills = serializers.IntegerField()
    fresh_skills = serializers.IntegerField()       # score >= 85
    relevant_skills = serializers.IntegerField()    # score 70–84
    stale_skills = serializers.IntegerField()       # score < 70
    skills = SkillSnapshotSerializer(many=True)


class SkillGapSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillGap
        fields = ["id", "skill_name", "priority", "reason", "user_has_it"]
        read_only_fields = fields


class GapReportSerializer(serializers.ModelSerializer):
    gaps = SkillGapSerializer(many=True, read_only=True)
    total_gaps = serializers.SerializerMethodField()
    missing_skills = serializers.SerializerMethodField()
    high_priority_gaps = serializers.SerializerMethodField()
    medium_priority_gaps = serializers.SerializerMethodField()
    low_priority_gaps = serializers.SerializerMethodField()

    class Meta:
        model = GapReport
        fields = [
            "id", "target_role", "created_at",
            "total_gaps", "missing_skills",
            "high_priority_gaps", "medium_priority_gaps", "low_priority_gaps",
            "gaps",
        ]
        read_only_fields = fields

    def get_total_gaps(self, obj):
        return obj.gaps.count()

    def get_missing_skills(self, obj):
        return obj.gaps.filter(user_has_it=False).count()

    def get_high_priority_gaps(self, obj):
        return obj.gaps.filter(priority="high", user_has_it=False).count()

    def get_medium_priority_gaps(self, obj):
        return obj.gaps.filter(priority="medium", user_has_it=False).count()

    def get_low_priority_gaps(self, obj):
        return obj.gaps.filter(priority="low", user_has_it=False).count()


class GapAnalyzeInputSerializer(serializers.Serializer):
    jd_text = serializers.CharField(min_length=50)
    target_role = serializers.CharField(required=False, allow_blank=True, default="")


class LearningStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningStep
        fields = [
            "id", "skill_name", "step_order", "title",
            "description", "resource_url", "resource_type", "estimated_hours",
        ]
        read_only_fields = fields


class LearningPathSerializer(serializers.ModelSerializer):
    steps = LearningStepSerializer(many=True, read_only=True)
    total_steps = serializers.SerializerMethodField()
    total_hours = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = [
            "id", "path_type", "target_role", "created_at",
            "total_steps", "total_hours", "steps",
        ]
        read_only_fields = fields

    def get_total_steps(self, obj):
        return obj.steps.count()

    def get_total_hours(self, obj):
        return round(sum(s.estimated_hours for s in obj.steps.all()), 1)


class CurriculumGenerateInputSerializer(serializers.Serializer):
    gap_report_id = serializers.IntegerField()
    path_type = serializers.ChoiceField(choices=["hacker", "certified"])


class CapstoneReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = CapstoneReview
        fields = ["id", "github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]
        read_only_fields = fields


class CapstoneSerializer(serializers.ModelSerializer):
    review = CapstoneReviewSerializer(read_only=True)

    class Meta:
        model = Capstone
        fields = [
            "id", "title", "description", "tech_stack", "deliverables",
            "evaluation_rubric", "difficulty", "target_role", "created_at", "review",
        ]
        read_only_fields = fields


class CapstoneGenerateInputSerializer(serializers.Serializer):
    gap_report_id = serializers.IntegerField()


class CapstoneReviewInputSerializer(serializers.Serializer):
    github_url = serializers.URLField()
