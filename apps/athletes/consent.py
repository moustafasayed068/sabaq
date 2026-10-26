"""Consent texts. Changing a text means a new version; old consents keep theirs.

DRAFT: the owner's lawyer must review this text before launch (docs/security.md).
"""

import hashlib

HEALTH_CONSENT_VERSION = "health-2026-10-draft-1"
HEALTH_CONSENT_TEXT = (
    "عشان نعملك خطة آمنة، هنسألك أسئلة عن صحتك، وإصاباتك، ولو عندك وجع دلوقتي. "
    "الإجابات دي بيانات صحية حساسة: بنحفظها متشفّرة، وبنستخدمها بس عشان قواعد الأمان في خطتك. "
    "مش بنشاركها مع حد، ومحدش من فريقنا بيشوفها غير لو لازم، وكل مرة بتتسجّل. "
    "بنمسحها بعد سنة من آخر خطة ليك، وتقدر تمسحها قبل كده من الإعدادات. "
    "سبق مش بديل عن الدكتور، والخطة مش نصيحة طبية."
)


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
