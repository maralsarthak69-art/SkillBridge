from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    PATH_CHOICES = [
        ("hacker", "Hacker Path"),
        ("certified", "Certified Path"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    preferred_path = models.CharField(max_length=20, choices=PATH_CHOICES, default="hacker")
    target_role = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} — {self.preferred_path}"


class ParsedCV(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="cvs")
    raw_text = models.TextField()
    extracted_skills = models.JSONField(default=dict)
    # Structure: { "technical": [...], "soft": [...], "roles": [...], "pii_detected": true/false }
    pii_flagged = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"CV for {self.user_profile.user.username} @ {self.uploaded_at:%Y-%m-%d %H:%M}"


class SkillSnapshot(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="skill_snapshots")
    skill_name = models.CharField(max_length=255)
    years_experience = models.FloatField(null=True, blank=True)
    freshness_score = models.IntegerField()  # 0–100
    decay_reason = models.TextField(blank=True)
    analyzed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-analyzed_at", "-freshness_score"]

    def __str__(self):
        return f"{self.skill_name} — {self.freshness_score}/100 ({self.user_profile.user.username})"


class GapReport(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="gap_reports")
    jd_text = models.TextField()
    target_role = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"GapReport for {self.user_profile.user.username} — {self.target_role or 'Unknown Role'}"


class SkillGap(models.Model):
    PRIORITY_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    report = models.ForeignKey(GapReport, on_delete=models.CASCADE, related_name="gaps")
    skill_name = models.CharField(max_length=255)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    reason = models.TextField(blank=True)
    user_has_it = models.BooleanField(default=False)

    class Meta:
        ordering = ["priority", "skill_name"]

    def __str__(self):
        status = "✓" if self.user_has_it else "✗"
        return f"{status} {self.skill_name} [{self.priority}] — {self.report}"


class LearningPath(models.Model):
    PATH_CHOICES = [
        ("hacker", "Hacker Path"),
        ("certified", "Certified Path"),
    ]

    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="learning_paths")
    gap_report = models.ForeignKey(GapReport, on_delete=models.SET_NULL, null=True, blank=True, related_name="learning_paths")
    path_type = models.CharField(max_length=20, choices=PATH_CHOICES)
    target_role = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.path_type.title()} Path — {self.target_role or 'General'} ({self.user_profile.user.username})"


class LearningStep(models.Model):
    RESOURCE_TYPES = [
        ("video", "Video"),
        ("article", "Article"),
        ("project", "Project"),
        ("course", "Course"),
        ("cert", "Certification"),
        ("docs", "Documentation"),
    ]

    learning_path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="steps")
    skill_name = models.CharField(max_length=255)
    step_order = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    description = models.TextField()
    resource_url = models.URLField(blank=True)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES, default="article")
    estimated_hours = models.FloatField(default=0)

    class Meta:
        ordering = ["step_order"]

    def __str__(self):
        return f"Step {self.step_order}: {self.title}"


class Capstone(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="capstones")
    gap_report = models.ForeignKey(GapReport, on_delete=models.SET_NULL, null=True, blank=True, related_name="capstones")
    title = models.CharField(max_length=500)
    description = models.TextField()
    tech_stack = models.JSONField(default=list)       # ["Python", "FastAPI", "Redis", ...]
    deliverables = models.JSONField(default=list)     # ["REST API with auth", "Deployed to AWS", ...]
    evaluation_rubric = models.JSONField(default=list) # [{"criterion": "...", "weight": 20}, ...]
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="intermediate")
    target_role = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user_profile.user.username})"


class CapstoneReview(models.Model):
    capstone = models.OneToOneField(Capstone, on_delete=models.CASCADE, related_name="review")
    github_url = models.URLField()
    review_summary = models.TextField()
    score = models.IntegerField()                     # 0–100
    strengths = models.JSONField(default=list)        # ["Good use of Docker", ...]
    improvements = models.JSONField(default=list)     # ["Missing tests", ...]
    reviewed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for '{self.capstone.title}' — {self.score}/100"
