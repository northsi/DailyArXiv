# main.py
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta

import pytz

from llm_utils import (
    batch_summarize_findings,
    filter_low_quality_papers,
    summarize_topic,
)
from utils import (
    back_up_files,
    generate_table,
    get_daily_date,
    get_daily_papers_by_keyword_with_retries,
    remove_backups,
    restore_files,
)

# ── Configuration ─────────────────────────────────────────────────────────────

beijing_timezone = pytz.timezone("Asia/Shanghai")

keywords = ["NbSe2"]

max_results_per_keyword = {
    "NbSe2": 10,
}

column_names = ["Title", "Link", "Abstract", "Date", "Authors"]

CACHE_FILE = "paper_cache.json"

# ── Cache helpers ─────────────────────────────────────────────────────────────


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def clean_cache(cache: dict, keep_days: int = 90) -> dict:
    """清理旧缓存；保留质量判断以避免旧论文被重复筛选。"""
    cutoff = datetime.now(beijing_timezone) - timedelta(days=keep_days)
    cleaned = {}
    removed = 0
    for link, meta in cache.items():
        date_str = meta.get("Date", "")
        try:
            paper_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=beijing_timezone
            )
            if paper_date >= cutoff or meta.get("Quality_Filter"):
                cleaned[link] = meta
            else:
                removed += 1
        except (ValueError, TypeError):
            cleaned[link] = meta  # 日期解析失败的条目保留，不误删
    print(
        f"[debug]   Cache cleaned: removed {removed} old entries, kept {len(cleaned)}"
    )
    return cleaned


def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_papers():
    """Fetch configured topics using the existing request and retry policy."""
    # ── Step 1: Fetch papers from arXiv ──────────────────────────────────────
    print("[debug] Step 1: Fetching papers …")
    keyword_papers: dict = {}

    for keyword in keywords:
        link = "AND" if len(keyword.split()) == 1 else "OR"
        max_result = max_results_per_keyword.get(keyword, 10)
        print(f"[debug]   Fetching '{keyword}' (max={max_result}, link={link}) …")

        # 请求前随机等待 3～8 秒
        delay = random.uniform(3, 8)
        print(f"[debug]   Waiting {delay:.1f}s before request...")
        time.sleep(delay)

        papers = get_daily_papers_by_keyword_with_retries(
            keyword, column_names, max_result, link
        )
        if papers is None:
            raise RuntimeError(f"Failed to fetch papers for keyword: '{keyword}'")

        print(f"[debug]   Got {len(papers)} papers for '{keyword}'")
        keyword_papers[keyword] = papers
        time.sleep(5)
    return keyword_papers


def screen_papers(keyword_papers, paper_cache):
    """Apply quality screening before any finding summaries."""
    all_papers = [p for papers in keyword_papers.values() for p in papers]
    print(f"[debug] Total papers fetched: {len(all_papers)}")

    # Quality screening is the first AI stage, before any finding summaries.
    screened = filter_low_quality_papers(all_papers, paper_cache)
    accepted_links = {paper["Link"] for paper in screened}
    for keyword, papers in keyword_papers.items():
        keyword_papers[keyword] = [p for p in papers if p["Link"] in accepted_links]
    print(f"[main] Quality filter: kept {len(screened)} / {len(all_papers)} papers")


def summarize_papers(keyword_papers, paper_cache, existing_links):
    """Populate findings from cache or generate missing findings."""
    # ── Step 2: Summarize findings; migrate legacy translation caches ─────────
    print("[main] Summarizing abstract findings …")
    keyword_new_papers: dict = {}

    for keyword, papers in keyword_papers.items():
        new_papers = [p for p in papers if p.get("Link", "") not in existing_links]
        keyword_new_papers[keyword] = new_papers
        needs_summary = []
        for paper in papers:
            cached = paper_cache.get(paper.get("Link", ""), {})
            if cached.get("Finding_Summary"):
                paper["Finding_Summary"] = cached["Finding_Summary"]
            else:
                needs_summary.append(paper)

        if needs_summary:
            summaries = batch_summarize_findings(
                [p.get("Abstract", "") for p in needs_summary], batch_size=5
            )
            for paper, summary in zip(needs_summary, summaries):
                paper["Finding_Summary"] = summary
                paper_cache[paper["Link"]].pop("Abstract_CN", None)
                paper_cache[paper["Link"]].update(
                    {
                        "Finding_Summary": summary,
                        "Title": paper.get("Title", ""),
                        "Date": paper.get("Date", ""),
                    }
                )
        else:
            print(f"[debug]   '{keyword}': all findings loaded from cache ✓")
    return keyword_new_papers


def build_topic_summaries(keyword_new_papers):
    """Build daily overviews from accepted new papers."""
    # ── Step 3: 只对新文献生成 topic summary ──────────────────────────────────
    print("[main] Generating topic summaries …")
    topic_summaries: dict = {}
    for keyword in keywords:
        new_papers = keyword_new_papers[keyword]
        print(f"[debug]   Summarising '{keyword}': {len(new_papers)} new papers …")
        if new_papers:
            topic_summaries[keyword] = summarize_topic(keyword, new_papers)
            print(f"[debug]   Summary length: {len(topic_summaries[keyword])} chars")
        else:
            topic_summaries[keyword] = "*今日无通过筛选的新文献。*"
            print("[debug]   No new papers — summary skipped ✓")
        time.sleep(2)

    print("[debug] Step 3 complete ✓")
    return topic_summaries


def write_reports(keyword_papers, keyword_new_papers, topic_summaries, current_date):
    """Write the website content consumed by the Jekyll homepage."""
    # ── Step 4: Write website content ─────────────────────────
    print("[debug] Step 4: Writing website content …")
    with open("README.md", "w", encoding="utf-8") as f_rm:
        # ---------- README header ----------
        f_rm.write("# Daily Papers\n\n")
        f_rm.write(
            "The project automatically fetches the latest papers from arXiv based on keywords.\n\n"
            "The subheadings represent search keywords. "
            "Only the most recent articles per keyword are kept (up to 100).\n\n"
            "Results are displayed on this website after each scheduled update.\n\n"
        )
        f_rm.write(f"Last update: {current_date}\n\n---\n\n")

        # ══════════════════════════════════════════════════════════════════════
        # PART 1 – Today's Overview（只展示今日新文献的总结）
        # ══════════════════════════════════════════════════════════════════════
        overview_header = f"## 📋 Today's Overview\n*{get_daily_date()}*\n\n"
        f_rm.write(overview_header)

        for keyword in keywords:
            new_count = len(keyword_new_papers[keyword])
            block = f"### {keyword} ({new_count} new today)\n\n{topic_summaries[keyword]}\n\n"
            f_rm.write(block)

        # ══════════════════════════════════════════════════════════════════════
        # PART 2 – Paper Details（展示全部抓取到的文献，含缓存的发现总结）
        # ══════════════════════════════════════════════════════════════════════
        f_rm.write("---\n\n## 📄 Paper Details\n\n")

        for keyword in keywords:
            papers = keyword_papers[keyword]  # 全量展示
            print(
                f"[debug]   Generating table for '{keyword}' ({len(papers)} papers) …"
            )

            f_rm.write(f"### {keyword}\n\n")

            rm_table = generate_table(papers)
            f_rm.write(rm_table + "\n\n")

    print("[debug] Step 4 complete ✓")


def run_pipeline() -> None:
    """Execute fetch, screening, summaries and website generation."""
    current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")
    # 加载缓存，并快照已有的链接集合（在本次运行更新缓存之前）
    paper_cache = load_cache()
    existing_links = set(paper_cache.keys())
    print(f"[debug] Cache loaded: {len(existing_links)} previously processed papers")

    keyword_papers = fetch_papers()
    screen_papers(keyword_papers, paper_cache)
    keyword_new_papers = summarize_papers(keyword_papers, paper_cache, existing_links)
    paper_cache = clean_cache(paper_cache, keep_days=10)
    save_cache(paper_cache)
    print("[debug] Step 2 complete ✓ — cache updated & saved")
    topic_summaries = build_topic_summaries(keyword_new_papers)
    write_reports(keyword_papers, keyword_new_papers, topic_summaries, current_date)


def main() -> None:
    """Run the updater with report backup and restoration on failure."""
    back_up_files()
    try:
        run_pipeline()
    except Exception as exc:
        import traceback

        print(f"[Error] {exc}")
        print("[debug] Full traceback:")
        traceback.print_exc()
        restore_files()
        sys.exit(1)
    remove_backups()
    print("[main] Done ✓")


if __name__ == "__main__":
    main()
