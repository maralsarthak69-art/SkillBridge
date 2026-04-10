"""
test_service.py
Handles AI-powered test generation and answer scoring logic.
"""
import json
import re
from django.conf import settings
from groq import Groq


PASSING_SCORE = 70.0  # percentage threshold to pass


# ──────────────────────────────────────────────
# Question Generation
# ──────────────────────────────────────────────

def generate_skill_questions(skill_name: str, difficulty: str, num_questions: int = 5) -> list:
    """
    Calls Groq to generate MCQ questions for a given skill and difficulty.
    Returns a list of question dicts:
    [
        {
            "question": "What does ... mean?",
            "options": ["A", "B", "C", "D"],
            "correct_index": 2,       # 0-based index of correct option
            "explanation": "Because..."
        },
        ...
    ]
    """
    client = Groq(api_key=settings.GROQ_API_KEY)

    prompt = f"""
You are a technical assessment AI. Generate exactly {num_questions} multiple choice questions to test a candidate's knowledge of "{skill_name}" at {difficulty} level.

Return ONLY a valid JSON array. No markdown, no explanation, just the raw JSON array.

Each question object must follow this exact structure:
{{
  "question": "The question text here?",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_index": 0,
  "explanation": "Brief explanation of why this answer is correct."
}}

Rules:
- correct_index is 0-based (0 = first option, 3 = last option)
- All 4 options must be plausible
- Questions must be technical and specific to {skill_name}
- Difficulty level: {difficulty}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )

    raw = response.choices[0].message.content.strip()

    # Try direct parse
    try:
        questions = json.loads(raw)
        if isinstance(questions, list):
            return _validate_questions(questions)
    except json.JSONDecodeError:
        pass

    # Fallback: extract JSON array from response
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        try:
            questions = json.loads(match.group())
            return _validate_questions(questions)
        except json.JSONDecodeError:
            pass

    raise ValueError("AI returned an invalid response. Please try again.")


def _validate_questions(questions: list) -> list:
    """Ensures each question has the required fields."""
    validated = []
    for q in questions:
        if all(k in q for k in ("question", "options", "correct_index")):
            # Ensure correct_index is int and within range
            q["correct_index"] = int(q["correct_index"])
            if 0 <= q["correct_index"] < len(q["options"]):
                validated.append(q)
    return validated


# ──────────────────────────────────────────────
# Scoring Logic
# ──────────────────────────────────────────────

def score_answers(questions: list, answers: dict) -> dict:
    """
    Scores user answers against correct answers.

    questions: list of question dicts (from SkillTest.questions)
    answers:   dict of {str(question_index): selected_option_index}

    Returns:
    {
        "score": 80.0,          # percentage
        "passed": True,
        "correct": 4,
        "total": 5,
        "breakdown": [...]      # per-question result
    }
    """
    total   = len(questions)
    correct = 0
    breakdown = []

    for i, question in enumerate(questions):
        user_answer    = answers.get(str(i))
        correct_index  = question.get("correct_index")
        is_correct     = (user_answer is not None) and (int(user_answer) == correct_index)

        if is_correct:
            correct += 1

        breakdown.append({
            "question_index":  i,
            "question":        question.get("question"),
            "your_answer":     user_answer,
            "correct_index":   correct_index,
            "correct_option":  question["options"][correct_index] if correct_index is not None else None,
            "is_correct":      is_correct,
            "explanation":     question.get("explanation", ""),
        })

    score  = round((correct / total) * 100, 2) if total > 0 else 0.0
    passed = score >= PASSING_SCORE

    return {
        "score":     score,
        "passed":    passed,
        "correct":   correct,
        "total":     total,
        "breakdown": breakdown,
    }
