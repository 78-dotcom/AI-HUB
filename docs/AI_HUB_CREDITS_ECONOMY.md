# AI HUB Credits — product and compliance design

Status: proposed product design. No wallet, payment, redemption, or token functionality is enabled.

## Recommended first version

Use **HUB Credits** as closed-loop service credits consumed only for AI HUB services. The balance is an account-level usage ledger, not a bank account, investment, cryptocurrency, or promise of cash redemption.

A USD reference can make pricing understandable: for example, 100 credits may be the displayed usage equivalent of USD 1.00. This is a pricing convention only. It must not be marketed as a stablecoin, a dollar deposit, an investment, or a guaranteed cash redemption right.

## Initial product rules

- Credits can be purchased in clearly priced packs through a licensed payment provider.
- Credits can be spent only on AI HUB services supplied by the AI HUB operator.
- No peer-to-peer transfers, external merchant acceptance, trading, staking, yield, or blockchain token in v1.
- No cash withdrawal or promise to redeem credits at par in v1.
- Show the price in the customer's local fiat currency at checkout; keep a USD reference price internally for provider-cost accounting.
- Show model/tool prices before execution, reserve the estimated credits, then settle against recorded provider usage and release unused reservation.
- Never promise unlimited AI usage. Set plan quotas, per-request caps, and account-level spend limits.
- Maintain an append-only ledger: purchase, reservation, settlement, release, refund adjustment, expiry (if legally permitted), and admin correction. Never edit historical ledger rows.
- Support idempotency keys, immutable transaction IDs, audit logs, and reconciliation against payment-provider events.
- Do not allow a negative balance; concurrent requests must reserve credits atomically.
- Keep promotional credits separate from purchased credits and disclose expiry/eligibility clearly.

## Illustrative denomination

- 1 HUB Credit = USD 0.01 of displayed AI HUB service usage.
- 100 HUB Credits = USD 1.00 reference value for pricing display.
- Actual checkout prices, taxes, payment fees, provider costs, margins, refunds, and regional pricing are handled separately.

This denomination does **not** mean that a credit is a USD-backed asset or redeemable for one cent.

## Why not launch a stablecoin now?

A transferable token or a promise to redeem against USD can trigger payment-services, e-money, cryptoasset, custody, consumer-protection, AML, tax, and safeguarding obligations depending on the countries and exact product design. UK FCA guidance defines e-money by reference to stored monetary value issued on receipt of funds and accepted by parties other than the issuer; the limited-network/single-issuer analysis is fact-specific. Obtain specialist legal advice before enabling transfers, third-party acceptance, cash redemption, or blockchain settlement.

## Release gates

1. Confirm legal entity, launch jurisdictions, customer type, and terms with payments counsel.
2. Select a payment provider that supports the target countries and handles card/payment compliance.
3. Build and test the double-entry/append-only ledger and payment webhook reconciliation.
4. Implement pricing catalogue, cost capture, reserve/settle/release, refunds, and fraud controls.
5. Run a closed beta with low purchase limits and transparent user disclosures.
6. Only consider transferable tokens or redemption after a separate legal and economic review.

## Non-goals for v1

- No crypto token or blockchain.
- No USD bank-like wallet.
- No P2P transfers or external payments.
- No interest, yield, investment language, or speculative appreciation.
- No claim that the unit is legally equivalent to USD.
