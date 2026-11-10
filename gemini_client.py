import json
import re
import requests

def call_grok(prompt: str, api_key: str, model: str = "grok-2-mini", system_instruction: str = None, temperature: float = 0.2) -> str:
    """
    Calls xAI Grok REST API (OpenAI-compatible endpoint).
    Supports grok-2-mini, grok-2, and grok-beta.
    """
    if not api_key:
        raise ValueError("xAI Grok API Key is missing. Please enter your xAI API key in the sidebar.")

    clean_key = api_key.strip()
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {clean_key}"
    }

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    models_to_try = [model, "grok-2-mini", "grok-beta", "grok-2"]
    seen = set()
    last_err = None

    for m in models_to_try:
        if m in seen:
            continue
        seen.add(m)
        payload = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
            else:
                last_err = f"{m} (HTTP {resp.status_code}): {resp.text[:120]}"
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(f"Grok API Error: {last_err}")


def call_gemini(prompt: str, api_key: str, system_instruction: str = None, temperature: float = 0.2) -> str:
    """
    Calls Google Gemini REST API directly using requests.
    Supports v1beta, v1, and multiple flash models with fast failover.
    """
    if not api_key:
        raise ValueError("Google Gemini API Key is missing. Please enter your API key in the sidebar.")

    clean_key = api_key.strip()

    # Helpful hint for keys that are not standard AI Studio keys
    if clean_key.startswith("AQ."):
        raise ValueError(
            "The entered API key starts with 'AQ...'. Google AI Studio keys typically start with 'AIzaSy...'. "
            "Please create a free API key at https://aistudio.google.com/app/apikey"
        )

    endpoints = [
        ("v1beta", "gemini-1.5-flash"),
        ("v1", "gemini-1.5-flash"),
        ("v1beta", "gemini-1.5-flash-latest"),
        ("v1beta", "gemini-2.0-flash")
    ]

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 1024,
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    last_err = None
    for api_ver, model in endpoints:
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model}:generateContent?key={clean_key}"
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=6
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
            else:
                last_err = f"{model} ({resp.status_code}): {resp.text[:120]}"
        except Exception as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"Gemini API Error: {last_err}")


def call_llm(prompt: str, api_key: str, provider: str = "gemini", system_instruction: str = None, temperature: float = 0.2) -> str:
    """Unified dispatcher for supported LLM providers (xAI Grok or Google Gemini)."""
    prov = (provider or "").lower()
    if "grok" in prov or "xai" in prov:
        return call_grok(prompt, api_key, system_instruction=system_instruction, temperature=temperature)
    return call_gemini(prompt, api_key, system_instruction=system_instruction, temperature=temperature)


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
