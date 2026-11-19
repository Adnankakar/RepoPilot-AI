"""RAG Orchestration module

Purpose
-------
Generate grounded answers with verified file and line references. The flow is:

1. Retrieve relevant evidence (e.g., from a vector store or search service).
2. Build a prompt that includes the retrieved evidence and instructs the model to cite it
   using the ``[absolute_path:start-end]`` syntax.
3. Call the LLM via a concrete ``LLMProvider`` implementation.
4. Validate that the citations in the model output actually exist in the source
   files. If validation fails or there is insufficient evidence, return
   ``"not enough evidence"``.

Only the ``openrouter`` provider is required for this project, but the design
allows additional providers later.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple

import httpx

from .config import settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM Provider abstraction
# ---------------------------------------------------------------------------
class LLMProvider(ABC):
    """Abstract interface for an LLM service.

    Sub‑classes must implement :meth:`call_llm` which receives a full prompt
    (including any retrieved evidence) and returns the raw model response as a
    string.
    """

    @abstractmethod
    def call_llm(self, prompt: str) -> str:
        """Send *prompt* to the underlying model and return the response.
        Implementations may raise ``RuntimeError`` if the request fails.
        """
        raise NotImplementedError


class OpenRouterProvider(LLMProvider):
    """LLM provider that talks to the OpenRouter API.

    Configuration is read from ``app.core.config.settings`` which loads values
    from ``.env``:

    - ``LLM_PROVIDER`` – must be ``openrouter``.
    - ``LLM_MODEL`` – model identifier, e.g. ``particle-ai/particle-1:free``.
    - ``OPENROUTER_API_KEY`` – secret API key.
    """

    _endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self) -> None:
        if settings.llm_provider.lower() != "openrouter":
            raise RuntimeError(
                f"OpenRouterProvider configured with unsupported provider: {settings.llm_provider}"
            )
        self.model = settings.llm_model
        self.api_key = settings.openrouter_api_key
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in the environment")
        log.debug("OpenRouterProvider initialised for model %s", self.model)

    def _make_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your/repo",
        }

    def call_llm(self, prompt: str) -> str:
        """Call the OpenRouter API with exponential backoff.

        Retries up to ``MAX_RETRIES`` times with a jittered backoff. Handles
        timeouts and HTTP 429/503 rate‑limit or service‑unavailable responses.
        If the provider remains unavailable, a ``RuntimeError`` with a clear
        message is raised so the orchestration layer can surface an outage note.
        """
        import time
        import random

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        MAX_RETRIES = 5
        base_delay = 1.0  # seconds
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = httpx.post(
                    self._endpoint,
                    headers=self._make_headers(),
                    json=payload,
                    timeout=30.0,
                )
                if response.status_code in (429, 503):
                    # Rate limit or service unavailable – trigger retry
                    raise httpx.HTTPStatusError(
                        f"Rate limited / unavailable (status {response.status_code})",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                log.warning(
                    "OpenRouter request attempt %d failed: %s", attempt, exc
                )
                if attempt == MAX_RETRIES:
                    log.error("All retries exhausted – provider may be down")
                    raise RuntimeError(
                        "LLM provider is currently unavailable, please try again later."
                    ) from exc
                # exponential backoff with jitter
                delay = base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, delay * 0.1)
                time.sleep(delay + jitter)
            except Exception as exc:
                # Unexpected error – do not retry, bubble up
                log.exception("Unexpected OpenRouter request failure")
                raise RuntimeError(f"OpenRouter LLM call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Helper utilities for citation validation
# ---------------------------------------------------------------------------
def _read_lines(file_path: str, start: int, end: int) -> str:
    """Read lines *start*‑*end* (1‑based inclusive) from *file_path*.
    Returns the concatenated lines as a single string or an empty string on error.
    """
    try:
        p = Path(file_path)
        if not p.is_file():
            return ""
        with p.open(encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[start - 1 : end]).strip()
    except Exception:
        return ""


def _validate_citations(answer: str, evidence: List[Tuple[str, str, int, int]]) -> bool:
    """Ensure every citation in *answer* matches an item in *evidence*.

    Expected citation format: ``[absolute_path:start-end]``.
    The function returns ``True`` only if **all** citations correspond to an
    entry in *evidence* **and** the quoted snippet appears verbatim in the file.
    """
    citation_pat = re.compile(r"\[([^\]]+?):(\d+)-(\d+)\]")
    found = citation_pat.findall(answer)
    if not found:
        return False

    # Map (file, start, end) -> expected excerpt text
    evidence_map = { (fp, s, e): txt for txt, fp, s, e in evidence }

    for file_path, start_str, end_str in found:
        start, end = int(start_str), int(end_str)
        key = (file_path, start, end)
        expected = evidence_map.get(key)
        if expected is None:
            return False
        actual = _read_lines(file_path, start, end)
        if expected.strip() not in actual:
            return False
    return True


# ---------------------------------------------------------------------------
# Retrieval stub (to be replaced with real implementation)
# ---------------------------------------------------------------------------
def retrieve_evidence(query: str, top_k: int = settings.retrieval_top_k) -> List[Tuple[str, str, int, int]]:
    """Retrieve *top_k* evidence snippets for *query*.

    Returns a list of ``(text, file_path, start_line, end_line)`` tuples.
    The concrete implementation is project‑specific; for now we return an empty
    list so the module can be imported without additional dependencies.
    """
    # TODO: integrate with the project's vector store / search service.
    return []


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def build_prompt(question: str, evidence: List[Tuple[str, str, int, int]]) -> str:
    """Create a prompt that forces the LLM to cite the supplied evidence.

    The prompt tells the model to cite each excerpt using the format
    ``[absolute_path:start-end]``.
    """
    if not evidence:
        evidence_block = "(no evidence found)"
    else:
        lines = []
        for txt, file_path, start, end in evidence:
            lines.append(f"- {txt.strip()} [{file_path}:{start}-{end}]")
        evidence_block = "\n".join(lines)
    return (
        "The following excerpts have been retrieved from the code base. "
        "Use them to answer the question and include citations in the form "
        "[file:start-end].\n\nEvidence:\n"
        + evidence_block
        + "\n\nQuestion: "
        + question
    )


# Small evaluation set for answer quality
eval_set = [
    {
        "question": "How does the retrieval service compute the similarity threshold?",
        "expected_keywords": ["retrieval_similarity_threshold", "0.5"],
    },
    {
        "question": "What embedding model is used by default?",
        "expected_keywords": ["all-MiniLM-L6-v2"],
    },
]

def evaluate_answer(question: str, answer: str) -> bool:
    """Very lightweight quality check.

    Looks for the presence of any of the ``expected_keywords`` defined in
    ``eval_set`` for the given *question*. Returns ``True`` if at least one keyword
    is found; otherwise ``False``.
    """
    for entry in eval_set:
        if entry["question"] == question:
            for kw in entry["expected_keywords"]:
                if kw.lower() in answer.lower():
                    return True
            return False
    # If the question is not in the evaluation set, consider it passed.
    return True

    """Generate an answer with validated citations.

    1. Retrieve evidence.
    2. If no evidence → ``"not enough evidence"``.
    3. Build a prompt that includes the evidence.
    4. Call the LLM.
    5. Validate citations; on failure → ``"not enough evidence"``.
    """
    evidence = retrieve_evidence(question)
    if not evidence:
        return "not enough evidence"
    prompt = build_prompt(question, evidence)
    provider: LLMProvider = OpenRouterProvider()
    answer = provider.call_llm(prompt)
    if not _validate_citations(answer, evidence):
        return "not enough evidence"
    return answer


# ---------------------------------------------------------------------------
# Example usage (can be removed in production)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    q = "How does the retrieval service compute the similarity threshold?"
    try:
        ans = answer_question(q)
        print("Answer:\n", ans)
    except RuntimeError as e:
        print(e)
