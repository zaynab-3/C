C Project Sync

Last updated: 2026-09-05
Maintainer: Zainab's ChatGPT
Repository: https://github.com/zaynab-3/C.git
Current branch: feat/ai-provider-abstraction

PURPOSE

This file is the shared technical handoff between:

Zainab + Zainab's ChatGPT

Hoteit + Hoteit's ChatGPT

Authority order:

Actual repository code and migrations

Verified tests and runtime logs

This sync file

Chat memory / verbal summaries

Do not claim something is implemented unless repository code and/or verification evidence supports it.

Use ASCII -> in this file to avoid encoding corruption.

CURRENT CHECKPOINT

The real WhatsApp gateway is connected to Meta WhatsApp Cloud API and has been verified end-to-end with a transactional outbox reliability layer.

Phone
-> Meta WhatsApp Cloud API
-> Cloudflare quick tunnel [DEV ONLY]
-> FastAPI
-> webhook verification
-> signature verification
-> sender authorization
-> Meta payload normalization
-> PostgreSQL
-> Message + OutboxEvent
-> ONE transaction
-> Celery Beat
-> c.dispatch_outbox
-> Redis / Celery
-> c.process_message
-> row lock + processed-message check
-> Meta outbound API
-> processed_at + outbound_external_id
-> WhatsApp reply

The previous reliability problem:

DB commit
-> Celery .delay()

has been replaced by:

Message + OutboxEvent
-> ONE PostgreSQL transaction
-> dispatcher publishes later

If Redis is temporarily unavailable after the database transaction, the pending outbox event remains durable and can be retried.

IMPORTANT: this is at-least-once processing, NOT exactly-once.
Consumer locking and processed_at protect against normal duplicate Celery delivery.
A rare ambiguity still exists if Meta accepts an outbound message and the worker crashes before PostgreSQL records the successful outbound result.
Do not claim exact-once delivery.

VERIFIED IMPLEMENTATION

Meta / WhatsApp

Implemented and verified:

Real Meta webhook GET verification

X-Hub-Signature-256 POST verification

Meta-shaped inbound text parsing

Sender allowlist

PostgreSQL message persistence

Deduplication by UNIQUE(channel, external_id)

Real outbound WhatsApp send

Automatic deterministic worker reply

Current Graph API version in code: v26.0

Current development reply:
C received your message automatically.

Transactional outbox

Implemented:

outbox_events table

OutboxEvent SQLAlchemy model

Message + OutboxEvent atomic transaction

c.dispatch_outbox Celery task

Celery Beat dispatcher every second

retry/backoff after broker publish failure

processed_at field

outbound_external_id field

SELECT FOR UPDATE processing lock

already-processed skip protection

Live verification proved:

c.dispatch_outbox -> published=1 failed=0
c.process_message -> received
Meta outbound POST -> HTTP 200
automatic reply -> sent
processing task -> succeeded

A later real message was verified directly in PostgreSQL:

processed_at = populated
outbound_external_id = populated
outbox status = published
attempts = 1
last_error = empty

Tests

Latest complete test run:

17 passed
2 dependency deprecation warnings

Warnings are from dependencies and are not project failures.

Covered behavior includes:

outbox publish success

outbox retry after broker failure

automatic worker reply

already-processed skip

outbound WhatsApp client

webhook storage

duplicate handling

unauthorized sender ignore

invalid webhook rejection

Meta GET verification

signature rejection

Docker / infrastructure

Verified:

PostgreSQL healthy

Redis healthy

Celery worker running

Celery Beat running

worker registers c.dispatch_outbox

worker registers c.process_message

Beat fires dispatcher every second

empty dispatcher returns published=0 failed=0

Celery worker runs non-root

Docker dependency caching improved

Beat schedule location: /tmp/celerybeat-schedule

Reason: the non-root container user cannot write the default schedule file inside /app.

Windows FastAPI

Async Psycopg cannot use the normal Windows ProactorEventLoop in this setup.
Use:

uv run python -m c_backend.server

The dedicated server launcher uses SelectorEventLoop.

DATABASE

messages

Important fields:

id
channel
external_id
sender_id
content_type
content
received_at
raw_payload
processed_at
outbound_external_id
created_at

Deduplication: UNIQUE(channel, external_id)

outbox_events

Important fields:

id
event_key
event_type
payload
status
attempts
available_at
last_error
published_at
created_at

Current event type: process_message

AI PROVIDER DECISION

C MUST support both Gemini and OpenAI behind one provider abstraction.

DEVELOPMENT / FREE TESTING

Gemini

PRODUCTION LATER

OpenAI

This must NOT become a Gemini-specific architecture.

Required direction:

C Worker / LangGraph
|
v
AI Provider Interface
| |
v v
GeminiProvider OpenAIProvider

The rest of C calls the shared provider interface rather than provider-specific code.
Provider selection must be configuration-driven.

Conceptually during development:
AI_PROVIDER=gemini

Later for production:
AI_PROVIDER=openai

Switching provider must NOT require rewriting:

webhook code

worker architecture

LangGraph orchestration

business rules

policy engine

approval engine

tool adapters

Exact SDKs, models, quotas, pricing, credentials and API details must be checked against CURRENT official documentation when implementation starts. Do not guess them from this file.

FROZEN ARCHITECTURE

WHATSAPP
-> META CLOUD API
-> FASTAPI / CHANNEL GATEWAY
verify
authorize
validate
deduplicate
normalize
persist
-> POSTGRESQL MESSAGE + OUTBOX
-> CELERY / REDIS
-> C WORKER
-> LANGGRAPH
-> AI PROVIDER INTERFACE
-> Gemini [development]
-> OpenAI [production]
-> ACTION PROPOSAL
-> POLICY ENGINE
-> APPROVAL IF REQUIRED
-> TOOL EXECUTOR
-> MTC
-> Calendar
-> Drive
-> Gmail
-> Work
-> AUDIT RESULT
-> OUTBOUND DELIVERY
-> META
-> WHATSAPP

Correct action sequence:

C INTELLIGENCE
-> ACTION PROPOSAL
-> POLICY ENGINE
-> APPROVAL IF REQUIRED
-> ACTION EXECUTOR
-> AUDIT RESULT

AI interprets and proposes.

Deterministic Python owns:

validation

authorization

DB writes

deduplication

policy

approvals

tool execution

audit

retries

NOT IMPLEMENTED YET

AI Provider interface

GeminiProvider

OpenAIProvider

LangGraph

intelligent text replies

audio transcription/processing

image understanding

document understanding

action proposal model

policy engine

approval engine

MTC integration

Calendar integration

Drive integration

Gmail integration

Work execution integration

complete action/audit schema

dedicated outbound jobs

dead-letter/operator tooling

production monitoring

stable production tunnel/domain

production hosting

Cloudflare Quick Tunnel remains DEVELOPMENT ONLY.

EXACT NEXT CHECKPOINT

Create shared AI Provider interface.

Implement GeminiProvider first for free testing.

Preserve OpenAIProvider compatibility from day one.

Make provider choice configuration-driven.

Add provider-switching tests.

Keep model calls inside worker/orchestration, never the webhook.

Add first text-only LangGraph flow.

Only then add audio/image/document processing.

Do not start tool execution or approvals before the provider/orchestration boundary is stable.

HOTEIT HANDOFF FORMAT

Hoteit's ChatGPT should inspect repository code and this file before advising Hoteit.

Use:

# HOTEIT DECISION

# REPO FINDING

# WHAT CHANGED

# WHAT WAS VERIFIED

# CONFLICT / RISK

# REQUEST TO ZAINAB

# NEXT RECOMMENDED ACTION

Zainab's ChatGPT will reconcile Hoteit's handoff against repository state and update this file.

LATEST VERIFIED MILESTONE

b6b2f2b
feat: add reliable transactional outbox processing

Live Meta WhatsApp E2E: VERIFIED
Transactional outbox: VERIFIED
Automated tests: 17 PASSED

NEXT:
AI provider abstraction -> Gemini development implementation -> OpenAI-compatible production path.


AI PROVIDER ABSTRACTION CHECKPOINT

Branch: feat/ai-provider-abstraction

WHAT CHANGED

- Added one AIProvider contract shared by all model vendors.
- Added GeminiProvider for free development/testing.
- Added OpenAIProvider for later production use.
- Provider selection is configuration-driven with AI_PROVIDER.
- Gemini default development model is gemini-3.8-flash.
- OpenAI model remains configuration-only until production model selection.
- Added provider factory and provider-isolation tests.

ARCHITECTURE

C / future LangGraph
-> AIProvider
   -> GeminiProvider [development/free testing]
   -> OpenAIProvider [production later]

IMPORTANT

No OpenAI paid API call is required during development.
The webhook and worker must not depend on provider-specific SDK APIs.
Provider-specific code stays behind the AIProvider boundary.

NEXT

- Add a real GEMINI_API_KEY locally only; never commit it.
- Live-test Gemini through the provider abstraction.
- Then connect text message processing to the AI provider inside the worker/orchestration layer.
- LangGraph comes after the provider boundary is live-verified.
