# AI HUB — Differentiating Product Features

Status: product proposal and implementation roadmap. This document defines product direction; it does not claim that every capability is already implemented.

## Product thesis

AI HUB should be a user-controlled workspace where multiple AI systems cooperate to produce verifiable work. The differentiator is the workflow around models: orchestration, project continuity, evidence, execution, and measurable outcomes—not a claim that the platform owns a new foundation model.

## Seven product pillars

### 1. AI Council — adversarial multi-model review
A user can ask for a high-stakes or complex task to be reviewed by a small council:
- Lead model frames the task and acceptance criteria.
- Specialist model independently proposes a solution.
- Critic model searches for omissions, contradictions, and failure modes.
- Lead model reconciles the findings and labels unresolved disagreement.

Requirements:
- Show model/provider attribution and distinguish independent analysis from copied context.
- Never fabricate consensus; preserve material disagreement.
- Start with an explicit user action, not automatic fan-out on every chat.
- Enforce a configurable maximum number of model calls, token budget, timeout, and spend ceiling.
- If cost cannot be estimated or a limit is missing, do not launch multi-model execution.
- Return partial results safely if one provider fails.

### 2. Project Memory — continuity with user control
Store structured project goals, decisions, constraints, artifacts, and next steps separately from raw chat history.
- Each memory item has provenance, timestamp, and project scope.
- Users can inspect, correct, export, and delete project memory.
- Ask before saving sensitive or ambiguous information.
- Never treat private conversations as model-training data.
- Retrieval must respect workspace ownership and access controls.

### 3. Truth Check — evidence and uncertainty
For research-style answers:
- Separate verified facts, reasoned conclusions, assumptions, and unknowns.
- Attach source URLs and retrieval timestamps to claims.
- Prefer primary sources and corroboration for consequential claims.
- Detect conflicting sources and stale evidence.
- Do not present a source's existence as proof that it supports a claim.

### 4. One Task — outcome-oriented workflows
Turn a request into a bounded plan with deliverables such as a report, spreadsheet, draft, or code change.
- Preview the plan and required permissions before external side effects.
- Require confirmation before sending messages, spending money, publishing, or changing customer data.
- Track task state, artifacts, errors, and completion criteria.
- Support cancellation and resumability.

### 5. Personal AI Team — specialist agents
Allow users to assemble reusable roles (researcher, analyst, developer, editor, operations assistant).
- Agents are workflow roles, not claims of independent human-like intelligence.
- Each role has a narrow instruction set, allowed tools, and explicit permissions.
- A coordinator assigns tasks and checks outputs.
- Prevent uncontrolled agent loops with step, time, and cost limits.

### 6. Future Lab — scenario exploration
Extend the existing deterministic assumption stress-test into an evidence-informed decision workspace:
- Current baseline and explicit user assumptions.
- Downside/base/upside scenarios with uncertainty clearly labelled.
- Evidence and domain constraints added before stronger conclusions.
- Later: compare expected outcomes with actual outcomes.
- Do not call scenario arithmetic a forecast or a trained world model.

### 7. AI Evolution — outcome feedback
With user consent, compare recommendations and predicted ranges against recorded outcomes.
- Track calibration and error by task type and domain.
- Use feedback to improve routing, templates, and evaluation—not silently train on private user data.
- Show what changed and why.
- Keep a rollback path for policy and routing changes.

## Recommended implementation sequence

### Stage A — safe foundation
1. Keep the existing intelligence-routing and Future Lab work isolated until all CI checks pass.
2. Extract provider calls behind a single model gateway.
3. Add provider capability metadata, timeouts, normalized errors, and usage capture.
4. Add a pricing catalogue and hard request-level spend limits before multi-model execution.
5. Add workspace ownership tests and secret-redaction tests.

### Stage B — first differentiator
1. Build AI Council as an opt-in workflow.
2. Start with two model calls: independent answer plus critic; add a synthesizer only when useful.
3. Add per-task budget preview and a hard server-side maximum.
4. Show attribution, disagreements, evidence gaps, and partial failures.
5. Add deterministic tests with mocked providers; no live provider calls in CI.

### Stage C — durable project workspace
1. Add project entities and structured project memory.
2. Add user controls for review, correction, export, and deletion.
3. Add retrieval scoped by account and project.
4. Add Truth Check and citations to research workflows.

### Stage D — useful execution and learning
1. Add One Task plans and permission previews.
2. Add Personal AI Team using bounded roles and tool permissions.
3. Expand Future Lab with evidence and outcome tracking.
4. Add opt-in outcome feedback and calibration dashboards.

## Release gates

A feature is not production-ready until:
- Automated tests pass, including authorization and failure-path tests.
- API credentials and private data remain server-side.
- Per-user and per-request resource limits are enforced server-side.
- User-visible limitations and model attribution are accurate.
- Logging excludes secrets and unnecessary private content.
- Database migrations, backup, and rollback are documented.
- Deployment is reviewed and explicitly approved.

## Commercial principle

Do not promise unlimited model usage. Offer transparent plan limits, usage visibility, and paid higher limits only after provider costs and unit economics are measured. Start with one valuable small-business workflow, then reuse the same secure orchestration platform across the wider AI HUB.

## What is not claimed

This roadmap does not claim that AI HUB has invented multi-agent systems, persistent memory, world models, or source verification. The product opportunity is to combine these capabilities into a coherent, transparent, user-controlled experience with measurable quality and predictable costs.
