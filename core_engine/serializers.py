from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, SkillCategory, Skill, UserSkill, SkillBadge, ResumeParseResult, SkillTest, TestAttempt, LearningResource, Portfolio, PortfolioSkillEntry


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UserProfile
        fields = ["bio", "avatar_url", "resume_url", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model  = User
        fields = ["id", "username", "email", "first_name", "last_name", "profile"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model  = User
        fields = ["username", "email", "password", "first_name", "last_name"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


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
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    # Strip correct_index from questions before sending to client
    questions_for_client = serializers.SerializerMethodField()

    class Meta:
        model  = SkillTest
        fields = ["id", "skill", "skill_name", "questions_for_client", "generated_at"]

    def get_questions_for_client(self, obj):
        """Return questions without correct_index so users can't cheat."""
        return [
            {
                "index":    i,
                "question": q.get("question"),
                "options":  q.get("options"),
            }
            for i, q in enumerate(obj.questions)
        ]


class TestSubmitSerializer(serializers.Serializer):
    """Accepts answers as {question_index: selected_option_index}"""
    answers = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=3)
    )


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
        fields = ["id", "skill", "skill_name", "source", "title", "url", "thumbnail", "channel", "duration", "fetched_at"]
        read_only_fields = ["fetched_at"]


class PortfolioSkillEntrySerializer(serializers.ModelSerializer):
    skill_name        = serializers.CharField(source="skill.name", read_only=True)
    skill_difficulty  = serializers.CharField(source="skill.difficulty", read_only=True)
    badge_hash        = serializers.SerializerMethodField()
    resources         = LearningResourceSerializer(many=True, read_only=True)

    class Meta:
        model  = PortfolioSkillEntry
        fields = ["skill", "skill_name", "skill_difficulty", "score", "badge_hash", "resources"]

    def get_badge_hash(self, obj):
        # badge can be None if skill was verified but badge wasn't awarded yet
        return str(obj.badge.verification_hash) if obj.badge else None


class PortfolioSerializer(serializers.ModelSerializer):
    username     = serializers.CharField(source="user.username", read_only=True)
    full_name    = serializers.SerializerMethodField()
    skill_entries = PortfolioSkillEntrySerializer(many=True, read_only=True)

    class Meta:
        model  = Portfolio
        fields = ["slug", "username", "full_name", "bio_snapshot", "is_public", "skill_entries", "created_at", "updated_at"]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
