"""bAInary refinement subsystem (D): LLM-based pseudo-C refinement."""

from bainary.refine.client import (
    AnthropicClient,
    LLMClient,
    MockClient,
    OpenAICompatibleClient,
    create_client,
)
from bainary.refine.errors import RefineError

# TODO(Task 5): re-export Refiner once refiner.py exists.
# from bainary.refine.refiner import Refiner

__all__ = [
    "RefineError",
    "create_client",
    "LLMClient",
    "OpenAICompatibleClient",
    "AnthropicClient",
    "MockClient",
]
