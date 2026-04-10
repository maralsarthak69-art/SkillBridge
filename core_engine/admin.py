from django.contrib import admin
from .models import UserProfile, ParsedCV, SkillSnapshot, GapReport, SkillGap, LearningPath, LearningStep, Capstone, CapstoneReview


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "preferred_path", "target_role", "created_at"]
    list_filter = ["preferred_path"]
    search_fields = ["user__username", "user__email", "target_role"]


@admin.register(ParsedCV)
class ParsedCVAdmin(admin.ModelAdmin):
    list_display = ["user_profile", "pii_flagged", "uploaded_at"]
    list_filter = ["pii_flagged"]
    search_fields = ["user_profile__user__username"]
    readonly_fields = ["raw_text", "extracted_skills", "pii_flagged", "uploaded_at"]


@admin.register(SkillSnapshot)
class SkillSnapshotAdmin(admin.ModelAdmin):
    list_display = ["skill_name", "freshness_score", "years_experience", "user_profile", "analyzed_at"]
    list_filter = ["freshness_score", "analyzed_at"]
    search_fields = ["skill_name", "user_profile__user__username"]
    readonly_fields = ["skill_name", "freshness_score", "years_experience", "decay_reason", "analyzed_at"]


class SkillGapInline(admin.TabularInline):
    model = SkillGap
    extra = 0
    readonly_fields = ["skill_name", "priority", "reason", "user_has_it"]


@admin.register(GapReport)
class GapReportAdmin(admin.ModelAdmin):
    list_display = ["user_profile", "target_role", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user_profile__user__username", "target_role"]
    readonly_fields = ["jd_text", "target_role", "created_at"]
    inlines = [SkillGapInline]


@admin.register(SkillGap)
class SkillGapAdmin(admin.ModelAdmin):
    list_display = ["skill_name", "priority", "user_has_it", "report"]
    list_filter = ["priority", "user_has_it"]
    search_fields = ["skill_name", "report__user_profile__user__username"]
    readonly_fields = ["skill_name", "priority", "reason", "user_has_it", "report"]


class LearningStepInline(admin.TabularInline):
    model = LearningStep
    extra = 0
    readonly_fields = ["step_order", "skill_name", "title", "resource_url", "resource_type", "estimated_hours"]


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    list_display = ["user_profile", "path_type", "target_role", "created_at"]
    list_filter = ["path_type", "created_at"]
    search_fields = ["user_profile__user__username", "target_role"]
    readonly_fields = ["path_type", "target_role", "created_at"]
    inlines = [LearningStepInline]


@admin.register(LearningStep)
class LearningStepAdmin(admin.ModelAdmin):
    list_display = ["step_order", "title", "skill_name", "resource_type", "estimated_hours", "learning_path"]
    list_filter = ["resource_type"]
    search_fields = ["title", "skill_name", "learning_path__user_profile__user__username"]
    readonly_fields = ["step_order", "skill_name", "title", "description", "resource_url", "resource_type", "estimated_hours"]


class CapstoneReviewInline(admin.StackedInline):
    model = CapstoneReview
    extra = 0
    readonly_fields = ["github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]


@admin.register(Capstone)
class CapstoneAdmin(admin.ModelAdmin):
    list_display = ["title", "difficulty", "target_role", "user_profile", "created_at"]
    list_filter = ["difficulty", "created_at"]
    search_fields = ["title", "target_role", "user_profile__user__username"]
    readonly_fields = ["title", "description", "tech_stack", "deliverables", "evaluation_rubric", "difficulty", "target_role", "created_at"]
    inlines = [CapstoneReviewInline]


@admin.register(CapstoneReview)
class CapstoneReviewAdmin(admin.ModelAdmin):
    list_display = ["capstone", "score", "github_url", "reviewed_at"]
    list_filter = ["reviewed_at"]
    search_fields = ["capstone__title", "capstone__user_profile__user__username"]
    readonly_fields = ["capstone", "github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]
