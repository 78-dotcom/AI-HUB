# HUB Credits — staged implementation status

## Current code scope

- `GET /api/credits/balance` returns an account-scoped balance from the ledger.
- `GET /api/credits/ledger` returns the authenticated user's recent ledger entries.
- `record_credit_entry` is an internal append-only posting primitive for trusted payment reconciliation code. Current event types are completed purchase, spend, refund, and adjustment only.
- An idempotency key prevents the same provider event from being posted twice for one account.
- The ledger refuses deductions that would create a negative balance.
- Reservation/hold and settlement workflows are intentionally not exposed yet; they require a separate atomic hold model before model calls can consume credits.
- No public route can mint, purchase, transfer, redeem, or cash out credits.
- The current API explicitly reports that purchases, transfers, and cash redemption are disabled.

## Pricing convention

The API exposes a reference of USD 0.01 per credit for internal product planning. This is a display convention only, not a stored-money balance, USD claim, stablecoin, investment, or redemption promise.

## Before enabling sales or spending

1. Select a payment provider and confirm target launch countries.
2. Obtain legal review for the actual closed-loop design, customer terms, refunds, tax, and any regulatory permissions.
3. Implement verified signed webhooks and reconciliation before posting purchase events.
4. Add atomic credit reservation/settlement integrated with each provider call; prevent concurrent overspend using database row locking or an equivalent serializable strategy.
5. Add pricing catalog, provider cost accounting, margins, quotas, fraud controls, refunds, and customer support processes.
6. Test payment failures, duplicate/out-of-order webhooks, chargebacks, refunds, and account closure.
7. Only then enable checkout and user-visible spending.

The current balance endpoint is a ledger foundation, not a payment wallet. Do not enable it for paid customers until the release gates are complete.
