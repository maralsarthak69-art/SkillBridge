from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


# ──────────────────────────────────────────────
# 1. User Profile
# ──────────────────────────────────────────────

class UserProfile(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio        = models.TextField(blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")
    resume_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile({self.user.username})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create a UserProfile whenever a new User is saved."""
    if created:
        UserProfile.objects.create(user=instance)


# ──────────────────────────────────────────────
# 2. Skill Category & Skill
# ──────────────────────────────────────────────

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
        ("beginner",     "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced",     "Advanced"),
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


# ──────────────────────────────────────────────
# 3. User Skill Progress
# ──────────────────────────────────────────────

class UserSkill(models.Model):
    STATUS_CHOICES = [
        ("enrolled",    "Enrolled"),
        ("in_progress", "In Progress"),
        ("verified",    "Verified"),
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


# ──────────────────────────────────────────────
# 4. Skill Badge
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# 5. Resume Parse Result
# ──────────────────────────────────────────────

class ResumeParseResult(models.Model):
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name="resume_parse")
    raw_text         = models.TextField(blank=True, default="")
    extracted_skills = models.JSONField(default=list)   # list of skill name strings
    parsed_at        = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ResumeParseResult({self.user.username})"


# ──────────────────────────────────────────────
# 6. Skill Test
# ──────────────────────────────────────────────

class SkillTest(models.Model):
    skill        = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="tests")
    questions    = models.JSONField(default=list)   # list of question objects
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_tests")

    def __str__(self):
        return f"SkillTest: {self.skill.name} @ {self.generated_at:%Y-%m-%d %H:%M}"


# ──────────────────────────────────────────────
# 7. Test Attempt
# ──────────────────────────────────────────────

class TestAttempt(models.Model):
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name="test_attempts")
    skill_test   = models.ForeignKey(SkillTest, on_delete=models.CASCADE, related_name="attempts")
    answers      = models.JSONField(default=dict)   # {question_index: selected_option}
    score        = models.FloatField(null=True, blank=True)
    passed       = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]

    def __str__(self):
        return f"Attempt: {self.user.username} | {self.skill_test.skill.name} | score={self.score}"


# ──────────────────────────────────────────────
# 8. Learning Resource
# ──────────────────────────────────────────────

class LearningResource(models.Model):
    SOURCE_CHOICES = [
        ("youtube", "YouTube"),
        ("udemy",   "Udemy"),
    ]

    skill       = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="resources")
    source      = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    title       = models.CharField(max_length=300)
    url         = models.URLField()
    thumbnail   = models.URLField(blank=True, default="")
    duration    = models.CharField(max_length=50, blank=True, default="")  # e.g. "PT10M30S" or "10h 30m"
    channel     = models.CharField(max_length=200, blank=True, default="")  # YouTube channel or Udemy instructor
    fetched_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("skill", "url")
        ordering        = ["source", "title"]

    def __str__(self):
        return f"[{self.source}] {self.title[:60]}"


# ──────────────────────────────────────────────
# 9. Portfolio
# ──────────────────────────────────────────────

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
