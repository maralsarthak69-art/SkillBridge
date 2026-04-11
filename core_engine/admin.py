from django.contrib import admin
from .models import (
    UserProfile, ParsedCV, SkillSnapshot, GapReport, SkillGap,
    LearningPath, LearningStep, Capstone, CapstoneReview,
    SkillCategory, Skill, UserSkill, SkillBadge, ResumeParseResult,
    SkillTest, TestAttempt, LearningResource, Portfolio, PortfolioSkillEntry,
    SkillMap, RoadmapProgress, RoadmapTask,
)

# ── Sarthak's AI Models ───────────────────────────────────────────────────────

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ["user", "preferred_path", "target_role", "created_at"]
    list_filter   = ["preferred_path"]
    search_fields = ["user__username", "user__email", "target_role"]


@admin.register(ParsedCV)
class ParsedCVAdmin(admin.ModelAdmin):
    list_display  = ["user_profile", "pii_flagged", "uploaded_at"]
    list_filter   = ["pii_flagged"]
    search_fields = ["user_profile__user__username"]
    readonly_fields = ["raw_text", "extracted_skills", "pii_flagged", "uploaded_at"]


@admin.register(SkillSnapshot)
class SkillSnapshotAdmin(admin.ModelAdmin):
    list_display  = ["skill_name", "freshness_score", "years_experience", "user_profile", "analyzed_at"]
    list_filter   = ["analyzed_at"]
    search_fields = ["skill_name", "user_profile__user__username"]
    readonly_fields = ["skill_name", "freshness_score", "years_experience", "decay_reason", "analyzed_at"]


class SkillGapInline(admin.TabularInline):
    model = SkillGap
    extra = 0
    readonly_fields = ["skill_name", "priority", "reason", "user_has_it"]


@admin.register(GapReport)
class GapReportAdmin(admin.ModelAdmin):
    list_display  = ["user_profile", "target_role", "created_at"]
    list_filter   = ["created_at"]
    search_fields = ["user_profile__user__username", "target_role"]
    readonly_fields = ["jd_text", "target_role", "created_at"]
    inlines = [SkillGapInline]


@admin.register(SkillGap)
class SkillGapAdmin(admin.ModelAdmin):
    list_display  = ["skill_name", "priority", "user_has_it", "report"]
    list_filter   = ["priority", "user_has_it"]
    search_fields = ["skill_name", "report__user_profile__user__username"]
    readonly_fields = ["skill_name", "priority", "reason", "user_has_it", "report"]


class LearningStepInline(admin.TabularInline):
    model = LearningStep
    extra = 0
    readonly_fields = ["step_order", "skill_name", "title", "resource_url", "resource_type", "estimated_hours"]


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    list_display  = ["user_profile", "path_type", "target_role", "created_at"]
    list_filter   = ["path_type"]
    search_fields = ["user_profile__user__username", "target_role"]
    readonly_fields = ["path_type", "target_role", "created_at"]
    inlines = [LearningStepInline]


@admin.register(LearningStep)
class LearningStepAdmin(admin.ModelAdmin):
    list_display  = ["step_order", "title", "skill_name", "resource_type", "estimated_hours", "learning_path"]
    list_filter   = ["resource_type"]
    search_fields = ["title", "skill_name"]
    readonly_fields = ["step_order", "skill_name", "title", "description", "resource_url", "resource_type", "estimated_hours"]


class CapstoneReviewInline(admin.StackedInline):
    model = CapstoneReview
    extra = 0
    readonly_fields = ["github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]


@admin.register(Capstone)
class CapstoneAdmin(admin.ModelAdmin):
    list_display  = ["title", "difficulty", "target_role", "user_profile", "created_at"]
    list_filter   = ["difficulty"]
    search_fields = ["title", "target_role", "user_profile__user__username"]
    readonly_fields = ["title", "description", "tech_stack", "deliverables", "evaluation_rubric", "difficulty", "target_role", "created_at"]
    inlines = [CapstoneReviewInline]


@admin.register(CapstoneReview)
class CapstoneReviewAdmin(admin.ModelAdmin):
    list_display  = ["capstone", "score", "github_url", "reviewed_at"]
    search_fields = ["capstone__title"]
    readonly_fields = ["capstone", "github_url", "score", "review_summary", "strengths", "improvements", "reviewed_at"]


# ── Rutuja's Infrastructure Models ───────────────────────────────────────────

@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display  = ["name"]
    search_fields = ["name"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ["name", "category", "difficulty", "created_at"]
    list_filter   = ["difficulty", "category"]
    search_fields = ["name"]


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display  = ["user", "skill", "status", "score", "started_at"]
    list_filter   = ["status"]
    search_fields = ["user__username", "skill__name"]


@admin.register(SkillBadge)
class SkillBadgeAdmin(admin.ModelAdmin):
    list_display  = ["user", "skill", "score", "verification_hash", "awarded_at"]
    search_fields = ["user__username", "skill__name"]
    readonly_fields = ["verification_hash"]


@admin.register(ResumeParseResult)
class ResumeParseResultAdmin(admin.ModelAdmin):
    list_display  = ["user", "parsed_at"]
    search_fields = ["user__username"]
    readonly_fields = ["raw_text", "extracted_skills", "parsed_at"]


@admin.register(SkillTest)
class SkillTestAdmin(admin.ModelAdmin):
    list_display  = ["skill", "generated_by", "generated_at"]
    search_fields = ["skill__name"]
    readonly_fields = ["questions", "generated_at"]


@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    list_display  = ["user", "skill_test", "score", "passed", "attempted_at"]
    list_filter   = ["passed"]
    search_fields = ["user__username"]
    readonly_fields = ["answers", "score", "passed", "attempted_at"]


@admin.register(LearningResource)
class LearningResourceAdmin(admin.ModelAdmin):
    list_display  = ["title", "skill", "source", "channel", "fetched_at"]
    list_filter   = ["source"]
    search_fields = ["title", "skill__name"]


class PortfolioSkillEntryInline(admin.TabularInline):
    model = PortfolioSkillEntry
    extra = 0
    readonly_fields = ["skill", "badge", "score"]


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display  = ["user", "slug", "is_public", "updated_at"]
    list_filter   = ["is_public"]
    search_fields = ["user__username", "slug"]
    readonly_fields = ["slug", "created_at", "updated_at"]
    inlines = [PortfolioSkillEntryInline]


# ── SkillMap & Roadmap ────────────────────────────────────────────────────────

@admin.register(SkillMap)
class SkillMapAdmin(admin.ModelAdmin):
    list_display  = ["user", "skill_name", "status", "freshness_score", "staleness_index", "demand_score", "last_analyzed"]
    list_filter   = ["status", "last_analyzed"]
    search_fields = ["user__username", "skill_name"]
    readonly_fields = ["staleness_breakdown", "last_analyzed", "created_at"]


class RoadmapTaskInline(admin.TabularInline):
    model  = RoadmapTask
    extra  = 0
    readonly_fields = ["skill_name", "gap_severity", "priority", "status", "completed_at"]


@admin.register(RoadmapProgress)
class RoadmapProgressAdmin(admin.ModelAdmin):
    list_display  = ["user", "target_role", "path_preference", "overall_gap_score", "overlap_pct", "created_at"]
    list_filter   = ["path_preference", "created_at"]
    search_fields = ["user__username", "target_role"]
    readonly_fields = ["created_at", "updated_at"]
    inlines       = [RoadmapTaskInline]


@admin.register(RoadmapTask)
class RoadmapTaskAdmin(admin.ModelAdmin):
    list_display  = ["roadmap", "skill_name", "gap_severity", "status", "completed_at"]
    list_filter   = ["status", "gap_severity"]
    search_fields = ["skill_name", "roadmap__user__username"]
    readonly_fields = ["capstone_task", "review_result", "created_at"]
