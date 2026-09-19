import os
import json
import hashlib
import re
import html
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import feedparser


# =========================================================
# SETTINGS
# =========================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = "gpt-5.6-luna"

NEWS_FILE = "news.json"

MAX_PER_CATEGORY = 5
MAX_TOTAL = 20

# সরাসরি বিশ্বস্ত নিউজের RSS Feeds (ছবি ও বিস্তারিত তথ্যের জন্য সেরা)
FEEDS = {
    "বাংলাদেশ":
        "https://www.prothomalo.com/feed",

    "বিশ্ব":
        "https://feeds.bbci.co.uk/news/world/rss.xml",

    "খেলা":
        "https://feeds.bbci.co.uk/sport/rss.xml",

    "প্রযুক্তি":
        "https://www.wired.com/feed/rss"
}


# =========================================================
# COMMON FUNCTIONS
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def make_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def load_news():
    if not os.path.exists(NEWS_FILE):
        return {"updated_at": "", "articles": []}

    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"updated_at": "", "articles": []}

        if not isinstance(data.get("articles"), list):
            data["articles"] = []

        return data
    except Exception as e:
        print("news.json read error:", e)
        return {"updated_at": "", "articles": []}


def save_news(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("news.json saved:", len(data["articles"]), "articles")


# =========================================================
# REMOVE NEWSPAPER / WEBSITE REFERENCES
# =========================================================

SOURCE_WORDS = [
    "ndtv", "cnn", "bbc", "reuters", "yahoo", "fox news", "foxsports",
    "click2houston", "anandabazar", "आनन्दबाजार", "প্রথম আলো", "যুগান্তর",
    "কালের কণ্ঠ", "সমকাল", "ইত্তেফাক", "বাংলাদেশ প্রতিদিন", "dhaka tribune",
    "the daily star", "tbs", "new age", "associated press", "ap news",
    "al jazeera", "guardian", "washington post", "new york times", "financial times"
]


def remove_source_from_title(title):
    title = clean_text(title)
    pattern = (
        r"\s*[-|–—]\s*"
        r"(?:" + "|".join(re.escape(x) for x in SOURCE_WORDS) + r")"
        r"(?:\.com|\.net|\.org)?\s*$"
    )
    title = re.sub(pattern, "", title, flags=re.I)
    title = re.sub(
        r"\s*[-|–—]\s*[A-Za-z0-9.-]+\.(?:com|net|org|co\.uk|co\.in)\s*$",
        "",
        title,
        flags=re.I
    )
    return title.strip(" -–—|")


def remove_source_references(text):
    text = clean_text(text)
    lines = re.split(r"(?<=[.!?।])\s+", text)
    clean_lines = []

    for line in lines:
        low = line.lower()
        if any(k in low for k in ["source:", "reference:", "সূত্র:", "রেফারেন্স:"]):
            continue
        if re.search(r"https?://|www\.", line, flags=re.I):
            continue
        if any(word in low for word in SOURCE_WORDS) and len(line) < 120:
            continue
        clean_lines.append(line.strip())

    return " ".join(clean_lines).strip()


# =========================================================
# RSS
# =========================================================

def get_rss_items(url):
    print("\nReading RSS:", url)
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        print("RSS items:", len(feed.entries))
        return feed.entries
    except Exception as e:
        print("RSS ERROR:", e)
        return []


# =========================================================
# FIND IMAGE
# =========================================================

def extract_rss_image(entry):
    # 1. media_content
    try:
        media = entry.get("media_content")
        if media:
            for item in media:
                url = item.get("url")
                if url:
                    return url
    except Exception:
        pass

    # 2. media_thumbnail
    try:
        thumb = entry.get("media_thumbnail")
        if thumb:
            for item in thumb:
                url = item.get("url")
                if url:
                    return url
    except Exception:
        pass

    # 3. enclosures
    try:
        enclosures = entry.get("enclosures")
        if enclosures:
            for item in enclosures:
                url = item.get("href") or item.get("url")
                if url:
                    return url
    except Exception:
        pass

    # 4. HTML inside summary/description
    try:
        raw = entry.get("summary") or entry.get("description") or ""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw, flags=re.I)
        if match:
            return match.group(1)
    except Exception:
        pass

    return ""


def extract_og_image(url):
    if not url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            return ""

        page = response.text

        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', page, flags=re.I)
        if match:
            return html.unescape(match.group(1))

        match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', page, flags=re.I)
        if match:
            return html.unescape(match.group(1))

        match = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', page, flags=re.I)
        if match:
            return html.unescape(match.group(1))

    except Exception as e:
        print("OG image error:", e)

    return ""


def make_unique_visual(category, title):
    seed = make_id(category + "|" + title)
    number = int(seed[:8], 16)

    palettes = [
        ("#991b1b", "#450a0a"), ("#1d4ed8", "#172554"),
        ("#047857", "#022c22"), ("#7c3aed", "#2e1065"),
        ("#c2410c", "#431407"), ("#0369a1", "#082f49")
    ]
    color1, color2 = palettes[number % len(palettes)]

    icons = {"বাংলাদেশ": "🇧🇩", "বিশ্ব": "🌍", "খেলা": "🏆", "প্রযুক্তি": "💻"}
    icon = icons.get(category, "📰")

    short = clean_text(title)
    if len(short) > 32:
        short = short[:32] + "…"

    safe_title = short.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">
        <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{color1}"/><stop offset="100%" stop-color="{color2}"/></linearGradient></defs>
        <rect width="1200" height="675" fill="url(#g)"/>
        <text x="600" y="280" text-anchor="middle" font-size="120">{icon}</text>
        <text x="600" y="400" text-anchor="middle" fill="white" font-size="40" font-family="Arial" font-weight="bold">{safe_title}</text>
        <text x="600" y="480" text-anchor="middle" fill="white" opacity=".8" font-size="26" font-family="Arial">DOP NEWS 24</text>
    </svg>"""

    return "data:image/svg+xml;charset=UTF-8," + requests.utils.quote(svg, safe="")


def get_best_image(entry, article_url, used_images, category, title):
    # 1. RSS Image
    image = extract_rss_image(entry)
    if image and image not in used_images:
        return image

    # 2. Extract OG Image
    if article_url:
        og = extract_og_image(article_url)
        if og and og not in used_images:
            return og

    # 3. Unique SVG Fallback
    return make_unique_visual(category, title)


# =========================================================
# AI WRITER (DETAILED PARAGRAPHS)
# =========================================================

def rewrite_with_ai(title, description, category):
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY missing")
        return None

    title = remove_source_from_title(title)
    description = remove_source_references(description)

    prompt = f"""
তুমি DOP NEWS 24-এর একজন পেশাদার সংবাদ সম্পাদক।

বিভাগ: {category}
মূল শিরোনাম: {title}
প্রাপ্ত বিবরণ: {description}

উপরের তথ্যের ভিত্তিতে একটি সম্পূর্ণ এবং অত্যন্ত বিস্তারিত বাংলা সংবাদ তৈরি করো।

অত্যন্ত গুরুত্বপূর্ণ নিয়ম:
1. কোনো সংবাদপত্র, টিভি চ্যানেল বা ওয়েবসাইটের নাম উল্লেখ করবে না।
2. সংবাদটি বাধ্যতামূলকভাবে ৩ থেকে ৫টি ছোট ও সুগঠিত অনুচ্ছেদে (paragraphs) বিস্তারিত লিখবে।
3. প্রতিটি অনুচ্ছেদের মাঝে দুটি নতুন লাইন (\\n\\n) থাকবে যাতে পড়ার সময় প্যারাগ্রাফ আলাদা বোঝা যায়।
4. তথ্য সংক্ষেপ না করে যতটা সম্ভব বিস্তারিতভাবে ঘটনাটি বর্ণনা করবে।

JSON উত্তর ফরম্যাট:
{{
  "title": "নতুন বাংলা সংবাদ শিরোনাম",
  "summary": "প্রথম অনুচ্ছেদ...\\n\\nদ্বিতীয় অনুচ্ছেদ...\\n\\nতৃতীয় অনুচ্ছেদ..."
}}
"""

    payload = {
        "model": MODEL,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "dop_news_article",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"}
                    },
                    "required": ["title", "summary"],
                    "additionalProperties": False
                }
            }
        }
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            print("OpenAI error:", response.text[:1000])
            return None

        result = response.json()
        output_text = ""

        for output in result.get("output", []):
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        output_text += content.get("text", "")

        if not output_text:
            return None

        article = json.loads(output_text)
        new_title = remove_source_from_title(article.get("title", ""))
        new_summary = remove_source_references(article.get("summary", ""))

        if not new_title or not new_summary:
            return None

        return {"title": new_title, "summary": new_summary}

    except Exception as e:
        print("AI ERROR:", e)
        return None


# =========================================================
# MAIN
# =========================================================

def main():
    print("\n========================================\nDOP NEWS 24 PUBLISHER\n========================================")

    data = load_news()
    old_articles = [art for art in data.get("articles", []) if art.pop("source_url", None) is None]

    existing_ids = {art.get("source_id") for art in old_articles if art.get("source_id")}
    used_images = {art.get("image") for art in old_articles if art.get("image")}

    new_articles = []

    for category, feed_url in FEEDS.items():
        print("\nCATEGORY:", category)
        entries = get_rss_items(feed_url)
        if not entries:
            continue

        count = 0
        for entry in entries:
            if count >= MAX_PER_CATEGORY:
                break

            raw_title = clean_text(entry.get("title", ""))
            raw_description = clean_text(entry.get("summary") or entry.get("description", ""))
            article_url = entry.get("link", "")

            if not raw_title:
                continue

            clean_title = remove_source_from_title(raw_title)
            source_id = make_id(clean_title + "|" + article_url)

            if source_id in existing_ids:
                print("Duplicate:", clean_title)
                continue

            print("Processing:", clean_title)

            ai = rewrite_with_ai(clean_title, raw_description, category)

            if ai:
                final_title = ai["title"]
                final_summary = ai["summary"]
                print("AI article OK")
            else:
                final_title = remove_source_from_title(clean_title)
                final_summary = remove_source_references(raw_description)
                if not final_summary:
                    print("Skipped: no clean content")
                    continue
                print("Fallback text used")

            image = get_best_image(entry, article_url, used_images, category, final_title)
            used_images.add(image)

            article = {
                "id": make_id(source_id + str(datetime.now())),
                "source_id": source_id,
                "category": category,
                "title": final_title,
                "summary": final_summary,
                "image": image,
                "published_at": datetime.now(timezone.utc).isoformat()
            }

            new_articles.append(article)
            existing_ids.add(source_id)
            count += 1

            if len(new_articles) >= MAX_TOTAL:
                break

        if len(new_articles) >= MAX_TOTAL:
            break

    print("\nNew clean articles:", len(new_articles))

    combined = (new_articles + old_articles)[:MAX_TOTAL]
    data["articles"] = combined
    save_news(data)

    print("\n========================================\nPUBLISH COMPLETE\n========================================")


if __name__ == "__main__":
    main()
