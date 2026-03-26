# llm_utils.py
import os
import re
import time
from typing import List, Dict

from openai import OpenAI


def _get_client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "DEEPSEEK_API_KEY is not set. "
            "Add it as a GitHub secret and pass it to the workflow step."
        )
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")


def _call_llm(
    prompt: str,
    model: str = "deepseek-chat",
    max_tokens: int = 2048,
    max_retries: int = 3,
) -> str:
    """Call the DeepSeek (OpenAI-compatible) API with automatic retry."""
    client = _get_client()
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[LLM] Attempt {attempt + 1}/{max_retries} failed: {exc}")
            if attempt < max_retries - 1:
                time.sleep(10)
    return ""


def batch_translate_to_chinese(texts: List[str], batch_size: int = 5) -> List[str]:
    """
    Translate a list of English abstracts into Chinese in batches.
    Returns a list of translated strings in the same order as the input.
    Batching reduces API round-trips significantly.
    """
    results = [""] * len(texts)

    for batch_start in range(0, len(texts), batch_size):
        batch = texts[batch_start : batch_start + batch_size]
        numbered_input = "\n\n".join(
            f"[{i + 1}] {text}" for i, text in enumerate(batch)
        )
        prompt = (
            f"请将以下 {len(batch)} 段英文学术摘要逐一翻译为中文，保持专业术语准确。\n"
            "严格按照如下格式输出，每条以编号开头，只输出翻译内容，不要有任何额外说明：\n"
            "[1] <第一段翻译>\n[2] <第二段翻译>\n……\n\n"
            f"{numbered_input}"
        )
        raw = _call_llm(prompt, max_tokens=3000)

        # Parse the numbered output robustly
        matches = re.findall(r"\[(\d+)\]\s*([\s\S]*?)(?=\[\d+\]|$)", raw)
        for num_str, translation in matches:
            idx = int(num_str) - 1
            if 0 <= idx < len(batch):
                results[batch_start + idx] = translation.strip()

        time.sleep(3)  # Respect API rate limits

    return results


def summarize_topic(keyword: str, papers: List[Dict]) -> str:
    """
    Generate an introductory overview paragraph (in English) for a topic's
    papers. Returns a plain-text/markdown paragraph.
    """
    if not papers:
        return f"*No papers found for '{keyword}' today.*"

    paper_snippets = "\n\n".join(
        f"{i + 1}. **{p.get('Title', '')}**\n   {p.get('Abstract', '')[:400]}…"
        for i, p in enumerate(papers)
    )
    prompt = (
        f"You are an expert in condensed matter physics and materials science.\n"
        f"Below are today's arXiv papers on the topic \"{keyword}\".\n"
        "Write a concise overview paragraph (4–6 sentences) in English summarising "
        "the main research themes, methodological trends, and notable findings "
        "across these papers. Be informative and precise. "
        "Do NOT enumerate the papers individually.\n\n"
        f"Papers:\n{paper_snippets}\n\nOverview:"
    )
    return _call_llm(prompt, max_tokens=600)


def extract_key_concepts(all_papers: List[Dict]) -> str:
    """
    Identify 6–10 important technical keywords / concepts from all today's
    papers and return a markdown-formatted explanation list.
    """
    if not all_papers:
        return "*Not enough papers to extract concepts today.*"

    sample = all_papers[:20]  # Stay within token budget
    paper_snippets = "\n".join(
        f"{i + 1}. {p.get('Title', '')}: {p.get('Abstract', '')[:250]}…"
        for i, p in enumerate(sample)
    )
    prompt = (
        "You are an expert researcher in physics and condensed matter science.\n"
        "Based on today's arXiv papers listed below, identify 6–10 important "
        "technical keywords, methods, or physical concepts that are central to "
        "understanding these papers.\n"
        "For each item provide:\n"
        "- The term in **bold** (include the Chinese name in parentheses)\n"
        "- A concise 1–2 sentence explanation of what it is and why it matters\n\n"
        "Format the output as a markdown bulleted list.\n\n"
        f"Papers:\n{paper_snippets}"
    )
    return _call_llm(prompt, max_tokens=1200)
