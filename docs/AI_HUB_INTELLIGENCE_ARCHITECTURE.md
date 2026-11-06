# AI HUB Intelligence Architecture

Status: proposed implementation blueprint for the next product stage.

## Product direction

AI HUB should become a user-controlled AI workspace and task execution platform, not merely a directory of model APIs. The product's differentiation should come from orchestration, reliable workflows, context management, integrations, transparent cost controls, and a useful business toolset.

The initial release will use established provider APIs. A proprietary foundation model is a later research and investment decision, not a prerequisite for launching a useful product.

## Core architecture

1. **Experience layer** — responsive web application first; mobile clients later. One conversation surface for chat, files, research, creation, and task workflows.
2. **Identity and workspace layer** — individual accounts, isolated user data, preferences, conversation history, consent and retention controls.
3. **Model gateway** — one server-side adapter contract for provider/model discovery, request normalization, timeout handling, retries, usage capture, and provider error normalization. Provider credentials remain server-side.
4. **Orchestrator** — interprets the requested task, selects an execution strategy, chooses eligible models using declared capabilities, and decides whether a task needs one model, model comparison, or a multi-step workflow.
5. **Tool runtime** — explicit, permission-scoped tools for web research, file analysis, image generation, and future integrations. Tools must have bounded inputs, timeouts, and auditable outcomes.
6. **Context and memory** — conversation context plus user-controlled saved preferences and project knowledge. Do not silently turn private chats into training data.
7. **Usage and commercial controls** — provider/model token usage, estimated provider cost from a maintained price catalogue, per-plan quotas, hard spend limits, and transparent user-facing usage.
8. **Operations and trust** — structured logs without secrets, abuse protection, privacy controls, data export/deletion, monitoring, and incident procedures.

## Orchestration flow

1. Authenticate the user and resolve workspace permissions.
2. Validate request size, supported inputs, and plan limits.
3. Classify the task into a small, testable set of task types (general chat, coding, research, document analysis, creative generation, business workflow).
4. Build a candidate model set from configured provider metadata and verified capabilities.
5. Select a model or strategy using capability fit, latency, reliability, user preference, and estimated cost.
6. Execute only the tools and external actions the user has authorized.
7. Validate the result where practical (for example, a second-model review for code or a source check for research).
8. Return the answer with relevant sources or an explanation of limitations.
9. Record usage and cost estimates, and persist only data permitted by the user's settings.

## Initial implementation sequence

### Phase 0 — protect the foundation
- Confirm production configuration and PostgreSQL connectivity without exposing secret values.
- Verify CI and current tests.
- Rotate any credentials that may have been exposed in chat or logs.
- Add migrations rather than relying indefinitely on implicit table creation.

### Phase 1 — model gateway and orchestration foundation
- Extract provider request/response handling from the web route into a tested service module.
- Add a typed task request and deterministic model-selection policy.
- Add capability-aware routing with explicit fallback behavior.
- Add tests for missing providers, unsupported capabilities, provider failures, and cost-limit rejection.
- Preserve the existing chat API until the new service is proven equivalent.

### Phase 2 — useful intelligence features
- Multi-model comparison with clear per-model attribution.
- Research workflow with citations and source verification.
- File/document analysis with size/type limits.
- User-approved memory and project context.
- Tool execution with permission checks and audit records.

### Phase 3 — monetization and reliability
- Provider pricing catalogue and cost accounting.
- Plan quotas, usage caps, and user-visible limits.
- Subscription billing only after costs and unit economics are measured.
- Email verification, account recovery, admin tools, and stronger distributed abuse controls.

### Phase 4 — proprietary model strategy
- Evaluate open-weight models against real product tasks and quality benchmarks.
- Fine-tune only where there is a clear data-rights basis and measurable advantage.
- Consider self-hosting only when usage, latency, privacy requirements, and infrastructure economics justify it.
- Never assume that training a foundation model from scratch is necessary for product differentiation.

## Non-negotiable engineering rules

- Never commit API keys, passwords, database URLs, invitation codes, or session secrets.
- Never expose provider credentials to the browser.
- Never run new orchestration code in production before tests pass and a reviewed change is deployed.
- Never execute payments, send messages, or modify external customer data without explicit user authorization.
- Enforce account-level data ownership on every read and write.
- Track provider costs before selling unlimited plans.
- Keep model capability metadata honest; a label such as "vision" does not itself implement image support.
- Design for provider portability and graceful degradation.

## First commercial wedge

Start with one narrow, paid workflow for small businesses (for example, turning incoming customer enquiries into structured leads and draft replies), then reuse the same orchestration and tool framework across AI HUB. Validate willingness to pay with pilot customers before expanding the feature surface.
