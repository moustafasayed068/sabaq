from django.http import HttpRequest

from apps.core import flags


def site(request: HttpRequest) -> dict[str, bool]:
    """Footer links to the privacy and terms pages appear only once they are approved."""
    return {"legal_pages_live": flags.is_enabled("legal_pages")}
