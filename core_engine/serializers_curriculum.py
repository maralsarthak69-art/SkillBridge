"""
Curriculum Generator serializers — imported into serializers.py
"""
from rest_framework import serializers


class ResourceSlotSerializer(serializers.Serializer):
    title           = serializers.CharField()
    url             = serializers.CharField()
    type            = serializers.CharField()
    estimated_hours = serializers.FloatField()
    source_hook     = serializers.CharField()
    api_enriched    = serializers.BooleanField()


class PathSerializer(serializers.Serializer):
    resources       = ResourceSlotSerializer(many=True)
    estimated_hours = serializers.IntegerField()
    free            = serializers.BooleanField()
    youtube_query   = serializers.CharField(required=False, default="")
    udemy_query     = serializers.CharField(required=False, default="")


class RubricItemSerializer(serializers.Serializer):
    criterion      = serializers.CharField()
    weight         = serializers.IntegerField()
    pass_condition = serializers.CharField()


class MiniCapstoneSerializer(serializers.Serializer):
    task_title           = serializers.CharField()
    problem_statement    = serializers.CharField()
    specific_constraint  = serializers.CharField()
    deliverable          = serializers.CharField()
    proof_of_work_format = serializers.CharField()
    rubric               = RubricItemSerializer(many=True)
    estimated_days       = serializers.IntegerField()
    difficulty           = serializers.CharField()


class LearningUnitSerializer(serializers.Serializer):
    skill           = serializers.CharField()
    gap_severity    = serializers.CharField()
    priority        = serializers.CharField()
    bridge_hint     = serializers.CharField()
    hacker_path     = PathSerializer()
    certified_path  = PathSerializer()
    mini_capstone   = MiniCapstoneSerializer(allow_null=True)


class RoadmapSummarySerializer(serializers.Serializer):
    total_skills              = serializers.IntegerField()
    critical_skills           = serializers.IntegerField()
    total_hacker_hours        = serializers.IntegerField()
    total_certified_hours     = serializers.IntegerField()
    estimated_weeks_hacker    = serializers.FloatField()
    estimated_weeks_certified = serializers.FloatField()
    capstones_generated       = serializers.IntegerField()


class DevelopmentNoteSerializer(serializers.Serializer):
    type        = serializers.CharField()
    skill       = serializers.CharField()
    priority    = serializers.CharField()
    bridge_hint = serializers.CharField()


class DualPathRoadmapSerializer(serializers.Serializer):
    roadmap           = LearningUnitSerializer(many=True)
    development_notes = DevelopmentNoteSerializer(many=True)
    summary           = RoadmapSummarySerializer()


class RoadmapInputSerializer(serializers.Serializer):
    jd_text            = serializers.CharField(min_length=50)
    generate_capstones = serializers.BooleanField(default=True)


class CriterionScoreSerializer(serializers.Serializer):
    criterion = serializers.CharField()
    score     = serializers.IntegerField()
    weight    = serializers.IntegerField()
    feedback  = serializers.CharField()


class ReviewResultSerializer(serializers.Serializer):
    verdict          = serializers.CharField()
    total_score      = serializers.IntegerField()
    criterion_scores = CriterionScoreSerializer(many=True)
    overall_feedback = serializers.CharField()
    strengths        = serializers.ListField(child=serializers.CharField())
    improvements     = serializers.ListField(child=serializers.CharField())
    next_steps       = serializers.CharField()


class ReviewInputSerializer(serializers.Serializer):
    capstone_task  = serializers.DictField()
    proof_of_work  = serializers.CharField(min_length=10)
