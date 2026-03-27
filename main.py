# main.py
import sys
import time
import json
import os
import pytz
from datetime import datetime

from utils import (
    get_daily_papers_by_keyword_with_retries,
    generate_table,
    back_up_files,
    restore_files,
    remove_backups,
    get_daily_date,
)
from llm_utils import batch_translate_to_chinese, summarize_topic
from email_utils import send_daily_email

# ── Configuration ─────────────────────────────────────────────────────────────

beijing_timezone = pytz.timezone("Asia/Shanghai")
current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")

keywords = ["Superconductivity", "spin glass"]

max_results_per_keyword = {
    "Superconductivity": 20,
    "spin glass": 10,
}

issues_result = 30
column_names = ["Title", "Link", "Abstract", "Date", "Authors"]

CACHE_FILE = "paper_cache.json"

# ── Cache helpers ─────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ── Duplicate-run guard ───────────────────────────────────────────────────────

last_update_date = ""
try:
    with open("README.md", "r", encoding="utf-8") as f:
        for line in f:
            if "Last update:" in line:
                last_update_date = line.split(": ", 1)[1].strip()
                break
except FileNotFoundError:
    pass

# ── Main ──────────────────────────────────────────────────────────────────────

back_up_files()

# 加载缓存，并快照已有的链接集合（在本次运行更新缓存之前）
paper_cache = load_cache()
existing_links = set(paper_cache.keys())
print(f"[debug] Cache loaded: {len(existing_links)} previously processed papers")

try:
    # ── Step 1: Fetch papers from arXiv ──────────────────────────────────────
    print("[debug] Step 1: Fetching papers …")
    keyword_papers: dict = {}

    for keyword in keywords:
        link = "AND" if len(keyword.split()) == 1 else "OR"
        max_result = max_results_per_keyword.get(keyword, 10)
        print(f"[debug]   Fetching '{keyword}' (max={max_result}, link={link}) …")

        papers = get_daily_papers_by_keyword_with_retries(
            keyword, column_names, max_result, link
        )
        if papers is None:
            raise RuntimeError(f"Failed to fetch papers for keyword: '{keyword}'")

        print(f"[debug]   Got {len(papers)} papers for '{keyword}'")
        keyword_papers[keyword] = papers
        time.sleep(5)

    all_papers = [p for papers in keyword_papers.values() for p in papers]
    print(f"[debug] Total papers fetched: {len(all_papers)}")

    # ── Step 2: 只翻译新文献，旧文献从缓存读取 ────────────────────────────────
    print("[main] Translating abstracts …")
    keyword_new_papers: dict = {}  # 记录每个 keyword 的新文献，Step 3 用

    for keyword, papers in keyword_papers.items():
        new_papers    = [p for p in papers if p.get("Link", "") not in existing_links]
        cached_papers = [p for p in papers if p.get("Link", "") in existing_links]

        print(f"[debug]   '{keyword}': {len(new_papers)} new / {len(cached_papers)} from cache")
        keyword_new_papers[keyword] = new_papers

        # 旧文献直接从缓存填入 Abstract_CN，不调用 LLM
        for paper in cached_papers:
            paper["Abstract_CN"] = paper_cache[paper["Link"]].get("Abstract_CN", "")

        # 新文献才调用 LLM 翻译
        if new_papers:
            abstracts    = [p.get("Abstract", "") for p in new_papers]
            translations = batch_translate_to_chinese(abstracts, batch_size=5)
            for paper, cn in zip(new_papers, translations):
                paper["Abstract_CN"] = cn
                # 写入缓存
                paper_cache[paper["Link"]] = {
                    "Abstract_CN": cn,
                    "Title": paper.get("Title", ""),
                    "Date":  paper.get("Date",  ""),
                }
        else:
            print(f"[debug]   No new abstracts for '{keyword}' — LLM call skipped ✓")

    save_cache(paper_cache)
    print("[debug] Step 2 complete ✓ — cache updated & saved")

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
            topic_summaries[keyword] = "*今日无新文献。*"
            print(f"[debug]   No new papers — summary skipped ✓")
        time.sleep(2)

    print("[debug] Step 3 complete ✓")

    # ── Step 4: Compose email body ─────────────────────────────────────────────
    print("[debug] Step 4: Composing email body …")
    email_body = f"# Daily arXiv Papers – {get_daily_date()}\n\n"
    for keyword in keywords:
        new_count = len(keyword_new_papers[keyword])
        email_body += f"## {keyword} ({new_count} new today)\n\n{topic_summaries[keyword]}\n\n"
    print("[debug] Step 4 complete ✓")

    # ── Step 5: Write README.md and ISSUE_TEMPLATE.md ─────────────────────────
    print("[debug] Step 5: Writing README.md and ISSUE_TEMPLATE.md …")
    with open("README.md", "w", encoding="utf-8") as f_rm, \
         open(".github/ISSUE_TEMPLATE.md", "w", encoding="utf-8") as f_is:

        # ---------- README header ----------
        f_rm.write("# Daily Papers\n\n")
        f_rm.write(
            "The project automatically fetches the latest papers from arXiv based on keywords.\n\n"
            "The subheadings represent search keywords. "
            "Only the most recent articles per keyword are kept (up to 100).\n\n"
            "Click the **Watch** button to receive daily email notifications.\n\n"
        )
        f_rm.write(f"Last update: {current_date}\n\n---\n\n")

        # ---------- ISSUE header ----------
        f_is.write("---\n")
        f_is.write(f"title: Latest {issues_result} Papers – {get_daily_date()}\n")
        f_is.write("labels: documentation\n---\n")
        f_is.write(
            "**Check the [GitHub page](https://github.com/zezhishao/MTS_Daily_ArXiv) "
            "for a better reading experience and more papers.**\n\n"
        )

        # ══════════════════════════════════════════════════════════════════════
        # PART 1 – Today's Overview（只展示今日新文献的总结）
        # ══════════════════════════════════════════════════════════════════════
        overview_header = f"## 📋 Today's Overview\n*{get_daily_date()}*\n\n"
        f_rm.write(overview_header)
        f_is.write(overview_header)

        for keyword in keywords:
            new_count = len(keyword_new_papers[keyword])
            block = f"### {keyword} ({new_count} new today)\n\n{topic_summaries[keyword]}\n\n"
            f_rm.write(block)
            f_is.write(block)

        # ══════════════════════════════════════════════════════════════════════
        # PART 2 – Paper Details（展示全部抓取到的文献，含缓存的旧翻译）
        # ══════════════════════════════════════════════════════════════════════
        f_rm.write("---\n\n## 📄 Paper Details\n\n")
        f_is.write("---\n\n## 📄 Paper Details\n\n")

        for keyword in keywords:
            papers = keyword_papers[keyword]  # 全量展示
            print(f"[debug]   Generating table for '{keyword}' ({len(papers)} papers) …")

            f_rm.write(f"### {keyword}\n\n")
            f_is.write(f"### {keyword}\n\n")

            rm_table = generate_table(papers)
            is_table = generate_table(papers[:issues_result])

            f_rm.write(rm_table + "\n\n")
            f_is.write(is_table + "\n\n")

    print("[debug] Step 5 complete ✓")

    # ── Step 6: Send email ────────────────────────────────────────────────────
    smtp_port_raw = os.environ.get("SMTP_PORT", "").strip()
    if smtp_port_raw:
        print("[debug] Step 6: Sending email …")
        send_daily_email(
            subject=f"📄 Daily arXiv Papers – {get_daily_date()}",
            body_markdown=email_body,
        )
        print("[debug] Step 6 complete ✓")
    else:
        print("[debug] Step 6: Skipped — SMTP_PORT not configured.")

except Exception as exc:
    import traceback
    print(f"[Error] {exc}")
    print("[debug] Full traceback:")
    traceback.print_exc()
    restore_files()
    sys.exit(1)

remove_backups()
print("[main] Done ✓")
