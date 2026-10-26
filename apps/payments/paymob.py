"""Paymob client: create a checkout intention, refund, and verify callback HMACs.

Only the standard library is used. Every request goes to `settings.PAYMOB_BASE_URL` over https.
No card data ever passes through us: the athlete pays on Paymob's own checkout page.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from django.conf import settings

log = logging.getLogger(__name__)

# Fields of a transaction callback that Paymob signs, in lexicographic order (Paymob docs,
# "HMAC calculation"). Values are concatenated with no separator; booleans are "true"/"false".
TRANSACTION_HMAC_FIELDS: tuple[str, ...] = (
    "amount_cents",
    "created_at",
    "currency",
    "error_occured",
    "has_parent_transaction",
    "id",
    "integration_id",
    "is_3d_secure",
    "is_auth",
    "is_capture",
    "is_refunded",
    "is_standalone_payment",
    "is_voided",
    "order.id",
    "owner",
    "pending",
    "source_data.pan",
    "source_data.sub_type",
    "source_data.type",
    "success",
)


class PaymobError(Exception):
    """Paymob refused the request or could not be reached."""


@dataclass(frozen=True)
class PaymobConfig:
    base_url: str
    secret_key: str
    public_key: str
    hmac_secret: str
    integration_ids: tuple[int, ...]
    timeout_s: int

    @classmethod
    def from_settings(cls) -> PaymobConfig:
        return cls(
            base_url=settings.PAYMOB_BASE_URL,
            secret_key=settings.PAYMOB_SECRET_KEY,
            public_key=settings.PAYMOB_PUBLIC_KEY,
            hmac_secret=settings.PAYMOB_HMAC_SECRET,
            integration_ids=tuple(settings.PAYMOB_INTEGRATION_IDS),
            timeout_s=settings.PAYMOB_TIMEOUT_S,
        )

    @property
    def is_complete(self) -> bool:
        return bool(
            self.secret_key and self.public_key and self.hmac_secret and self.integration_ids
        )


# ---------------------------------------------------------------- HMAC


def _lookup(obj: Mapping[str, Any], dotted: str) -> Any:  # noqa: ANN401 - JSON value
    value: Any = obj
    for part in dotted.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _as_text(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


def transaction_hmac(obj: Mapping[str, Any], secret: str) -> str:
    """HMAC-SHA512 (hex) of a transaction callback's `obj`."""
    message = "".join(_as_text(_lookup(obj, f)) for f in TRANSACTION_HMAC_FIELDS)
    return hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()


def hmac_matches(obj: Mapping[str, Any], received: str, secret: str) -> bool:
    if not secret or not received:
        return False
    return hmac.compare_digest(transaction_hmac(obj, secret), received.strip().lower())


# ---------------------------------------------------------------- HTTP

# (method, url, headers, body) -> (status, parsed JSON). Tests replace it; nothing else should.
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, *, timeout_s: int
) -> tuple[int, Any]:
    if not url.startswith("https://"):
        raise PaymobError("Paymob URLs must use https")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310 - https enforced above
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310  # nosec B310
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PaymobError(f"Paymob unreachable: {type(exc).__name__}") from exc
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, None


@dataclass(frozen=True)
class Intention:
    id: str
    client_secret: str
    paymob_order_id: int | None


class PaymobClient:
    def __init__(self, config: PaymobConfig, transport: Transport | None = None) -> None:
        self.config = config
        self._transport = transport

    def _send(self, method: str, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        headers = {
            "Authorization": f"Token {self.config.secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{self.config.base_url}{path}"
        body = json.dumps(payload).encode()
        if self._transport is not None:
            return self._transport(method, url, headers, body)
        return _urllib_transport(method, url, headers, body, timeout_s=self.config.timeout_s)

    def create_intention(
        self,
        *,
        amount_cents: int,
        currency: str,
        item_name: str,
        reference: str,
        phone: str,
        notification_url: str,
        redirection_url: str,
    ) -> Intention:
        """Start a checkout. `reference` (our Order id) comes back as the merchant order id."""
        payload = {
            "amount": amount_cents,
            "currency": currency,
            "payment_methods": list(self.config.integration_ids),
            "items": [
                {"name": item_name, "amount": amount_cents, "description": item_name, "quantity": 1}
            ],
            # Paymob requires billing fields. We collect no names or emails (docs/security.md),
            # so only the verified phone is real; "NA" is Paymob's documented "not available".
            "billing_data": {
                "first_name": "NA",
                "last_name": "NA",
                "email": "NA",
                "phone_number": phone,
            },
            "special_reference": reference,
            "notification_url": notification_url,
            "redirection_url": redirection_url,
        }
        status, data = self._send("POST", "/v1/intention/", payload)
        if status not in (200, 201) or not isinstance(data, dict) or not data.get("client_secret"):
            log.warning("paymob.intention_failed", extra={"status": status})
            raise PaymobError(f"intention failed with HTTP {status}")
        order_id = data.get("intention_order_id")
        return Intention(
            id=str(data.get("id", "")),
            client_secret=str(data["client_secret"]),
            paymob_order_id=int(order_id) if order_id is not None else None,
        )

    def checkout_url(self, client_secret: str) -> str:
        query = urllib.parse.urlencode(
            {"publicKey": self.config.public_key, "clientSecret": client_secret}
        )
        return f"{self.config.base_url}/unifiedcheckout/?{query}"

    def refund(self, *, transaction_id: int, amount_cents: int) -> dict[str, Any]:
        status, data = self._send(
            "POST",
            "/api/acceptance/void_refund/refund",
            {"transaction_id": transaction_id, "amount_cents": amount_cents},
        )
        if status not in (200, 201) or not isinstance(data, dict) or data.get("success") is False:
            log.warning("paymob.refund_failed", extra={"status": status})
            raise PaymobError(f"refund failed with HTTP {status}")
        return data


def client() -> PaymobClient:
    return PaymobClient(PaymobConfig.from_settings())
