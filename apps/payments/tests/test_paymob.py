import hashlib
import hmac
import json

import pytest

from apps.payments import paymob

# The example transaction from Paymob's HMAC docs (as used by paymob-rails' spec); fake secret.
DOCS_SECRET = "test-only-hmac-secret"
DOCS_OBJ = {
    "id": 2556706,
    "amount_cents": 100,
    "pending": False,
    "success": True,
    "is_auth": False,
    "is_capture": False,
    "is_standalone_payment": True,
    "is_voided": False,
    "is_refunded": False,
    "is_3d_secure": True,
    "integration_id": 6741,
    "has_parent_transaction": False,
    "order": {"id": 4778239, "merchant_order_id": "x"},
    "created_at": "2020-03-25T18:39:44.719228",
    "currency": "EGP",
    "source_data": {"pan": "2346", "type": "card", "sub_type": "MasterCard"},
    "error_occured": False,
    "owner": 4705,
    "data": {"message": "Approved"},
}
# The exact string Paymob signs: field values in lexicographic key order, no separators.
DOCS_MESSAGE = (
    "100"
    "2020-03-25T18:39:44.719228"
    "EGP"
    "false"
    "false"
    "2556706"
    "6741"
    "true"
    "false"
    "false"
    "false"
    "true"
    "false"
    "4778239"
    "4705"
    "false"
    "2346"
    "MasterCard"
    "card"
    "true"
)


def test_hmac_fields_are_sorted_like_paymob_signs_them():
    assert list(paymob.TRANSACTION_HMAC_FIELDS) == sorted(paymob.TRANSACTION_HMAC_FIELDS)


def test_hmac_matches_the_documented_concatenation():
    expected = hmac.new(DOCS_SECRET.encode(), DOCS_MESSAGE.encode(), hashlib.sha512).hexdigest()
    assert paymob.transaction_hmac(DOCS_OBJ, DOCS_SECRET) == expected
    assert paymob.hmac_matches(DOCS_OBJ, expected, DOCS_SECRET)
    assert paymob.hmac_matches(DOCS_OBJ, expected.upper(), DOCS_SECRET)


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount_cents", 99), ("success", False), ("currency", "USD"), ("id", 1)],
)
def test_any_signed_field_change_breaks_the_hmac(field, value):
    good = paymob.transaction_hmac(DOCS_OBJ, DOCS_SECRET)
    assert not paymob.hmac_matches({**DOCS_OBJ, field: value}, good, DOCS_SECRET)


def test_order_id_change_breaks_the_hmac():
    good = paymob.transaction_hmac(DOCS_OBJ, DOCS_SECRET)
    assert not paymob.hmac_matches({**DOCS_OBJ, "order": {"id": 1}}, good, DOCS_SECRET)


def test_unsigned_fields_do_not_matter_and_missing_values_are_empty():
    good = paymob.transaction_hmac(DOCS_OBJ, DOCS_SECRET)
    assert paymob.hmac_matches({**DOCS_OBJ, "data": {}}, good, DOCS_SECRET)
    no_card = {**DOCS_OBJ, "source_data": {"pan": None, "type": "wallet", "sub_type": None}}
    assert paymob.transaction_hmac(no_card, "k") == paymob.transaction_hmac(
        {**no_card, "source_data": {"type": "wallet"}}, "k"
    )


@pytest.mark.parametrize(("received", "secret"), [("", DOCS_SECRET), ("abc", ""), ("abc", "k")])
def test_missing_or_wrong_hmac_never_matches(received, secret):
    assert not paymob.hmac_matches(DOCS_OBJ, received, secret)


CONFIG = paymob.PaymobConfig(
    base_url="https://accept.paymob.com",
    secret_key="sk_test",
    public_key="pk_test",
    hmac_secret="h",
    integration_ids=(11, 12),
    timeout_s=5,
)


class FakeTransport:
    def __init__(self, status=201, data=None):
        self.status = status
        self.data = data
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, json.loads(body)))
        return self.status, self.data


def intention(transport):
    return paymob.PaymobClient(CONFIG, transport).create_intention(
        amount_cents=34900,
        currency="EGP",
        item_name="plan",
        reference="ref-1",
        phone="+201001234567",
        notification_url="https://sabaq.example/payments/paymob/callback/",
        redirection_url="https://sabaq.example/pay/done/",
    )


def test_create_intention_sends_server_price_and_reference():
    transport = FakeTransport(data={"id": "pi_1", "client_secret": "cs_1", "intention_order_id": 7})
    result = intention(transport)
    assert result == paymob.Intention("pi_1", "cs_1", 7)
    method, url, headers, body = transport.calls[0]
    assert (method, url) == ("POST", "https://accept.paymob.com/v1/intention/")
    assert headers["Authorization"] == "Token sk_test"
    assert body["amount"] == 34900
    assert body["items"][0]["amount"] == 34900
    assert body["payment_methods"] == [11, 12]
    assert body["special_reference"] == "ref-1"
    assert body["billing_data"]["phone_number"] == "+201001234567"


@pytest.mark.parametrize(
    ("status", "data"), [(401, {"detail": "no"}), (201, {"id": "x"}), (500, None)]
)
def test_create_intention_failures_raise(status, data):
    with pytest.raises(paymob.PaymobError):
        intention(FakeTransport(status, data))


def test_checkout_url_uses_public_key_and_client_secret():
    url = paymob.PaymobClient(CONFIG).checkout_url("cs_1")
    assert url == "https://accept.paymob.com/unifiedcheckout/?publicKey=pk_test&clientSecret=cs_1"


def test_refund_posts_transaction_and_amount():
    transport = FakeTransport(200, {"success": True, "id": 99})
    paymob.PaymobClient(CONFIG, transport).refund(transaction_id=5, amount_cents=34900)
    _, url, _, body = transport.calls[0]
    assert url.endswith("/api/acceptance/void_refund/refund")
    assert body == {"transaction_id": 5, "amount_cents": 34900}


@pytest.mark.parametrize(("status", "data"), [(400, {}), (200, {"success": False})])
def test_refund_failures_raise(status, data):
    with pytest.raises(paymob.PaymobError):
        paymob.PaymobClient(CONFIG, FakeTransport(status, data)).refund(
            transaction_id=5, amount_cents=1
        )


def test_real_transport_refuses_plain_http():
    with pytest.raises(paymob.PaymobError):
        paymob._urllib_transport("POST", "http://accept.paymob.com/x", {}, b"{}", timeout_s=1)


def test_config_is_complete_only_with_every_key(settings):
    settings.PAYMOB_SECRET_KEY = "s"
    settings.PAYMOB_PUBLIC_KEY = "p"
    settings.PAYMOB_HMAC_SECRET = "h"
    settings.PAYMOB_INTEGRATION_IDS = [1]
    assert paymob.PaymobConfig.from_settings().is_complete
    settings.PAYMOB_HMAC_SECRET = ""
    assert not paymob.PaymobConfig.from_settings().is_complete
