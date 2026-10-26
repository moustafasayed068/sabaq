"""Read queries for athlete data. Always scoped to the caller: never look up by id alone."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from apps.athletes.models import Questionnaire

if TYPE_CHECKING:
    from apps.accounts.models import User


def questionnaire_for(
    questionnaire_id: UUID | str | None, *, session_key: str | None, user: User | None = None
) -> Questionnaire | None:
    """The questionnaire only if it belongs to this session (or this signed-in user)."""
    if not questionnaire_id:
        return None
    qs = Questionnaire.objects.select_related("race").filter(pk=questionnaire_id)
    if user is not None and user.is_authenticated:
        mine = qs.filter(user=user).first()
        if mine:
            return mine
    if not session_key:
        return None
    return qs.filter(session_key=session_key, user__isnull=True).first()
