# AI HUB — Complete Feature Delivery Plan

Status: approved product scope; implementation is staged. This document is a delivery contract, not a claim that every capability is already implemented or live.

## Product outcome

AI HUB is one international workspace for multiple AI models, media creation, evidence-based research, personal and team workflows, integrations, and a creator marketplace. English is the default product language; Russian and additional languages must be supported through localization keys rather than duplicated UI logic. Web is the first-class client; mobile apps follow on the same API.

## Complete feature scope

| Capability | Required product behavior | Release gate |
|---|---|---|
| Realtime voice | Low-latency speech input/output, interruption handling, transcript, explicit microphone permission, mute/stop | Provider integration, browser permission UX, privacy disclosure, latency and failure tests |
| Image generation and editing | Prompt-to-image, edit an uploaded image, variation, history and ownership | Provider capability check, upload validation, moderation, storage limits and cost caps |
| Video generation | Prompt/reference-driven clips, job queue, progress, cancellation, result storage | Async worker, provider limits, duration/size caps, storage lifecycle, cost gate |
| Audio/music | Speech, transcription, sound/music generation where licensed provider supports it | Consent, file validation, rights/safety policy, duration and cost limits |
| Web research / Truth Check | Search sources, fetch and extract evidence, cite claim-to-source links, show timestamps and conflicts | Search provider, source provenance, prompt-injection isolation, freshness and citation tests |
| Documents and files | PDF, office documents, spreadsheets, images; summarize, extract, compare and create files | MIME/size limits, malware scanning strategy, private storage, tenant isolation |
| External integrations | User-authorized Google Drive, Telegram and other selected services | OAuth, minimal scopes, encrypted tokens, disconnect/revoke, audit trail |
| Workflow automation | Bounded multi-step jobs, schedules, retries, approvals, logs, cancellation and resumability | Queue/worker, idempotency, quotas, human approval for side effects |
| Team workspaces | Members, roles, invitations, shared projects, per-resource permissions | Tenant isolation, RBAC tests, invite abuse controls, audit history |
| Subscription and payments | Free/paid plans, entitlements, usage meter, billing portal, invoices and webhooks | Provider selection, legal/tax review, webhook signature/replay protection, refunds and reconciliation |
| Marketplace monetization | Ratings, reviews, reporting, moderation, commissions and creator payouts | Moderation operations, creator terms, fraud controls, payout KYC/tax obligations and disputes |
| AI HUB-owned models | Evaluate open-weight models, fine-tune where justified, optional hosted inference | Benchmark advantage, data rights, deployment cost and rollback plan |

## Architecture work required

1. **Provider gateway:** normalized adapters for text, vision, image, audio and video; explicit capability metadata; timeouts, retries, usage and cost capture; secrets remain server-side.
2. **Async media and automation runtime:** queue-backed workers, durable job states, idempotency keys, bounded retries, cancellation and artifact retention.
3. **Evidence pipeline:** search adapter, URL allowlist/denylist policy, safe fetch/extraction, source timestamps, claim/source association and prompt-injection containment.
4. **File service:** private object storage abstraction, signed short-lived access, MIME sniffing, size limits, ownership checks and deletion.
5. **Identity/workspaces:** account isolation first, then organizations, roles and project membership; every query scoped by tenant.
6. **Commercial controls:** plan entitlements, quotas, provider cost ledger, payment webhook inbox, reconciliation and creator settlement only after finance/legal review.
7. **Observability:** structured redacted logs, health/readiness checks, metrics for latency, failure rate, provider spend, queue depth and storage.

## Delivery order

### Track 0 — protect current foundation
- Keep PR #4 draft until current head CI passes and production database readiness is verified.
- Verify backup and restore procedure before schema changes.
- Rotate any credentials previously exposed in chat.
- Introduce versioned migrations and deployment rollback notes.

### Track 1 — high-value user capabilities
1. File/document analysis and secure file storage.
2. Source-backed web research / Truth Check.
3. Image generation and editing.
4. Realtime voice.
5. Audio transcription and generation.

### Track 2 — asynchronous creation and action
1. Video generation jobs.
2. Workflow automation engine and approvals.
3. External integrations beginning with one provider selected by pilot demand.

### Track 3 — collaboration and monetization
1. Team workspaces and role-based access.
2. Subscription entitlements and payment processing.
3. Marketplace moderation, ratings and reviews.
4. Creator commissions and payouts after compliance review.

### Track 4 — proprietary model strategy
- Benchmark open-weight models on real anonymized/consented tasks.
- Fine-tune only with lawful data rights and measurable quality gains.
- Consider self-hosting only when total cost, reliability and privacy justify it.

## Definition of done for every feature

- API contract and user flow documented.
- Provider capability is verified, not inferred from a UI label.
- Authentication, ownership, authorization and tenant-isolation tests exist.
- Invalid input, provider outage, timeout, retry and partial-failure paths are tested.
- Per-user limits, rate limits and server-side cost ceilings are enforced.
- Secrets and private user content are excluded from logs and browser bundles.
- Data retention, export and deletion behavior is documented.
- CI passes on the exact PR head.
- Production database backup, migration and rollback are verified.
- Feature is marked separately as implemented, tested, deployed and production-verified.

## External prerequisites

Some capabilities require user-owned provider accounts, API credentials, OAuth app registration, payment-provider onboarding, storage/queue services, or legal review. Credentials must be entered only into the appropriate provider dashboard or encrypted environment-variable manager; never paste passwords, API keys, database URLs or payment secrets into chat or source control.

## Current implementation snapshot — 2026-11-06

The following work is present on the draft feature branch; none of it is live in production:

- **Document extraction UI and API:** PDF, DOCX, XLSX, TXT, Markdown, CSV and JSON; 8 MiB upload limit; 24,000-character extraction cap; authentication required; original uploads are processed in memory and are not persisted.
- **Office-file safeguards:** ZIP archive entry and expanded-size limits; spreadsheet row/column limits; formulas are read as cached values and are not executed.
- **Scanned PDF OCR:** Tesseract OCR for up to 5 pages, bounded render size, 5-second per-page timeout; English and Russian language packs are installed in the production image. OCR use is reported in the UI. This is not a substitute for a full OCR/document-storage service.
- **Web Research:** authenticated UI/API, Brave LLM Context integration, provider-extracted page chunks and source metadata, numbered source IDs and clickable links, freshness filter, strict relevance mode, and prompt-injection instructions. This is source-grounded synthesis, **not independent truth verification** or direct full-page crawling by AI HUB.
- **External prerequisite:** Web Research remains inactive until BRAVE_SEARCH_API_KEY is configured as a server-side Render secret. The provider account/plan and API key have not been created or purchased by this implementation.

CI history:
- Commit ee0787d38cacf24e3c916a1b07288c7df4aacb43: Tests #134 and Python checks #156 passed, including production Docker build and image-import smoke test.
- Current Web Research LLM Context upgrade commit dfe8aa87bf3a91ce731c094f816e1ba835c7f280: fresh CI is running; do not mark it CI-verified until both workflows complete successfully.

## Current truthfulness rule

A roadmap entry is not a shipped feature. The project status report must distinguish:
- **Planned** — scope documented.
- **Implemented** — code exists on a branch.
- **CI-verified** — exact commit passed automated checks.
- **Deployed** — production deployment contains that commit.
- **Production-verified** — live behavior was tested successfully.

No automatic merge or production deployment is authorized by this plan.
