"""Sabaq plan engine: pure Python, no Django, no database, no network.

A port of reference/engine-js/sabaq-engine.js. The golden tests in engine/tests prove
the output is identical to the JavaScript reference.
"""

from engine.checkin import check_in, resume_after_clearance
from engine.data import DIST_NAME, HEALTH_QUESTIONS, RACES, race_by_id
from engine.generate import generate, level_of
from engine.health import screen
from engine.jsmath import js_round
from engine.paces import fmt_pace, fmt_time, parse_duration, predict_time, vdot_from
from engine.types import CheckInFeedback, CheckInResult, Env, Flags, HealthAnswers, Plan, PlanInput

# Stored with every generated plan. Bump it whenever the output can change.
ENGINE_VERSION = "1.2.0"

__all__ = [
    "DIST_NAME",
    "ENGINE_VERSION",
    "HEALTH_QUESTIONS",
    "RACES",
    "CheckInFeedback",
    "CheckInResult",
    "Env",
    "Flags",
    "HealthAnswers",
    "Plan",
    "PlanInput",
    "check_in",
    "fmt_pace",
    "fmt_time",
    "generate",
    "js_round",
    "level_of",
    "parse_duration",
    "predict_time",
    "race_by_id",
    "resume_after_clearance",
    "screen",
    "vdot_from",
]
