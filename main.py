# main.py
import sys
import time
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

keywords = ["Superconductivity", "spin glass"]  # TODO: extend as needed

max_results_per_keyword = {
    "Superconductivity": 20,
    "spin glass": 10,
}

issues_result = 30  # Max papers to include in the GitHub Issue
column_names = ["Title", "Link", "Abstract", "Date", "Authors"]

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

# Uncomment to prevent running twice on the same day:
# if last_update_date == current_date:
#     sys.exit("Already updated today!")

# ── Main ──────────────────────────────────────────────────────────────────────

back_up_files()

try:
    # ── Step 1: Fetch papers from arXiv ──────────────────────────────────────
    keyword_papers: dict = {}

    for keyword in keywords:
        link = "AND" if len(keyword.split()) == 1 else "OR"
        max_result = max_results_per_keyword.get(keyword, 10)

        papers = get_daily_papers_by_keyword_with_retries(
            keyword, column_names, max_result, link
        )
        if papers is None:
            raise RuntimeError(f"Failed to fetch papers for keyword: '{keyword}'")

        keyword_papers[keyword] = papers
        time.sleep(5)  # Be polite to the arXiv API

    all_papers = [p for papers in keyword_papers.values() for p in papers]

    # ── Step 2: Translate all abstracts to Chinese (batched LLM calls) ────────
    print("[main] Translating abstracts …")
    for keyword, papers in keyword_papers.items():
        abstracts    = [p.get("Abstract", "") for p in papers]
        translations = batch_translate_to_chinese(abstracts, batch_size=5)
        for paper, cn in zip(papers, translations):
            paper["Abstract_CN"] = cn

    # ── Step 3: Generate per-topic overview summaries ─────────────────────────
    print("[main] Generating topic summaries …")
    topic_summaries: dict = {}
    for keyword, papers in keyword_papers.items():
        topic_summaries[keyword] = summarize_topic(keyword, papers)
        time.sleep(2)

    # ── Step 4: Compose email body (overview only) ────────────────────────────
    email_body = f"# Daily arXiv Papers – {get_daily_date()}\n\n"
    for keyword in keywords:
        email_body += f"## {keyword}\n\n{topic_summaries[keyword]}\n\n"

    # ── Step 5: Write README.md and ISSUE_TEMPLATE.md ─────────────────────────
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
        # PART 1 – Today's Overview
        # ══════════════════════════════════════════════════════════════════════
        overview_header = f"## 📋 Today's Overview\n*{get_daily_date()}*\n\n"
        f_rm.write(overview_header)
        f_is.write(overview_header)

        for keyword in keywords:
            block = f"### {keyword}\n\n{topic_summaries[keyword]}\n\n"
            f_rm.write(block)
            f_is.write(block)

        # ══════════════════════════════════════════════════════════════════════
        # PART 2 – Paper Details (title + bilingual abstract + authors + date)
        # ══════════════════════════════════════════════════════════════════════
        f_rm.write("---\n\n## 📄 Paper Details\n\n")
        f_is.write("---\n\n## 📄 Paper Details\n\n")

        for keyword in keywords:
            papers = keyword_papers[keyword]

            f_rm.write(f"### {keyword}\n\n")
            f_is.write(f"### {keyword}\n\n")

            rm_table = generate_table(papers)                       # full list
            is_table = generate_table(papers[:issues_result])       # capped list

            f_rm.write(rm_table + "\n\n")
            f_is.write(is_table + "\n\n")

    # ── Step 6: Send email ────────────────────────────────────────────────────
    send_daily_email(
        subject=f"📄 Daily arXiv Papers – {get_daily_date()}",
        body_markdown=email_body,
    )

except Exception as exc:
    print(f"[Error] {exc}")
    restore_files()
    sys.exit(1)

remove_backups()
print("[main] Done ✓")
