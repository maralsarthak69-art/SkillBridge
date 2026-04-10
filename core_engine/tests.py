"""
Comprehensive test suite for SkillBridge backend.
Covers all phases: Auth, Skills, Resume, Tests, Resources, Portfolio.
"""
import json
import uuid
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock

from .models import (
    UserProfile, SkillCategory, Skill, UserSkill,
    SkillBadge, ResumeParseResult, SkillTest, TestAttempt,
    LearningResource, Portfolio, PortfolioSkillEntry,
)
from .test_service import score_answers, _validate_questions, PASSING_SCORE
from .portfolio_service import generate_portfolio


# ──────────────────────────────────────────────
# Base Setup
# ──────────────────────────────────────────────

class BaseTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

        # Create regular user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@test.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )

        # Create admin user
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@test.com",
            password="adminpass123",
        )

        # Create skill category and skill
        self.category = SkillCategory.objects.create(name="Backend")
        self.skill = Skill.objects.create(
            name="Python",
            category=self.category,
            difficulty="beginner",
            description="Python programming",
        )

    def auth(self, user=None):
        """Force authenticate as given user."""
        self.client.force_authenticate(user=user or self.user)

    def unauth(self):
        self.client.force_authenticate(user=None)


# ──────────────────────────────────────────────
# Phase 1 — Auth & User Profile
# ──────────────────────────────────────────────

class AuthTests(BaseTestCase):

    def test_register_success(self):
        url  = reverse("register")
        data = {
            "username":   "newuser",
            "email":      "new@test.com",
            "password":   "newpass123",
            "first_name": "New",
            "last_name":  "User",
        }
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["username"], "newuser")
        # Profile auto-created via signal
        self.assertTrue(UserProfile.objects.filter(user__username="newuser").exists())

    def test_register_duplicate_username(self):
        url  = reverse("register")
        data = {"username": "testuser", "email": "x@x.com", "password": "pass1234"}
        res  = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_short_password(self):
        url  = reverse("register")
        data = {"username": "shortpass", "email": "x@x.com", "password": "123"}
        res  = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_me_requires_auth(self):
        url = reverse("me")
        res = self.client.get(url)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_me_returns_profile(self):
        self.auth()
        url = reverse("me")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["username"], "testuser")
        self.assertIn("profile", res.data)

    def test_profile_auto_created_on_register(self):
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_me_patch_profile(self):
        self.auth()
        url = reverse("me")
        res = self.client.patch(url, {"profile": {"bio": "Hello world"}}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.bio, "Hello world")


# ──────────────────────────────────────────────
# Phase 1 — Skills & Categories
# ──────────────────────────────────────────────

class SkillTests(BaseTestCase):

    def test_list_categories_public(self):
        url = reverse("categories")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Backend")

    def test_create_category_admin_only(self):
        url  = reverse("categories")
        data = {"name": "Frontend"}
        # Unauthenticated
        res = self.client.post(url, data)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        # Regular user
        self.auth()
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # Admin
        self.auth(self.admin)
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_list_skills_public(self):
        url = reverse("skills-list")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)

    def test_filter_skills_by_difficulty(self):
        url = reverse("skills-list")
        res = self.client.get(url, {"difficulty": "beginner"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        res = self.client.get(url, {"difficulty": "advanced"})
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 0)

    def test_skill_detail_public(self):
        url = reverse("skills-detail", args=[self.skill.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "Python")

    def test_enroll_in_skill(self):
        self.auth()
        url  = reverse("my-skills")
        data = {"skill": self.skill.id}
        res  = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "enrolled")

    def test_enroll_duplicate_skill(self):
        self.auth()
        UserSkill.objects.create(user=self.user, skill=self.skill)
        url  = reverse("my-skills")
        data = {"skill": self.skill.id}
        res  = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_my_skills(self):
        self.auth()
        UserSkill.objects.create(user=self.user, skill=self.skill)
        url = reverse("my-skills")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)


# ──────────────────────────────────────────────
# Phase 1 — Badges
# ──────────────────────────────────────────────

class BadgeTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.badge = SkillBadge.objects.create(
            user=self.user,
            skill=self.skill,
            score=85.0,
        )

    def test_list_my_badges(self):
        self.auth()
        url = reverse("my-badges")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["score"], 85.0)

    def test_verify_badge_valid(self):
        url = reverse("verify-badge", args=[self.badge.verification_hash])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["valid"])
        self.assertEqual(res.data["username"], "testuser")
        self.assertEqual(res.data["skill"], "Python")

    def test_verify_badge_invalid_uuid(self):
        url = reverse("verify-badge", args=[uuid.uuid4()])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(res.data["valid"])


# ──────────────────────────────────────────────
# Phase 3 — Test Service (Unit Tests)
# ──────────────────────────────────────────────

class TestServiceUnitTests(TestCase):

    def _make_questions(self):
        return [
            {"question": "Q1?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "A is correct"},
            {"question": "Q2?", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "B is correct"},
            {"question": "Q3?", "options": ["A", "B", "C", "D"], "correct_index": 2, "explanation": "C is correct"},
            {"question": "Q4?", "options": ["A", "B", "C", "D"], "correct_index": 3, "explanation": "D is correct"},
            {"question": "Q5?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "A is correct"},
        ]

    def test_score_all_correct(self):
        questions = self._make_questions()
        answers   = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 0}
        result    = score_answers(questions, answers)
        self.assertEqual(result["score"], 100.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["correct"], 5)
        self.assertEqual(result["total"], 5)

    def test_score_all_wrong(self):
        questions = self._make_questions()
        answers   = {"0": 1, "1": 0, "2": 0, "3": 0, "4": 1}
        result    = score_answers(questions, answers)
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["correct"], 0)

    def test_score_exactly_passing(self):
        questions = self._make_questions()
        # 4/5 = 80% — passes
        answers = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 1}
        result  = score_answers(questions, answers)
        self.assertEqual(result["score"], 80.0)
        self.assertTrue(result["passed"])

    def test_score_just_below_passing(self):
        questions = self._make_questions()
        # 3/5 = 60% — fails
        answers = {"0": 0, "1": 1, "2": 2, "3": 0, "4": 1}
        result  = score_answers(questions, answers)
        self.assertEqual(result["score"], 60.0)
        self.assertFalse(result["passed"])

    def test_score_empty_answers(self):
        questions = self._make_questions()
        result    = score_answers(questions, {})
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["passed"])

    def test_score_breakdown_length(self):
        questions = self._make_questions()
        answers   = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 0}
        result    = score_answers(questions, answers)
        self.assertEqual(len(result["breakdown"]), 5)

    def test_validate_questions_filters_invalid(self):
        questions = [
            {"question": "Q?", "options": ["A", "B", "C", "D"], "correct_index": 0},
            {"question": "Bad", "options": ["A", "B"]},  # missing correct_index
            {"question": "Bad2", "options": ["A", "B", "C", "D"], "correct_index": 10},  # out of range
        ]
        validated = _validate_questions(questions)
        self.assertEqual(len(validated), 1)

    def test_passing_score_threshold(self):
        self.assertEqual(PASSING_SCORE, 70.0)


# ──────────────────────────────────────────────
# Phase 3 — Test Generation & Submission API
# ──────────────────────────────────────────────

class TestAPITests(BaseTestCase):

    def _make_skill_test(self):
        questions = [
            {"question": f"Q{i}?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "A"}
            for i in range(5)
        ]
        return SkillTest.objects.create(
            skill=self.skill,
            questions=questions,
            generated_by=self.user,
        )

    @patch("core_engine.views.generate_skill_questions")
    def test_generate_test_success(self, mock_gen):
        mock_gen.return_value = [
            {"question": f"Q{i}?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "A"}
            for i in range(5)
        ]
        self.auth()
        url = reverse("test-generate")
        res = self.client.post(url, {"skill_id": self.skill.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("questions_for_client", res.data)
        self.assertEqual(len(res.data["questions_for_client"]), 5)
        # Correct answers must NOT be in response
        for q in res.data["questions_for_client"]:
            self.assertNotIn("correct_index", q)

    def test_generate_test_invalid_skill(self):
        self.auth()
        url = reverse("test-generate")
        res = self.client.post(url, {"skill_id": 9999}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_generate_test_requires_auth(self):
        url = reverse("test-generate")
        res = self.client.post(url, {"skill_id": self.skill.id}, format="json")
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_submit_test_pass(self):
        self.auth()
        skill_test = self._make_skill_test()
        url     = reverse("test-submit", args=[skill_test.id])
        answers = {str(i): 0 for i in range(5)}  # all correct
        res     = self.client.post(url, {"answers": answers}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["score"], 100.0)
        self.assertTrue(res.data["passed"])
        self.assertTrue(res.data["skill_verified"])
        self.assertIsNotNone(res.data["badge_hash"])

    def test_submit_test_fail(self):
        self.auth()
        skill_test = self._make_skill_test()
        url     = reverse("test-submit", args=[skill_test.id])
        answers = {str(i): 1 for i in range(5)}  # all wrong
        res     = self.client.post(url, {"answers": answers}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["score"], 0.0)
        self.assertFalse(res.data["passed"])
        self.assertFalse(res.data["skill_verified"])
        self.assertIsNone(res.data["badge_hash"])

    def test_submit_test_creates_userskill_on_pass(self):
        self.auth()
        skill_test = self._make_skill_test()
        url     = reverse("test-submit", args=[skill_test.id])
        answers = {str(i): 0 for i in range(5)}
        self.client.post(url, {"answers": answers}, format="json")
        user_skill = UserSkill.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(user_skill.status, "verified")
        self.assertEqual(user_skill.score, 100.0)
        self.assertIsNotNone(user_skill.completed_at)

    def test_submit_test_creates_badge_on_pass(self):
        self.auth()
        skill_test = self._make_skill_test()
        url     = reverse("test-submit", args=[skill_test.id])
        answers = {str(i): 0 for i in range(5)}
        self.client.post(url, {"answers": answers}, format="json")
        self.assertTrue(SkillBadge.objects.filter(user=self.user, skill=self.skill).exists())

    def test_submit_test_badge_hash_stable_on_retake(self):
        """Badge UUID must not change on retake even if score improves."""
        self.auth()
        skill_test = self._make_skill_test()
        url = reverse("test-submit", args=[skill_test.id])
        # First attempt — pass
        res1 = self.client.post(url, {"answers": {str(i): 0 for i in range(5)}}, format="json")
        hash1 = res1.data["badge_hash"]
        # Second attempt — pass again
        skill_test2 = self._make_skill_test()
        url2 = reverse("test-submit", args=[skill_test2.id])
        res2 = self.client.post(url2, {"answers": {str(i): 0 for i in range(5)}}, format="json")
        hash2 = res2.data["badge_hash"]
        self.assertEqual(hash1, hash2)

    def test_my_attempts_list(self):
        self.auth()
        skill_test = self._make_skill_test()
        TestAttempt.objects.create(
            user=self.user, skill_test=skill_test,
            answers={}, score=80.0, passed=True,
        )
        url = reverse("my-attempts")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["score"], 80.0)

    def test_submit_nonexistent_test(self):
        self.auth()
        url = reverse("test-submit", args=[9999])
        res = self.client.post(url, {"answers": {"0": 0}}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ──────────────────────────────────────────────
# Phase 4 — Learning Resources
# ──────────────────────────────────────────────

class ResourceTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.resource = LearningResource.objects.create(
            skill=self.skill,
            source="youtube",
            title="Python Tutorial",
            url="https://youtube.com/watch?v=abc123",
            thumbnail="https://img.youtube.com/abc.jpg",
            channel="TechChannel",
        )

    def test_list_resources_for_skill(self):
        self.auth()
        url = reverse("resources")
        res = self.client.get(url, {"skill_id": self.skill.id})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Python Tutorial")

    def test_list_resources_missing_skill_id(self):
        self.auth()
        url = reverse("resources")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_resources_invalid_skill(self):
        self.auth()
        url = reverse("resources")
        res = self.client.get(url, {"skill_id": 9999})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_recommended_resources(self):
        self.auth()
        UserSkill.objects.create(user=self.user, skill=self.skill, status="enrolled")
        url = reverse("resources-recommended")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)

    def test_recommended_resources_empty_when_no_skills(self):
        self.auth()
        url = reverse("resources-recommended")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 0)

    @patch("core_engine.views.fetch_and_store_resources")
    def test_refresh_resources(self, mock_fetch):
        mock_fetch.return_value = 3
        self.auth()
        url = reverse("resources-refresh")
        res = self.client.post(url, {"skill_id": self.skill.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["skill"], "Python")
        mock_fetch.assert_called_once_with(self.skill)


# ──────────────────────────────────────────────
# Phase 5 — Portfolio
# ──────────────────────────────────────────────

class PortfolioTests(BaseTestCase):

    def setUp(self):
        super().setUp()
        # Give user a verified skill and badge
        self.user_skill = UserSkill.objects.create(
            user=self.user, skill=self.skill,
            status="verified", score=90.0,
        )
        self.badge = SkillBadge.objects.create(
            user=self.user, skill=self.skill, score=90.0,
        )

    def test_generate_portfolio(self):
        self.auth()
        url = reverse("portfolio-generate")
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("slug", res.data)
        self.assertEqual(res.data["username"], "testuser")
        self.assertEqual(len(res.data["skill_entries"]), 1)
        self.assertEqual(res.data["skill_entries"][0]["skill_name"], "Python")
        self.assertEqual(res.data["skill_entries"][0]["score"], 90.0)

    def test_generate_portfolio_no_verified_skills(self):
        self.auth()
        self.user_skill.status = "enrolled"
        self.user_skill.save()
        url = reverse("portfolio-generate")
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_portfolio_public_view(self):
        # Generate first
        portfolio = generate_portfolio(self.user)
        url = reverse("portfolio-public", args=[portfolio.slug])
        res = self.client.get(url)  # no auth
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["username"], "testuser")

    def test_portfolio_public_view_not_found(self):
        url = reverse("portfolio-public", args=["nonexistent-slug"])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_portfolio_private_not_accessible(self):
        portfolio = generate_portfolio(self.user)
        portfolio.is_public = False
        portfolio.save()
        url = reverse("portfolio-public", args=[portfolio.slug])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_portfolio_view(self):
        generate_portfolio(self.user)
        self.auth()
        url = reverse("portfolio-me")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["username"], "testuser")

    def test_my_portfolio_not_found_before_generate(self):
        self.auth()
        url = reverse("portfolio-me")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_badge_hash_in_portfolio_entry(self):
        portfolio = generate_portfolio(self.user)
        self.auth()
        url = reverse("portfolio-public", args=[portfolio.slug])
        res = self.client.get(url)
        entry = res.data["skill_entries"][0]
        self.assertIsNotNone(entry["badge_hash"])
        self.assertEqual(entry["badge_hash"], str(self.badge.verification_hash))

    def test_portfolio_slug_unique_per_user(self):
        p1 = generate_portfolio(self.user)
        p2 = generate_portfolio(self.user)  # regenerate
        self.assertEqual(p1.slug, p2.slug)  # same user = same slug

    def test_portfolio_generate_requires_auth(self):
        url = reverse("portfolio-generate")
        res = self.client.post(url)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

class HealthCheckTest(APITestCase):
    def test_health_check(self):
        url = reverse("health-check")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "ok")
        self.assertEqual(res.data["app"], "core_engine")
