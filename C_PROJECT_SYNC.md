C Project Sync

Last updated: 2026-09-05
Maintainer: Zainab's ChatGPT
Repository: https://github.com/zaynab-3/C.git
Current branch: feat/conversation-context

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

Bounded conversation context is implemented and unit-tested on this branch.
LIVE CONVERSATION CONTEXT E2E: VERIFIED.
History comes from existing Message records; there is no long-term memory or
LangGraph checkpointer. See CONVERSATION CONTEXT CHECKPOINT below.

WhatsApp audio input is complete and live E2E verified for English voice notes.
The text flow remains working. See WHATSAPP AUDIO INPUT CHECKPOINT for the
branch-close verification record and the separate Meta authorization incident.

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
-> current text or persisted audio transcript + bounded Message history
-> stateless text LangGraph (START -> generate_response -> END)
-> AIProvider / configured Gemini or OpenAI provider
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

108 passed
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

Current event types: process_message, send_whatsapp_reply

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
GeminiProvider     OpenAIProvider

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

LangGraph persistence/checkpointing and nodes beyond text generation

OpenAI audio transcription (Gemini inbound audio is live-verified; see checkpoint below)

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

dead-letter/operator tooling

production monitoring

stable production tunnel/domain

production hosting

Cloudflare Quick Tunnel remains DEVELOPMENT ONLY.

CURRENT TEXT ORCHESTRATION CHECKPOINT

The first text-only LangGraph orchestration flow is implemented, unit-tested, and live-verified.

Required direction:

WhatsApp message
-> worker
-> LangGraph
-> AIProvider
-> generated response
-> durable outbound delivery

Keep LangGraph provider-agnostic.

Do not allow Gemini/OpenAI SDKs to execute C tools directly.

Future scope (not part of this checkpoint):
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

d49df41
feat: add text LangGraph orchestration

Text LangGraph: IMPLEMENTED
Automated tests: 34 PASSED
Live WhatsApp -> LangGraph -> Gemini -> WhatsApp E2E: VERIFIED
Reliable generation / delivery split: VERIFIED

NEXT:
First multimodal input path: WhatsApp voice notes / audio.

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


TEXT LANGGRAPH CHECKPOINT

Branch: feat/langgraph-text-orchestration

WHAT CHANGED

- Added orchestration/text.py with typed input, state, result and invocation context.
- START -> generate_response -> END calls get_ai_provider() / AIProvider.
- c.process_message invokes the graph and persists its response/provider/model.
- The exact existing system prompt remains in the worker and is passed as context.
- The compiled graph is reused, with fresh state per invocation and no checkpointer.
- Provider errors propagate unchanged to the existing Celery generation retry boundary.
- Reply/AI metadata and outbound event still share one transaction.
- Delivery, duplicate protection and provider implementations are unchanged.
- No tools, actions or multimodal nodes were added.

WHAT WAS VERIFIED

- uv run pytest: 34 passed, 1 existing Starlette/AnyIO deprecation warning.
- Tests ran from an isolated temporary directory with dummy database/broker settings,
  avoiding the repository .env; provider and external delivery calls were mocked.
- Tests cover graph/provider calls and metadata, independent invocations,
  worker graph traversal, unchanged prompt, AI failure without persistence/delivery,
  saved-reply reuse, outbound delivery failures and outbox dispatch reliability.
- Live WhatsApp -> LangGraph -> AIProvider -> Gemini -> durable outbound -> WhatsApp E2E: VERIFIED.
- Live input: LangGraph live test 1. Reply with exactly: LANGGRAPH LIVE
- Phone received exactly: LANGGRAPH LIVE
- Live provider/model: gemini / gemini-3.5-flash-lite.
- PostgreSQL confirmed generated_reply=LANGGRAPH LIVE.
- PostgreSQL confirmed ai_generated_at, processed_at and outbound_external_id are populated.
- process_message outbox event: published, attempts=1, no error.
- send_whatsapp_reply outbox event: published, attempts=1, no error.

REVIEW NOTES

- Existing database row locks remain held during generation and delivery.
- Delivery remains at-least-once with the previously documented Meta/commit ambiguity.
- This checkpoint stops at stateless text orchestration; no further scope is implemented.


HISTORICAL AUDIO CHECKPOINT PLAN (completed below)

Start the first WhatsApp voice-note / audio input path.

Direction:

WhatsApp voice note
-> Meta media webhook
-> media retrieval
-> audio processing / transcription
-> LangGraph
-> AIProvider
-> generated response
-> existing durable outbound delivery

Keep text behavior unchanged while adding audio.


WHATSAPP AUDIO INPUT CHECKPOINT

Branch: feat/whatsapp-audio-input
Implementation status: complete, unit-tested and live E2E verified.
LIVE AUDIO E2E: VERIFIED (at least two English voice notes).
Lebanese audio: no successful live retest is recorded in this repository.

ARCHITECTURE

WhatsApp audio
-> authenticated webhook + sender authorization
-> media metadata + process_message outbox in one transaction
-> Meta media retrieval (fresh URL, then authenticated bounded download)
-> AIProvider.transcribe_audio() / Gemini configured model
-> persisted transcript + transcription metadata (separate commit)
-> existing text LangGraph
-> generated reply + send_whatsapp_reply outbox in one transaction
-> existing durable outbound text delivery

WHAT CHANGED

- Completed the existing 150a3b507d28 migration skeleton; no second migration.
- Added nine nullable media/transcription columns. Downgrade removes only those columns.
- Parent revision is cba3814f9172; Alembic reports a single head, 150a3b507d28.
- Audio webhook metadata is normalized with content=None; text extraction is preserved.
- Downloads are streamed and capped at MAX_DOWNLOADED_AUDIO_BYTES (14 MiB).
- Temporary media URLs and audio bytes are not persisted.
- Bearer authentication is used for both Meta requests; redirects are disabled and
  download URLs are restricted to HTTPS Meta media domains.
- Media errors omit response bodies, URLs, tokens and underlying exception details.
- AITranscription extends the shared provider contract. Gemini sends bytes and their
  MIME type through the installed google-genai SDK using self.model.
- The transcription prompt requests only original-language spoken content, without
  answering the speaker. Automatic function calling remains explicitly disabled.
- OpenAI text support is unchanged; audio transcription raises a clear unsupported error.
- The text graph and its exact system prompt are unchanged. No additional graph nodes.

RETRY / CONCURRENCY BEHAVIOR

- A persisted transcript skips media download and transcription on generation retries.
- The transcript is committed before LangGraph runs; processed_at remains unset.
- After that commit releases the row lock, the worker locks and refreshes the row,
  then rechecks generated_reply and processed_at before continuing.
- A saved generated reply skips all transcription and generation work.
- AIProviderError and WhatsAppMediaError retry c.process_message only.
- WhatsAppSendError retries delivery only, reusing the exact saved generated reply.

VALIDATION

- uv run pytest: 88 passed; one existing Starlette/AnyIO deprecation warning.
- Tests use mocked providers, HTTP transport and database sessions; no live APIs or DB.
- Tests ran from an isolated temporary directory with dummy DB/broker settings,
  so importing application settings did not read the repository .env.
- git diff --check passed.
- uv run alembic heads and uv run alembic history passed without running migrations.
- Migration/model parity and exact downgrade columns are unit-tested.
- Existing text, provider, outbound delivery and dispatcher tests remain passing.

REVIEW RISKS / LIMITS

- External calls still hold row locks, as in the current development architecture.
- A crash or failed commit after provider transcription but before transcript durability
  can repeat transcription. Persisted transcripts prevent repeat work on later retries;
  this is not an exactly-once guarantee for external provider calls.
- The conservative 14 MiB cap leaves room for inline base64 encoding and request
  overhead below the 20 MB total request limit; no Gemini Files API is used.
- Message.media_mime_type preserves the exact inbound Meta MIME. Gemini inline
  data uses its trimmed, lowercase audio MIME without parameters (for example,
  audio/ogg; codecs=opus becomes audio/ogg). No transcoding is performed.
- English voice-note transcription is live-verified; Lebanese transcription remains
  unverified. No transcoding is implemented.
- Previously documented at-least-once Meta delivery ambiguity remains unchanged.

LIVE VERIFICATION RECORD

Source: maintainer's branch-close handoff. The closing review used local tests and
static checks only; it did not rerun live APIs or inspect credentials.

- Migration 150a3b507d28 was applied successfully; alembic current reported
  150a3b507d28 (head), as confirmed by the maintainer.
- Docker worker was rebuilt successfully and FastAPI was restarted successfully.
- The live WhatsApp text precheck passed; existing text flow remains working.
- At least two English WhatsApp voice notes completed the full audio path:
  Meta webhook -> media metadata -> media download -> Gemini transcription ->
  transcript persistence -> text LangGraph -> Gemini response -> durable send
  outbox -> Meta WhatsApp delivery.
- Current Gemini development model used: gemini-3.5-flash-lite (configuration-driven).
- A later Lebanese voice-note attempt stopped at Meta media retrieval with HTTP 401
  after the access token became invalid/expired. It never reached transcription.
  This was an external Meta authorization issue, not an audio/transcription
  architecture failure, and it is not evidence of Lebanese transcription failure.
- The Meta token was refreshed afterward and WhatsApp functionality recovered.
  No successful Lebanese retest is recorded, so Lebanese audio is not claimed verified.
- Known cosmetic behavior remains: an audio worker log may show content=None because
  recognized speech lives in transcript. This does not change the processing input.

NEXT FEATURE

Conversation context is next. Long-term memory is not part of that next checkpoint.
No conversation-context implementation or new branch is started by this closing work.
This branch is not merged to main as part of closing.
No images, documents, tools, policy, approvals, calls, TTS or voice replies were added.


CONVERSATION CONTEXT CHECKPOINT

Branch: feat/conversation-context
Implementation status: complete, unit-tested and live E2E verified.
LIVE CONVERSATION CONTEXT E2E: VERIFIED.

ARCHITECTURE

Current Message
-> current text content or durably persisted audio transcript
-> bounded previous Message records using the current async SQLAlchemy session
-> chronological ConversationEntry(role, content) values
-> run_text_graph(input_text, history=..., system_prompt=...)
-> existing AIProvider.generate_text()
-> existing generated reply + delivery outbox transaction
-> existing independent WhatsApp delivery task

The application's PostgreSQL Message table is the only history source. The graph
remains stateless between invocations. No LangGraph checkpointer, checkpoint-postgres
package, second persistence store, new graph node or migration was added.
There is no long-term memory, summarization or image/document context in this checkpoint.
Future extracted modality text should feed the same provider-independent
ConversationEntry abstraction; those modalities are not implemented now.

HISTORY SELECTION / LIMIT

- Same channel and same sender_id only; current message ID is explicitly excluded.
- Only rows strictly before the current (received_at, created_at, id) tuple qualify.
- received_at defines chronological order; created_at and UUID id break ties.
  This is deterministic when timestamps match, without claiming UUIDs encode time.
- SQL orders newest-first and applies LIMIT before loading rows. The bounded result
  is reversed to chronological order before producing user/assistant entries.
- CONVERSATION_HISTORY_LIMIT defaults to 10 previous Message records, accepts 0-50,
  and is passed through the Docker worker environment. Zero disables the history query.
- Each record contributes at most two entries: user content followed by a saved reply.
  The default therefore supplies at most 20 history entries plus the current input.
- The limit counts Message records, including records with missing usable text.

NORMALIZATION / PROVIDER INPUT

- Historical text uses content; historical audio uses transcript, never content/media ID.
- Missing/blank audio transcripts contribute no invented user text.
- Nonblank persisted generated_reply becomes an assistant entry only after successful
  outbound delivery is persisted (processed_at is set). Pending/failed outbound replies
  are excluded so C does not act as though the user saw a reply they never received.
  Missing assistant replies are not fabricated.
- Unsupported modalities contribute no entries.
- Only content_type, content, transcript and generated_reply are selected as history
  data. Identifiers, sender metadata, raw webhook payload, media bytes and media URLs
  are not serialized into the prompt.
- Nonempty history is serialized as role-labeled JSON explicitly described as untrusted
  conversation data, with a separate current_user_message object. JSON escaping keeps
  embedded quotes/newlines from changing that structure.
- History is never placed in the system prompt. The exact existing system prompt and
  AIProvider interface remain unchanged; provider SDK tool execution remains disabled.
- With no history, the provider receives the current text exactly as before.

RELIABILITY / KNOWN LIMITATIONS

- Transcript commits and subsequent lock reacquisition still precede history loading.
- Saved generated replies skip history loading, transcription and graph generation.
- Generated reply metadata and send_whatsapp_reply outbox remain one transaction.
- Delivery retries only send the saved reply; they do not query context or regenerate.
- Generated-but-not-yet-delivered replies are excluded from assistant conversation context.
- Existing row-lock, AI/media retry, delivery retry and duplicate behavior is unchanged.
- There is no per-sender processing serialization. Context reflects available persisted
  state at query time; an earlier turn still generating may have no assistant entry.
  A generation retry can see newly persisted history. No snapshot is persisted for it.
- Bounds are by record count, not tokens/characters or elapsed time. Large transcripts
  can still produce large prompts; no summarization or final token-budget policy exists.
- No new history index is added. The SQL result is bounded, but query cost as Message
  volume grows should be reviewed before scaling.
- Existing external-call row-lock duration and at-least-once delivery risks remain.

VALIDATION

- Full pytest suite: 108 passed; one existing Starlette/AnyIO deprecation warning.
- Query tests execute the selection SQL against a local in-memory SQLite table with
  relevant schema columns; PostgreSQL SQL compilation is checked as well.
- Tests cover sender/channel isolation, current/future exclusion, timestamp/UUID ties,
  SQL limits, chronological roles, text/audio normalization and incomplete prior turns.
- Worker-to-real-graph tests cover text->text, text->audio, audio->text and audio->audio.
- Structural regressions verify the previous exchange for 'Btehkini m3arab?' followed
  by 'Ane benet', and the text/audio 'cedar' follow-up. No real model response is claimed.
- Tests verify role-safe JSON structure, unchanged system prompt, invocation isolation,
  saved-reply reuse and delivery retries without context loading or regeneration.
- Existing text and audio reliability tests remain passing.
- Tests ran with mocked providers/HTTP and dummy settings outside the repository cwd,
  avoiding the real .env. No live external APIs or development database were used.
- git diff --check passed. No migration changes or dependency additions.

LIVE WHATSAPP VERIFICATION

Conversation context is live E2E verified on WhatsApp.

Verified paths:
- text -> text: PASS
- text -> voice: PASS
- voice -> text: PASS
- voice -> voice: PASS

Regression verification:
- A prior Arabic/Arabizi exchange used masculine wording.
- Another full turn occurred afterward.
- The user then corrected with "Bas ana benettt".
- C used the recent conversation context and switched to feminine wording.
- This verifies that correction understanding survives an intervening turn.

Cross-modal verification:
- A typed test word was recalled from a later voice-note question.
- A voice-note test word was recalled from a later typed question.
- A voice-note test word ("maple") was recalled from a later voice-note question.

Known transcription-quality note:
- One mixed Arabic/English voice test intended as "olive" was transcribed as the
  a phonetic Arabic-script rendering rather than preserving the English word.
- The later context recall reproduced that persisted transcript correctly.
- This is a transcription-fidelity issue, not a conversation-context failure.

This checkpoint remains short-term/recent conversation context only.
It is not long-term memory.
Images and documents are not implemented yet.

NEXT

Conversation-context branch is complete, committed and pushed.
Merge this checkpoint to main after remote verification.
Do not start long-term memory or the next feature until the merge is complete.
