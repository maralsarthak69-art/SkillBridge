from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


# ── User Profile (merged: Sarthak's path/role + Rutuja's bio/avatar/resume) ──

class UserProfile(models.Model):
    PATH_CHOICES = [
        ("hacker", "Hacker Path"),
        ("certified", "Certified Path"),
    ]

    user           = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    preferred_path = models.CharField(max_length=20, choices=PATH_CHOICES, default="hacker")
    target_role    = models.CharField(max_length=255, blank=True)
    bio            = models.TextField(blank=True, default="")
    avatar_url     = models.URLField(blank=True, default="")
    resume_url     = models.URLField(blank=True, default="")
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} — {self.preferred_path}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


# ── Sarthak's AI Models ───────────────────────────────────────────────────────

class ParsedCV(models.Model):
    user_profile     = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="cvs")
    raw_text         = models.TextField()
    extracted_skills = models.JSONField(default=dict)
    pii_flagged      = models.BooleanField(default=False)
    uploaded_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"CV for {self.user_profile.user.username} @ {self.uploaded_at:%Y-%m-%d %H:%M}"


class SkillSnapshot(models.Model):
    user_profile     = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="skill_snapshots")
    skill_name       = models.CharField(max_length=255)
    years_experience = models.FloatField(null=True, blank=True)
    freshness_score  = models.IntegerField()          # 0–100 (inverse of staleness)
    staleness_index  = models.IntegerField(default=0) # 0–100 (from NeonDB logic layer)
    demand_score     = models.IntegerField(default=50)
    growth_rate      = models.FloatField(default=0.0)
    decay_reason     = models.TextField(blank=True)
    analyzed_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-analyzed_at", "-freshness_score"]

    def __str__(self):
        return f"{self.skill_name} — staleness:{self.staleness_index}/100 ({self.user_profile.user.username})"


class GapReport(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="gap_reports")
    jd_text      = models.TextField()
    target_role  = models.CharField(max_length=255, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"GapReport for {self.user_profile.user.username} — {self.target_role or 'Unknown Role'}"


class SkillGap(models.Model):
    PRIORITY_CHOICES = [("high", "High"), ("medium", "Medium"), ("low", "Low")]

    report       = models.ForeignKey(GapReport, on_delete=models.CASCADE, related_name="gaps")
    skill_name   = models.CharField(max_length=255)
    priority     = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    reason       = models.TextField(blank=True)
    user_has_it  = models.BooleanField(default=False)

    class Meta:
        ordering = ["priority", "skill_name"]

    def __str__(self):
        status = "✓" if self.user_has_it else "✗"
        return f"{status} {self.skill_name} [{self.priority}] — {self.report}"


class LearningPath(models.Model):
    PATH_CHOICES = [("hacker", "Hacker Path"), ("certified", "Certified Path")]

    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="learning_paths")
    gap_report   = models.ForeignKey(GapReport, on_delete=models.SET_NULL, null=True, blank=True, related_name="learning_paths")
    path_type    = models.CharField(max_length=20, choices=PATH_CHOICES)
    target_role  = models.CharField(max_length=255, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.path_type.title()} Path — {self.target_role or 'General'} ({self.user_profile.user.username})"


class LearningStep(models.Model):
    RESOURCE_TYPES = [
        ("video", "Video"), ("article", "Article"), ("project", "Project"),
        ("course", "Course"), ("cert", "Certification"), ("docs", "Documentation"),
    ]

    learning_path  = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="steps")
    skill_name     = models.CharField(max_length=255)
    step_order     = models.PositiveIntegerField()
    title          = models.CharField(max_length=500)
    description    = models.TextField()
    resource_url   = models.URLField(blank=True)
    resource_type  = models.CharField(max_length=20, choices=RESOURCE_TYPES, default="article")
    estimated_hours = models.FloatField(default=0)

    class Meta:
        ordering = ["step_order"]

    def __str__(self):
        return f"Step {self.step_order}: {self.title}"


class Capstone(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced"),
    ]

    user_profile      = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="capstones")
    gap_report        = models.ForeignKey(GapReport, on_delete=models.SET_NULL, null=True, blank=True, related_name="capstones")
    title             = models.CharField(max_length=500)
    description       = models.TextField()
    tech_stack        = models.JSONField(default=list)
    deliverables      = models.JSONField(default=list)
    evaluation_rubric = models.JSONField(default=list)
    difficulty        = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="intermediate")
    target_role       = models.CharField(max_length=255, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user_profile.user.username})"


class CapstoneReview(models.Model):
    capstone       = models.OneToOneField(Capstone, on_delete=models.CASCADE, related_name="review")
    github_url     = models.URLField()
    review_summary = models.TextField()
    score          = models.IntegerField()
    strengths      = models.JSONField(default=list)
    improvements   = models.JSONField(default=list)
    reviewed_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for '{self.capstone.title}' — {self.score}/100"


# ── Rutuja's Infrastructure Models ───────────────────────────────────────────

class SkillCategory(models.Model):
    name        = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        verbose_name_plural = "Skill Categories"
        ordering            = ["name"]

    def __str__(self):
        return self.name


class Skill(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced"),
    ]

    name        = models.CharField(max_length=150, unique=True)
    category    = models.ForeignKey(SkillCategory, on_delete=models.SET_NULL, null=True, related_name="skills")
    description = models.TextField(blank=True, default="")
    difficulty  = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="beginner")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.difficulty})"


class UserSkill(models.Model):
    STATUS_CHOICES = [
        ("enrolled", "Enrolled"), ("in_progress", "In Progress"), ("verified", "Verified"),
    ]

    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_skills")
    skill        = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="user_skills")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="enrolled")
    score        = models.FloatField(null=True, blank=True)
    started_at   = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "skill")
        ordering        = ["-started_at"]

    def __str__(self):
        return f"{self.user.username} → {self.skill.name} [{self.status}]"


class SkillBadge(models.Model):
    user              = models.ForeignKey(User, on_delete=models.CASCADE, related_name="badges")
    skill             = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="badges")
    score             = models.FloatField()
    verification_hash = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    awarded_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "skill")
        ordering        = ["-awarded_at"]

    def __str__(self):
        return f"Badge: {self.user.username} — {self.skill.name}"


class ResumeParseResult(models.Model):
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name="resume_parse")
    raw_text         = models.TextField(blank=True, default="")
    extracted_skills = models.JSONField(default=list)
    parsed_at        = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ResumeParseResult({self.user.username})"


class SkillTest(models.Model):
    skill        = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="tests")
    questions    = models.JSONField(default=list)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_tests")

    def __str__(self):
        return f"SkillTest: {self.skill.name} @ {self.generated_at:%Y-%m-%d %H:%M}"


class TestAttempt(models.Model):
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name="test_attempts")
    skill_test   = models.ForeignKey(SkillTest, on_delete=models.CASCADE, related_name="attempts")
    answers      = models.JSONField(default=dict)
    score        = models.FloatField(null=True, blank=True)
    passed       = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]

    def __str__(self):
        return f"Attempt: {self.user.username} | {self.skill_test.skill.name} | score={self.score}"


class LearningResource(models.Model):
    SOURCE_CHOICES = [("youtube", "YouTube"), ("udemy", "Udemy")]

    skill      = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="resources")
    source     = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    title      = models.CharField(max_length=300)
    url        = models.URLField()
    thumbnail  = models.URLField(blank=True, default="")
    duration   = models.CharField(max_length=50, blank=True, default="")
    channel    = models.CharField(max_length=200, blank=True, default="")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("skill", "url")
        ordering        = ["source", "title"]

    def __str__(self):
        return f"[{self.source}] {self.title[:60]}"


class Portfolio(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name="portfolio")
    slug         = models.SlugField(max_length=150, unique=True)
    is_public    = models.BooleanField(default=True)
    bio_snapshot = models.TextField(blank=True, default="")
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Portfolio({self.user.username})"


class PortfolioSkillEntry(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="skill_entries")
    skill     = models.ForeignKey(Skill, on_delete=models.CASCADE)
    badge     = models.ForeignKey(SkillBadge, on_delete=models.SET_NULL, null=True, blank=True)
    score     = models.FloatField()
    resources = models.ManyToManyField(LearningResource, blank=True)

    class Meta:
        unique_together = ("portfolio", "skill")

    def __str__(self):
        return f"{self.portfolio.user.username} — {self.skill.name}"
