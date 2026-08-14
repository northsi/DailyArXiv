import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
from typing import List, Tuple

def get_latest_papers() -> List[Tuple[str, str, str]]:
    """
    Scrape the latest papers from the MTS_Daily_ArXiv GitHub page.
    
    Returns:
        List of tuples containing (title, summary, date) for each paper.
        Date is formatted as 'YYYY-MM-DD'.
    """
    url = "https://github.com/zezhishao/MTS_Daily_ArXiv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[Error] Failed to fetch GitHub page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the README content (usually in a .markdown-body div)
    readme = soup.find('div', {'class': 'markdown-body'})
    if not readme:
        print("[Error] Could not find README content on the page.")
        return []

    # Extract the date from the overview header
    date_match = re.search(r'\*(\w+ \d{1,2}, \d{4})\*', readme.get_text())
    if not date_match:
        paper_date = datetime.now().strftime("%Y-%m-%d")
    else:
        try:
            dt = datetime.strptime(date_match.group(1), "%B %d, %Y")
            paper_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            paper_date = datetime.now().strftime("%Y-%m-%d")

    papers = []
    # Find all list items that start with a number followed by a period (e.g., "1.  The study focuses on...")
    list_items = readme.find_all('li')
    
    for item in list_items:
        text = item.get_text().strip()
        # Match items that start with a number and a period (e.g., "1.  The study...")
        match = re.match(r'^\d+\.\s+(The study focuses on\s+(.+?)(?:,\s+employing\s+(.+?))?(?:,\s+to address/solve\s+(.+?))?\.)', text)
        if match:
            full_sentence = match.group(1)
            focus_area = match.group(2).strip() if match.group(2) else ""
            method = match.group(3).strip() if match.group(3) else ""
            challenge = match.group(4).strip() if match.group(4) else ""

            # Construct a concise title and summary
            title = f"Study on {focus_area}"
            summary_parts = []
            if method:
                summary_parts.append(f"Method: {method}")
            if challenge:
                summary_parts.append(f"Challenge: {challenge}")
            summary = " | ".join(summary_parts) if summary_parts else "No additional details provided."

            papers.append((title, summary, paper_date))

    return papers