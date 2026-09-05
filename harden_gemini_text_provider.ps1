$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feat/ai-provider-abstraction') {
    throw "Expected branch feat/ai-provider-abstraction, found: $branch"
}

@'
from pathlib import Path

provider_path = Path("src/c_backend/ai/gemini_provider.py")
text = provider_path.read_text(encoding="utf-8")
old = '''        config = None
        if system_prompt and system_prompt.strip():
            config = types.GenerateContentConfig(
                system_instruction=system_prompt.strip()
            )
'''
new = '''        config = types.GenerateContentConfig(
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(
                    disable=True,
                )
            ),
            system_instruction=(
                system_prompt.strip()
                if system_prompt and system_prompt.strip()
                else None
            ),
        )
'''
if old not in text:
    raise SystemExit("Expected Gemini config block was not found; stopping safely.")
provider_path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Strengthen the existing provider test to prove AFC stays disabled.
test_path = Path("tests/test_ai_providers.py")
test_text = test_path.read_text(encoding="utf-8")
needle = '    assert call["config"] is not None\n'
replacement = '''    assert call["config"] is not None
    assert call["config"].automatic_function_calling is not None
    assert call["config"].automatic_function_calling.disable is True
'''
if replacement not in test_text:
    if needle not in test_text:
        raise SystemExit("Expected Gemini provider test assertion was not found; stopping safely.")
    test_path.write_text(test_text.replace(needle, replacement, 1), encoding="utf-8")

sync_path = Path("C_PROJECT_SYNC.md")
sync = sync_path.read_text(encoding="utf-8")
checkpoint = '''

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
'''
if "LIVE GEMINI PROVIDER CHECKPOINT" not in sync:
    sync_path.write_text(sync.rstrip() + checkpoint + "\n", encoding="utf-8")

print("Gemini provider hardened for text-only generation.")
'@ | uv run python -

Write-Host "`nRunning full test suite..."
uv run pytest -v
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed. Nothing will be committed."
}

Write-Host "`nRunning one live Gemini call..."
@'
import asyncio
from c_backend.ai import get_ai_provider

async def main():
    provider = get_ai_provider()
    result = await provider.generate_text(
        "Reply with exactly: C intelligence is online.",
        system_prompt=(
            "You are C, a reliable WhatsApp-first assistant. "
            "Follow the user's requested output exactly."
        ),
    )
    print("Provider:", result.provider)
    print("Model:", result.model)
    print("Response:", result.text)

asyncio.run(main())
'@ | uv run python -

if ($LASTEXITCODE -ne 0) {
    throw "Live Gemini verification failed. Nothing will be committed."
}

.\git-sync.ps1 "chore: harden Gemini provider tool boundary"
