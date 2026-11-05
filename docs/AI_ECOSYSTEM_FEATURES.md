# AI HUB Brain, Reality Check and Marketplace

## AI HUB Brain
- Uses the capability-aware deterministic router in `intelligence.py`.
- Executes the selected configured text model through the existing OpenAI-compatible provider gateway.
- Tries declared alternatives sequentially if the selected provider fails.
- Does not create provider accounts, choose unconfigured models, or expose provider credentials.
- API: `POST /api/brain/run`.

## AI Reality Check
- Runs a lead model and a different reviewer model.
- Can compare the proposed answer against reference material explicitly supplied by the user.
- Uses the Council token cap and configured provider prices for a conservative preflight estimate.
- The estimate is not an invoice guarantee.
- It is a cross-model review, not external web verification or proof. A future search/retrieval integration is required for source verification.
- API: `POST /api/reality-check/run`.

## AI HUB Marketplace
- Includes four starter assistants: Business Planner, Writing Studio, Learning Coach, and Code Partner.
- Individual accounts can create, edit, delete, and optionally publish assistant definitions.
- Public assistants are visible in the community catalogue; private assistants remain owner-scoped. Owners can edit and delete their own assistants from the Marketplace UI.
- Execution uses configured text models and does not expose provider keys.
- Records use the `marketplace_assistants` PostgreSQL table.
- APIs: `GET /api/marketplace`, `POST/PUT/DELETE /api/marketplace/assistants`, and `POST /api/marketplace/{assistant_id}/run`.

## Not enabled yet
Marketplace payments, commissions, creator payouts, ratings, review moderation, and paid subscriptions are deliberately not enabled. Before monetization, add abuse reporting/moderation, creator terms, payment webhooks, refund and dispute handling, tax/legal review, and usage/cost settlement. No paid provider or infrastructure plan is required by these foundations.

## Release gate
The new table is included in `/api/health/ready`. Production use still requires the existing database backup/readiness checks. Keep the pull request in draft until those checks are complete; do not merge into the Render auto-deploying `main` branch prematurely.
