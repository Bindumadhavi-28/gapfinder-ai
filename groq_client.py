import os
import json
import re
from groq import Groq

DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FALLBACK_GROQ_MODELS = [
    DEFAULT_GROQ_MODEL,
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192"
]

def call_groq(prompt: str, api_key: str = None, model: str = None, system_instruction: str = None, temperature: float = 0.2) -> str:
    """
    Calls the official Groq API using the Groq Python SDK with Llama models.
    Supports llama-3.3-70b-versatile, llama-3.1-8b-instant, and automatic failover.
    """
    clean_key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
    if not clean_key:
        raise ValueError("Groq API Key is missing. Please enter your GROQ_API_KEY in the sidebar or .env file.")

    target_model = model or os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    client = Groq(api_key=clean_key)

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    # Try requested model first, then fallbacks
    models_to_try = [target_model] + [m for m in FALLBACK_GROQ_MODELS if m != target_model]
    last_err = None

    for m in models_to_try:
        try:
            chat_completion = client.chat.completions.create(
                messages=messages,
                model=m,
                temperature=temperature,
                max_completion_tokens=1024
            )
            if chat_completion.choices and chat_completion.choices[0].message:
                return chat_completion.choices[0].message.content or ""
        except Exception as e:
            err_str = str(e)
            last_err = err_str
            # Check for invalid API key
            if "401" in err_str or "invalid_api_key" in err_str.lower():
                raise ValueError("Invalid Groq API Key. Please verify your API key at https://console.groq.com/keys")
            # Check for rate limit
            if "429" in err_str or "rate_limit" in err_str.lower():
                raise RuntimeError("Groq API rate limit reached. Please wait a moment or switch to Built-in Local RAG.")
            continue

    raise RuntimeError(f"Groq API Error: {last_err}")


def extract_json(text: str):
    """Safely extracts JSON from an LLM response even if wrapped in markdown codeblocks."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        json_match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if json_match:
            return json.loads(json_match.group(1))
        raise
