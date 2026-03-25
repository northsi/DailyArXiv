import time
from typing import List, Dict
import google.generativeai as genai


def configure_gemini(api_key: str) -> None:
    """Configure the Gemini API with the provided key."""
    genai.configure(api_key=api_key)


def get_gemini_model(model_name: str = "gemini-1.5-flash"):
    """Return a configured Gemini GenerativeModel instance."""
    return genai.GenerativeModel(model_name)


def safe_generate(model, prompt: str, retries: int = 3, delay: int = 10) -> str:
    """Generate content with retry logic to handle transient API errors."""
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"  LLM call failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return ""


def summarize_papers_for_topic(papers: List[Dict], keyword: str, model) -> str:
    """Generate a concise English overview of all papers for a given topic."""
    if not papers:
        return "No papers found for this topic today."

    sample = papers[:10]  # limit to avoid token overflow
    papers_text = "\n\n".join(
        f"Title: {p.get('Title', 'N/A')}\nAbstract: {p.get('Abstract', 'N/A')}"
        for p in sample
    )

    prompt = (
        f'You are an expert scientific paper analyst. Below are today\'s arXiv papers on "{keyword}".\n\n'
        f"Write a concise overview (3–5 sentences) in English summarizing:\n"
        f"- The main research directions covered today\n"
        f"- Any notable trends or recurring themes\n"
        f"- What makes today's batch particularly interesting, if applicable\n\n"
        f"Papers:\n{papers_text}\n\n"
        f"Overview:"
    )

    return safe_generate(model, prompt)


def translate_abstract_to_chinese(abstract: str, model) -> str:
    """Translate a paper abstract from English to Chinese."""
    if not abstract:
        return ""

    prompt = (
        "Translate the following academic paper abstract from English to Chinese.\n"
        "Maintain academic accuracy and preserve technical terminology.\n"
        "Provide only the translation without any additional commentary.\n\n"
        f"Abstract:\n{abstract}\n\n"
        "Chinese Translation:"
    )

    return safe_generate(model, prompt)


def generate_knowledge_section(
    all_papers: List[Dict], keywords: List[str], model
) -> str:
    """
    Produce a structured list of key concepts and terms from today's papers
    that the reader should know or explore.
    """
    if not all_papers:
        return "No papers available to extract concepts from today."

    sample = all_papers[:15]  # limit to avoid token overflow
    papers_text = "\n\n".join(
        f"Title: {p.get('Title', 'N/A')}\nAbstract: {p.get('Abstract', 'N/A')}"
        for p in sample
    )
    topics_str = " and ".join(keywords)

    prompt = (
        f"You are an expert in {topics_str}. "
        f"Based on today's arXiv papers listed below, identify the key concepts, "
        f"techniques, and terms that a researcher should understand or explore.\n\n"
        f"Provide:\n"
        f"1. 6–10 key technical terms or concepts prominently featured today\n"
        f"2. A brief (1–2 sentence) plain-language explanation of each\n"
        f"3. A short note on why each is relevant based on today's papers\n\n"
        f"Papers:\n{papers_text}\n\n"
        f"Key Concepts & Keywords:"
    )

    return safe_generate(model, prompt)
