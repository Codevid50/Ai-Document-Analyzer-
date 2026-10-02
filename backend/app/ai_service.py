import json
import os
import re
import time
from typing import Any, Callable

from dotenv import load_dotenv
from openai import (
    APIError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError(
        "OPENROUTER_API_KEY is not set in the environment."
    )


# ============================================================
# CONFIGURATION
# ============================================================

MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free",
)

# Transport-level retries (429, 5xx, timeouts, connection errors)
MAX_RETRIES = 4
BASE_WAIT_SECONDS = 5
MAX_WAIT_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 90.0

# Retries when the model returns bad JSON / wrong structure
CHUNK_MAX_RETRIES = 2

# Optional pause between chunk requests (helps with free-tier limits)
CHUNK_DELAY_SECONDS = float(os.getenv("CHUNK_DELAY_SECONDS", "0"))

MAX_DOCUMENT_CHARS = 30000

# HTTP statuses that will never succeed on retry
NON_RETRYABLE_STATUSES = (400, 402, 403, 422)


# ============================================================
# OPENROUTER CLIENT
# ============================================================

# max_retries=0 -> we handle retries ourselves, so they don't multiply
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
    timeout=REQUEST_TIMEOUT_SECONDS,
    max_retries=0,
)


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================

class AIServiceError(Exception):
    """Base exception for AI service errors."""


class AIRateLimitError(AIServiceError):
    """Raised when the AI provider is rate-limited."""


class AIAuthenticationError(AIServiceError):
    """Raised when the API key is invalid."""


class AIMalformedResponseError(AIServiceError):
    """Raised when the AI returns an invalid response."""


class AINonJsonResponseError(AIServiceError):
    """Raised when the provider returns non-JSON content
    (e.g. a safety/moderation response instead of a completion)."""


class AIModelUnavailableError(AIServiceError):
    """Raised when the requested model returns a 404."""


# ============================================================
# JSON CLEANING / PARSING
# ============================================================

def clean_json_response(content: str) -> str:
    """
    Remove <think> blocks and Markdown code fences from AI output.
    """

    content = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    content = content.strip()

    content = re.sub(
        r"^```(?:json)?\s*\n?",
        "",
        content,
    )
    content = re.sub(
        r"\n?```\s*$",
        "",
        content,
    )

    return content.strip()


def parse_json_response(content: str) -> dict[str, Any]:
    """
    Parse AI response content into a JSON object.

    Tolerates code fences and extra text before/after the JSON
    (e.g. "Here is your JSON: {...}").
    """

    cleaned = clean_json_response(content)

    if not cleaned:
        raise AIMalformedResponseError(
            "AI returned an empty response."
        )

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1:
        raise AINonJsonResponseError(
            "The AI model returned a non-JSON response instead of "
            "the requested completion. "
            f"First 200 chars: {cleaned[:200]!r}"
        )

    if end <= start:
        raise AIMalformedResponseError(
            "AI response looks truncated (no closing brace). "
            f"First 200 chars: {cleaned[:200]!r}"
        )

    try:
        result = json.loads(cleaned[start:end + 1], strict=False)
    except json.JSONDecodeError as error:
        raise AIMalformedResponseError(
            f"AI returned invalid JSON: {cleaned[:500]}"
        ) from error

    if not isinstance(result, dict):
        raise AIMalformedResponseError(
            "AI response must be a JSON object, "
            f"got {type(result).__name__}."
        )

    return result


# ============================================================
# AI REQUEST (TRANSPORT LAYER)
# ============================================================

def _request_completion(prompt: str) -> str:
    """
    Send one prompt to OpenRouter and return the raw text content.

    Retries with exponential backoff on:
    - 429 rate limits
    - 5xx provider errors
    - timeouts / connection errors
    - empty or malformed API envelopes (e.g. "no choices")

    Raises immediately on authentication errors, missing models,
    and requests the provider rejects (400/402/403/422).
    """

    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            if not response.choices:
                # OpenRouter can return an error object with HTTP 200
                provider_error = getattr(response, "error", None)
                detail = f" Provider error: {provider_error}" if provider_error else ""
                raise AIMalformedResponseError(
                    f"AI returned no choices.{detail}"
                )

            content = response.choices[0].message.content

            if not content or not content.strip():
                raise AIMalformedResponseError(
                    "AI returned an empty response."
                )

            return content

        except AuthenticationError as error:
            raise AIAuthenticationError(
                "Invalid API key. Check your "
                "OPENROUTER_API_KEY configuration."
            ) from error

        except NotFoundError as error:
            raise AIModelUnavailableError(
                f"Model unavailable: {MODEL}. Error: {error}"
            ) from error

        except RateLimitError as error:
            if "per-day" in str(error).lower():
                raise AIRateLimitError(
                    "OpenRouter's daily free-model limit has been "
                    "reached. Wait for the daily reset, add credits "
                    "to your OpenRouter account, or set "
                    "OPENROUTER_MODEL to a paid model."
                ) from error

            last_error = error

        except APIError as error:
            status = getattr(error, "status_code", None)

            if status in NON_RETRYABLE_STATUSES:
                raise AIServiceError(
                    f"AI provider rejected the request "
                    f"(HTTP {status}): {error}"
                ) from error

            last_error = error

        except AIMalformedResponseError as error:
            last_error = error

        except Exception as error:
            # Unexpected SDK/parsing failure on an odd provider reply
            last_error = error

        if attempt < MAX_RETRIES - 1:
            wait_time = min(
                BASE_WAIT_SECONDS * (2 ** attempt),
                MAX_WAIT_SECONDS,
            )

            print(
                f"AI request failed "
                f"({type(last_error).__name__}: "
                f"{str(last_error)[:200]}). "
                f"Retrying in {wait_time} seconds "
                f"(attempt {attempt + 1}/{MAX_RETRIES})..."
            )

            time.sleep(wait_time)

    # ---------------- all retries failed ----------------

    if isinstance(last_error, AIServiceError):
        raise last_error

    status = getattr(last_error, "status_code", None)

    if isinstance(last_error, RateLimitError) or status == 429:
        raise AIRateLimitError(
            "The AI provider is temporarily unavailable "
            "due to rate limiting. Please try again later."
        ) from last_error

    raise AIServiceError(
        f"AI request failed after {MAX_RETRIES} attempts: "
        f"{last_error}"
    ) from last_error


def ask_ai(prompt: str) -> dict[str, Any]:
    """
    Send a prompt and return the response parsed as a JSON object.

    May raise AIMalformedResponseError / AINonJsonResponseError
    if the model does not return usable JSON. Callers decide
    whether to retry or fall back.
    """

    content = _request_completion(prompt)

    return parse_json_response(content)


# ============================================================
# VALIDATION HELPERS
# ============================================================

def valid_string_list(
    value: Any,
    minimum: int,
    maximum: int | None = None,
) -> bool:
    """
    Check that value is a list of non-empty strings.
    """

    if not isinstance(value, list):
        return False

    if len(value) < minimum:
        return False

    if maximum is not None and len(value) > maximum:
        return False

    return all(
        isinstance(item, str) and item.strip()
        for item in value
    )


def validate_summary_text(value: Any) -> bool:
    """
    Check that value is a non-empty string.
    """
    return isinstance(value, str) and bool(value.strip())


def validate_chunk_summary(data: dict[str, Any]) -> bool:
    """
    Chunk summary needs:
    - summary: non-empty string
    - key_points: at least 3 non-empty strings
    (extra items are trimmed later instead of rejected)
    """

    if not validate_summary_text(data.get("summary")):
        return False

    return valid_string_list(
        data.get("key_points"),
        minimum=3,
    )


def validate_final_summary(data: dict[str, Any]) -> bool:
    """
    Final summary needs:
    - summary: non-empty string
    - key_points: at least 5 non-empty strings
    - key_takeaways: at least 3 non-empty strings
    (extra items are trimmed later instead of rejected)
    """

    if not validate_summary_text(data.get("summary")):
        return False

    if not valid_string_list(
        data.get("key_points"),
        minimum=5,
    ):
        return False

    if not valid_string_list(
        data.get("key_takeaways"),
        minimum=3,
    ):
        return False

    return True


def normalize_chunk_summary(
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "summary": data["summary"].strip(),
        "key_points": [
            point.strip()
            for point in data["key_points"]
        ][:5],
    }


def normalize_final_summary(
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "summary": data["summary"].strip(),
        "key_points": [
            point.strip()
            for point in data["key_points"]
        ][:8],
        "key_takeaways": [
            takeaway.strip()
            for takeaway in data["key_takeaways"]
        ][:5],
    }


# ============================================================
# VALIDATED GENERATION (SHARED RETRY LOGIC)
# ============================================================

def _generate_validated(
    prompt: str,
    validator: Callable[[dict[str, Any]], bool],
    label: str,
) -> dict[str, Any] | None:
    """
    Ask the AI for JSON and validate it.

    Retries when the model returns bad JSON, the wrong structure,
    or a transient provider error that survived the transport retries.

    Returns the validated dict, or None if every attempt failed
    (the caller then uses a fallback).

    Authentication, rate-limit and model-unavailable errors are
    raised, because retrying or falling back cannot fix them.
    """

    total_attempts = CHUNK_MAX_RETRIES + 1

    for attempt in range(total_attempts):

        try:
            result = ask_ai(prompt)

        except (
            AIAuthenticationError,
            AIRateLimitError,
            AIModelUnavailableError,
        ):
            raise

        except AIServiceError as error:
            print(
                f"{label}: attempt {attempt + 1}/{total_attempts} "
                f"failed - {type(error).__name__}: "
                f"{str(error)[:300]}"
            )
            continue

        if validator(result):
            return result

        print(
            f"{label}: attempt {attempt + 1}/{total_attempts} "
            f"returned the wrong JSON structure."
        )

    return None


# ============================================================
# FALLBACKS
# ============================================================

def _split_sentences(text: str) -> list[str]:
    return [
        s.strip()
        for s in re.split(r"[.!?]+", text)
        if s.strip() and len(s.strip()) > 20
    ]


def create_fallback_short_summary(text: str) -> dict[str, Any]:
    """
    Basic fallback for short documents when the AI fails.
    """

    truncated = text[:800].strip()
    if len(text) > 800:
        truncated += "..."

    sentences = _split_sentences(text)

    return {
        "summary": truncated,
        "key_points": sentences[:5] if sentences else [truncated],
        "key_takeaways": sentences[:3] if sentences else [truncated],
    }


def create_fallback_summary(
    chunk: str,
    section_number: int,
) -> dict[str, Any]:
    """
    Basic fallback for one chunk when the AI fails.
    """

    truncated = chunk[:500].strip()
    if len(chunk) > 500:
        truncated += "..."

    sentences = _split_sentences(chunk)

    return {
        "summary": truncated or f"Section {section_number}",
        "key_points": sentences[:5] if sentences else [
            truncated or f"Section {section_number}"
        ],
    }


def create_fallback_final_summary(
    chunk_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Merge chunk summaries directly when the AI fails on the
    final step.
    """

    all_summaries: list[str] = []
    all_points: list[str] = []

    for chunk_summary in chunk_summaries:
        all_summaries.append(chunk_summary.get("summary", ""))
        all_points.extend(chunk_summary.get("key_points", []))

    joined = " ".join(all_summaries)

    combined_summary = joined[:500]
    if len(joined) > 500:
        combined_summary += "..."

    return {
        "summary": combined_summary,
        "key_points": all_points[:8] if all_points else [
            combined_summary
        ],
        "key_takeaways": all_points[:3] if all_points else [
            combined_summary
        ],
    }


# ============================================================
# SHORT DOCUMENT
# ============================================================

def summarize_short_document(text: str) -> dict[str, Any]:
    """
    Summarize a document that fits into one chunk.
    """

    prompt = f"""
You are an expert document summarizer.

Analyze the document below and produce a concise summary.

Return ONLY a valid JSON object with this exact structure:

{{
    "summary": "A clear, concise overview of the document in 100-150 words.",
    "key_points": [
        "Key point 1 (1-2 sentences)",
        "Key point 2 (1-2 sentences)",
        "Key point 3 (1-2 sentences)",
        "Key point 4 (1-2 sentences)",
        "Key point 5 (1-2 sentences)"
    ],
    "key_takeaways": [
        "Takeaway 1 (one concise sentence)",
        "Takeaway 2 (one concise sentence)",
        "Takeaway 3 (one concise sentence)"
    ]
}}

STRICT RULES:

- summary: maximum 100-150 words. Be concise.
- key_points: 5-8 items. Each must be 1-2 sentences maximum.
- key_takeaways: 3-5 items. Each must be one concise sentence.
- Do NOT repeat the same information across fields.
- Every item must be a non-empty string.
- Only use information from the document.
- Never invent facts or hallucinate content.
- Preserve important names, numbers, dates, and definitions.
- Return JSON only. No Markdown. No code fences.

DOCUMENT:

{text}
"""

    result = _generate_validated(
        prompt,
        validate_final_summary,
        "Short document",
    )

    if result is not None:
        return normalize_final_summary(result)

    print(
        "Short document: AI failed on every attempt. "
        "Using fallback summary."
    )

    return create_fallback_short_summary(text)


# ============================================================
# CHUNK SUMMARIZATION
# ============================================================

def summarize_chunk(
    chunk: str,
    section_number: int,
) -> dict[str, Any]:
    """
    Summarize one chunk of a large document.
    """

    prompt = f"""
You are summarizing section {section_number} of a larger document.

Return ONLY a valid JSON object with this exact structure:

{{
    "summary": "A concise summary of this section in 50-100 words.",
    "key_points": [
        "Key point 1 (one sentence)",
        "Key point 2 (one sentence)",
        "Key point 3 (one sentence)"
    ]
}}

STRICT RULES:

- summary: maximum 50-100 words. Be concise.
- key_points: exactly 3-5 items. Each must be one sentence.
- Every item must be a non-empty string.
- Only use information from this section.
- Never invent information.
- Preserve important names, numbers, dates, and facts.
- Focus on the most important ideas from this section.
- Return JSON only. No Markdown. No code fences.

DOCUMENT SECTION:

{chunk}
"""

    result = _generate_validated(
        prompt,
        validate_chunk_summary,
        f"Section {section_number}",
    )

    if result is not None:
        return normalize_chunk_summary(result)

    print(
        f"Section {section_number}: AI failed on every attempt. "
        f"Using fallback summary."
    )

    return create_fallback_summary(
        chunk,
        section_number,
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

def create_final_summary(
    chunk_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Combine all chunk summaries into one final summary.
    """

    combined = json.dumps(
        chunk_summaries,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
You are creating the final summary of a document.

Below are summaries from ALL parts of the document.
Use information from ALL of them to create a comprehensive overview.

Return ONLY a valid JSON object with this exact structure:

{{
    "summary": "A clear, concise overview of the entire document in 100-150 words.",
    "key_points": [
        "Key point 1 (1-2 sentences)",
        "Key point 2 (1-2 sentences)",
        "Key point 3 (1-2 sentences)",
        "Key point 4 (1-2 sentences)",
        "Key point 5 (1-2 sentences)"
    ],
    "key_takeaways": [
        "Takeaway 1 (one concise sentence)",
        "Takeaway 2 (one concise sentence)",
        "Takeaway 3 (one concise sentence)"
    ]
}}

STRICT RULES:

- summary: maximum 100-150 words. Be concise.
- key_points: 5-8 items. Each must be 1-2 sentences maximum.
- key_takeaways: 3-5 items. Each must be one concise sentence.
- Combine duplicate ideas from different sections.
- Every item must be a non-empty string.
- Use information from ALL supplied summaries.
- Select the most important information overall.
- Do not focus only on the first or last section.
- Never invent information.
- Preserve important names, numbers, dates, and facts.
- Do not mention chunking, sections, or parts.
- Return JSON only. No Markdown. No code fences.

SECTION SUMMARIES:

{combined}
"""

    result = _generate_validated(
        prompt,
        validate_final_summary,
        "Final summary",
    )

    if result is not None:
        return normalize_final_summary(result)

    print(
        "Final summary: AI failed on every attempt. "
        "Using fallback summary."
    )

    return create_fallback_final_summary(chunk_summaries)


# ============================================================
# MAIN SUMMARIZATION FUNCTION
# ============================================================

def summarize_text(
    text: str,
    chunks: list[str],
) -> dict[str, Any]:
    """
    Summarize a document.

    Short document:
        one AI request -> final summary

    Long document:
        chunks -> chunk summaries -> one final AI request
    """

    if not text.strip():
        raise ValueError("Document contains no text.")

    if not chunks:
        raise ValueError("No text chunks were created.")

    # ---------------- short document ----------------

    if len(chunks) == 1:
        return summarize_short_document(chunks[0])

    # ---------------- long document -----------------

    chunk_summaries: list[dict[str, Any]] = []

    for section_number, chunk in enumerate(chunks, start=1):

        print(
            f"Summarizing section "
            f"{section_number}/{len(chunks)}..."
        )

        try:
            chunk_summary = summarize_chunk(
                chunk=chunk,
                section_number=section_number,
            )

        except Exception as error:
            print(
                f"\nFAILED ON SECTION "
                f"{section_number}/{len(chunks)}"
            )
            print(f"Error type: {type(error).__name__}")
            print(f"Error: {error}")
            raise

        chunk_summaries.append(chunk_summary)

        if CHUNK_DELAY_SECONDS > 0 and section_number < len(chunks):
            time.sleep(CHUNK_DELAY_SECONDS)

    print("Creating final summary...")

    return create_final_summary(chunk_summaries)


# ============================================================
# ASK QUESTION
# ============================================================

def ask_question(
    text: str,
    question: str,
    history: list[dict] | None = None,
) -> str:
    """
    Answer a question about a document.
    Returns a plain string answer.
    """

    truncated = text[:MAX_DOCUMENT_CHARS]
    if len(text) > MAX_DOCUMENT_CHARS:
        truncated += "\n\n[Document truncated due to length]"

    conversation = ""
    if history:
        conversation = "CONVERSATION SO FAR:\n"
        conversation += "\n".join(
            f"{'User' if message['role'] == 'user' else 'Assistant'}: "
            f"{' '.join(message['content'].split())}"
            for message in history
        )
        conversation += (
            "\n\nUse the conversation only to understand follow-up questions; "
            "answers must still come only from the document.\n\n"
        )

    prompt = f"""You are an AI document assistant.

Answer the user's question using ONLY the information contained in the
document below.

RULES:

1. Do not use outside knowledge.
2. Do not invent, assume, or guess information.
3. Answer the user's question directly.
4. Stay focused on the question.
5. Do not summarize the entire document unless the question requires it.
6. If the question contains an incorrect assumption, correct it based on
   the document.
7. If the document does not contain enough information to answer the
   question, say:
   "The document does not contain enough information to answer this question."
8. Explain the reasoning when necessary.
9. Use the document's specific ideas, examples, facts, names, or arguments
   when they help answer the question.
10. Prefer paraphrasing over quoting.
11. Do not reproduce long passages from the document.
12. Only use short quotes when the exact wording is important.
13. Do not repeat the same idea.
14. Do not add unnecessary headings or filler.

ANSWER LENGTH:

- Simple question -> 1-3 short paragraphs.
- "Why" / "How" question -> explain the reasoning clearly.
- "Explain" / "Elaborate" -> give a moderately detailed answer, usually
  3-5 short paragraphs or a few useful bullet points.
- Do not make the answer longer just because the document is long.

IMPORTANT:

The answer should feel like a knowledgeable assistant explaining the
document to the user, not like a summary of the entire document.

{conversation}QUESTION:
{question}

DOCUMENT:
{truncated}

ANSWER:
"""

    content = _request_completion(prompt)

    answer = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    if not answer:
        raise AIMalformedResponseError(
            "AI returned an empty answer."
        )

    return answer