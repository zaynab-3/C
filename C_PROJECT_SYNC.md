C Project Sync

Last updated: 2026-09-05
Maintainer: Zainab's ChatGPT
Repository: https://github.com/zaynab-3/C.git
Current branch: feat/reliable-ai-outbound-delivery

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
-> AIProvider / Gemini
-> generated reply + AI metadata persisted
-> send_whatsapp_reply OutboxEvent
-> c.dispatch_outbox
-> c.send_whatsapp_reply
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

AI-generated worker reply through AIProvider

Current Graph API version in code: v26.0

Current development reply:
AI-generated response through the configured provider/model.

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

30 passed
1 dependency deprecation warning

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
GeminiProvider The rest of C calls the shared provider interface rather than provider-specific code.
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

LangGraph

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

Add the first text-only LangGraph orchestration flow.

Required direction:

WhatsApp message
-> worker
-> LangGraph
-> AIProvider
-> generated response
-> durable outbound delivery

Keep LangGraph provider-agnostic.

Do not allow Gemini/OpenAI SDKs to execute C tools directly.

After the text graph is stable:
-> audio / voice notes
-> images
-> documents
-> action proposals
-> policy / approval
-> tool integrations

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

bcc8404
feat: persist AI replies and isolate WhatsApp delivery retries

Live WhatsApp AI E2E: VERIFIED
Reliable AI generation / delivery split: VERIFIED
Automated tests: 30 PASSED

NEXT:
First text-only LangGraph orchestration layer.

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

LIVE GEMINI PROVIDER CHECKPOINT

WHAT WAS VERIFIED

- Real Gemini API call succeeded through get_ai_provider() -> GeminiProvider -> AIProvider response.
- Active development provider: Gemini.
- Active development model: gemini-3.8-flash.
- Live response returned exactly: C intelligence is online.
- No OpenAI API call was made.

ARCHITECTURE DECISION

- Gemini automatic function calling is explicitly disabled in the provider.
- Provider SDKs must not execute C tools directly.
- Future LangGraph + policy/approval layers own tool selection and execution.
- Deterministic Python remains responsible for consequential actions.

NEXT

- Connect inbound WhatsApp text processing to AIProvider in the worker.
- Then add the first text-only LangGraph orchestration layer.

WHATSAPP AI WORKER WIRING CHECKPOINT

WHAT CHANGED

- c.process_message now calls the provider-agnostic AIProvider for inbound WhatsApp text.
- The generated AI text becomes the outbound WhatsApp reply.
- The worker receives AI provider/model credentials through Docker Compose environment variables.
- AIProviderError and WhatsAppSendError are retried with Celery backoff.
- c.process_message uses late acknowledgement and worker-lost rejection for at-least-once processing.
- Provider SDK tool execution remains disabled; this stage is text reply only.

WHAT WAS VERIFIED

- Automated tests prove the worker calls AIProvider and sends its returned text.
- Automated tests prove an AI failure does not send a WhatsApp reply or mark the message processed.
- Automated tests still protect already-processed messages from duplicate processing.

CURRENT STATUS

LIVE END-TO-END VERIFIED on 2026-09-05.

WHAT WAS VERIFIED

- Real inbound WhatsApp message reached Meta -> FastAPI -> PostgreSQL/outbox -> Celery.
- c.process_message called Gemini through the provider-agnostic AIProvider.
- Gemini 3.8 Flash returned HTTP 200.
- Meta Graph API outbound send returned HTTP 200.
- The physical WhatsApp phone received C's generated reply.
- PostgreSQL confirmed processed_at is set.
- PostgreSQL confirmed outbound_external_id is stored.
- End-to-end text intelligence path is now live.

LIVE PATH

WhatsApp
-> Meta Cloud API
-> C FastAPI gateway
-> PostgreSQL / transactional outbox
-> Celery worker
-> AIProvider
-> Gemini
-> Meta Cloud API
-> WhatsApp

RELIABILITY ISSUE RESOLVED

- AI generation and WhatsApp delivery are now separate retry boundaries.
- Generated AI replies are persisted before outbound delivery.
- Meta delivery retries reuse the persisted reply instead of calling the AI provider again.
- A deterministic send_whatsapp_reply outbox event is created for delivery.

NEXT

- Add the first text-only LangGraph orchestration layer.



RELIABLE AI OUTBOUND DELIVERY CHECKPOINT

Branch: feat/reliable-ai-outbound-delivery
Implementation commit: bcc8404
Migration: cba3814f9172

WHAT CHANGED

- messages now persist generated_reply, ai_provider, ai_model and ai_generated_at.
- c.process_message performs AI generation only.
- Generated reply + send_whatsapp_reply OutboxEvent are committed durably.
- c.send_whatsapp_reply performs Meta delivery independently.
- AIProviderError retries generation only.
- WhatsAppSendError retries delivery only.
- Existing generated replies are reused instead of regenerated.

WHAT WAS VERIFIED

- Focused reliability tests passed.
- Full suite: 30 passed, 1 dependency warning.
- Live WhatsApp message completed end-to-end.
- Phone received: Test 2 received. System operational.
- PostgreSQL confirmed generated_reply exists.
- PostgreSQL confirmed ai_provider=gemini.
- Live test model: gemini-3.5-flash-lite.
- PostgreSQL confirmed ai_generated_at is populated.
- PostgreSQL confirmed processed_at is populated.
- PostgreSQL confirmed outbound_external_id is populated.
- send_whatsapp_reply outbox event status=published.
- send_whatsapp_reply attempts=1.
- send_whatsapp_reply last_error is empty.

IMPORTANT

Delivery remains at-least-once, not exactly-once.

A rare ambiguity remains if Meta accepts an outbound message and the worker crashes before PostgreSQL records the successful delivery.

Current external AI / Meta calls are still made while database row locks are held. This is acceptable for the current development checkpoint but should later move to a claim / lease state model before production scaling.

DEVELOPMENT MODEL NOTE

gemini-3.8-flash hit the current free-tier request quota during live testing.

The local development model was temporarily changed to gemini-3.5-flash-lite.

This does not change the provider architecture.

NEXT

First text-only LangGraph orchestration.
