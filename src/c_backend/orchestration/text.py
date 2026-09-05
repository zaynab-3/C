"""A stateless text graph; the worker owns persistence and retries."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from c_backend.ai import get_ai_provider


class TextInput(TypedDict):
    input_text: str


class TextResult(TypedDict):
    response_text: str
    provider: str
    model: str


class TextState(TextInput, TextResult):
    pass


class TextContext(TypedDict):
    system_prompt: str


async def generate_response(
    state: TextInput,
    runtime: Runtime[TextContext],
) -> TextResult:
    provider = get_ai_provider()
    response = await provider.generate_text(
        state["input_text"],
        system_prompt=runtime.context["system_prompt"],
    )
    return {
        "response_text": response.text,
        "provider": response.provider,
        "model": response.model,
    }


_builder = StateGraph(
    TextState,
    input_schema=TextInput,
    output_schema=TextResult,
    context_schema=TextContext,
)
_builder.add_node("generate_response", generate_response)
_builder.add_edge(START, "generate_response")
_builder.add_edge("generate_response", END)
_text_graph = _builder.compile()


async def run_text_graph(
    input_text: str,
    *,
    system_prompt: str,
) -> TextResult:
    return await _text_graph.ainvoke(
        {"input_text": input_text},
        context={"system_prompt": system_prompt},
    )
