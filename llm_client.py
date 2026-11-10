"""
Unified LLM Client supporting Groq API (Llama models) and Google Gemini REST APIs.
xAI Grok has been completely replaced by Groq + Llama.
"""
from groq_client import call_groq, extract_json
from gemini_client import call_gemini

def call_llm(prompt: str, api_key: str = None, provider: str = "groq", model: str = None, system_instruction: str = None, temperature: float = 0.2) -> str:
    """
    Unified LLM dispatcher for Groq (Llama) and Google Gemini.
    """
    prov = (provider or "groq").lower().strip()
    if "groq" in prov or "llama" in prov:
        return call_groq(prompt, api_key=api_key, model=model, system_instruction=system_instruction, temperature=temperature)
    elif "gemini" in prov:
        return call_gemini(prompt, api_key=api_key, system_instruction=system_instruction, temperature=temperature)
    raise ValueError(f"Unknown or unsupported LLM provider: '{provider}'. Supported providers are 'groq' and 'gemini'.")

__all__ = ["call_groq", "call_gemini", "call_llm", "extract_json"]
