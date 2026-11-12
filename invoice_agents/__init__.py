"""Acme invoice processing agents: ingestion, validation, approval and payment."""

import os

# PydanticAI prints a promotional banner on first use; it would interleave with CLI output.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
