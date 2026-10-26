# 0004: Paymob payments

## Context

Week 1 is free; one payment per race unlocks the rest of the plan. docs/security.md requires
server-side prices, a verified and idempotent callback whose amount matches the order, and no
unlock from the browser redirect. The owner adds the Paymob keys later, through env only.

## Decision

- Paymob **Intention API** (`POST /v1/intention/`) and the hosted **unified checkout** page. We
  never see card data. One integration id per payment method (card, wallet, Fawry) in
  `PAYMOB_INTEGRATION_IDS`.
- `Order` holds the server price in piastres plus currency. `Payment` is one Paymob transaction,
  unique by Paymob transaction id, so repeated callbacks update one row.
- The "transaction processed" callback is the only thing that unlocks a plan. It is accepted only
  when the HMAC-SHA512 over Paymob's fixed field list matches (`PAYMOB_HMAC_SECRET`), and it
  unlocks only when amount and currency equal the order's. A mismatch becomes `mismatch` for staff.
  A paid callback after a refund or mismatch never unlocks by itself.
- Refunds: staff with `payments.refund_order` refund in full from the admin; the plan goes back
  to week 1. A refund callback from Paymob does the same.
- Redoing the questions for the same race keeps the payment.
- HTTP calls use the standard library (`urllib`, https only, timeout). No SDK dependency.
- Without all keys, checkout says payment opens soon and every callback is rejected.

## Consequences

- Going live is only: set the five `PAYMOB_*` variables, set the callback URL
  (`/payments/paymob/callback/`) in the Paymob dashboard, and run one sandbox payment end to end.
- Prices live in `apps/payments/services.py`. Plans up to 4 weeks are "short"; longer is "long"
  (docs/product.md lists 8-16 weeks for long; 5-7 weeks is priced long until the owner says
  otherwise).
- Gulf: change `PAYMOB_BASE_URL` (uae/ksa) and the currency per country later (M4).
