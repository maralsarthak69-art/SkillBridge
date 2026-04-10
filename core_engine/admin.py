from django.contrib import admin
from .models import UserProfile, SkillCategory, Skill, UserSkill, SkillBadge, ResumeParseResult, SkillTest, TestAttempt, LearningResource, Portfolio, PortfolioSkillEntry


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ("user", "created_at", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display  = ("name",)
    search_fields = ("name",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ("name", "category", "difficulty", "created_at")
    list_filter   = ("difficulty", "category")
    search_fields = ("name",)


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display  = ("user", "skill", "status", "score", "started_at", "completed_at")
    list_filter   = ("status",)
    search_fields = ("user__username", "skill__name")


@admin.register(SkillBadge)
class SkillBadgeAdmin(admin.ModelAdmin):
    list_display  = ("user", "skill", "score", "verification_hash", "awarded_at")
    search_fields = ("user__username", "skill__name")
    readonly_fields = ("verification_hash",)


@admin.register(ResumeParseResult)
class ResumeParseResultAdmin(admin.ModelAdmin):
    list_display  = ("user", "parsed_at")
    search_fields = ("user__username",)
    readonly_fields = ("raw_text", "extracted_skills", "parsed_at")


@admin.register(SkillTest)
class SkillTestAdmin(admin.ModelAdmin):
    list_display  = ("skill", "generated_by", "generated_at")
    list_filter   = ("skill",)
    search_fields = ("skill__name",)
    readonly_fields = ("questions", "generated_at")


@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    list_display  = ("user", "skill_test", "score", "passed", "attempted_at")
    list_filter   = ("passed",)
    search_fields = ("user__username", "skill_test__skill__name")
    readonly_fields = ("answers", "score", "passed", "attempted_at")


@admin.register(LearningResource)
class LearningResourceAdmin(admin.ModelAdmin):
    list_display  = ("title", "skill", "source", "channel", "fetched_at")
    list_filter   = ("source", "skill")
    search_fields = ("title", "skill__name", "channel")


class PortfolioSkillEntryInline(admin.TabularInline):
    model  = PortfolioSkillEntry
    extra  = 0
    readonly_fields = ("skill", "badge", "score")


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display    = ("user", "slug", "is_public", "updated_at")
    list_filter     = ("is_public",)
    search_fields   = ("user__username", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
    inlines         = [PortfolioSkillEntryInline]
