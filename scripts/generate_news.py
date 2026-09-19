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


FEEDS = {
    "বাংলাদেশ":
        "https://news.google.com/rss/search?q=Bangladesh&hl=bn&gl=BD&ceid=BD:bn",

    "বিশ্ব":
        "https://news.google.com/rss/search?q=World+News&hl=en-US&gl=US&ceid=US:en",

    "খেলা":
        "https://news.google.com/rss/search?q=Sports&hl=en-US&gl=US&ceid=US:en",

    "প্রযুক্তি":
        "https://news.google.com/rss/search?q=Technology&hl=en-US&gl=US&ceid=US:en"
}


# =========================================================
# COMMON FUNCTIONS
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<script.*?</script>",
        " ",
        text,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def make_id(text):

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:20]


def load_news():

    if not os.path.exists(NEWS_FILE):

        return {
            "updated_at": "",
            "articles": []
        }

    try:

        with open(
            NEWS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):

            return {
                "updated_at": "",
                "articles": []
            }

        if not isinstance(
            data.get("articles"),
            list
        ):

            data["articles"] = []

        return data

    except Exception as e:

        print(
            "news.json read error:",
            e
        )

        return {
            "updated_at": "",
            "articles": []
        }


def save_news(data):

    data["updated_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    with open(
        NEWS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        "news.json saved:",
        len(data["articles"]),
        "articles"
    )


# =========================================================
# REMOVE NEWSPAPER / WEBSITE REFERENCES
# =========================================================

SOURCE_WORDS = [
    "ndtv",
    "cnn",
    "bbc",
    "reuters",
    "yahoo",
    "fox news",
    "foxsports",
    "click2houston",
    "anandabazar",
    "আনন্দবাজার",
    "প্রথম আলো",
    "যুগান্তর",
    "কালের কণ্ঠ",
    "সমকাল",
    "ইত্তেফাক",
    "বাংলাদেশ প্রতিদিন",
    "dhaka tribune",
    "the daily star",
    "tbs",
    "new age",
    "associated press",
    "ap news",
    "al jazeera",
    "guardian",
    "washington post",
    "new york times",
    "financial times"
]


def remove_source_from_title(title):

    title = clean_text(title)

    pattern = (
        r"\s*[-|–—]\s*"
        r"(?:"
        + "|".join(
            re.escape(x)
            for x in SOURCE_WORDS
        )
        + r")"
        r"(?:\.com|\.net|\.org)?\s*$"
    )

    title = re.sub(
        pattern,
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"\s*[-|–—]\s*[A-Za-z0-9.-]+\.(?:com|net|org|co\.uk|co\.in)\s*$",
        "",
        title,
        flags=re.I
    )

    return title.strip(
        " -–—|"
    )


def remove_source_references(text):

    text = clean_text(text)

    lines = re.split(
        r"(?<=[.!?।])\s+",
        text
    )

    clean_lines = []

    for line in lines:

        low = line.lower()

        if (
            "source:" in low
            or "reference:" in low
            or "সূত্র:" in line
            or "রেফারেন্স:" in line
        ):
            continue

        if re.search(
            r"https?://|www\.",
            line,
            flags=re.I
        ):
            continue

        if any(
            word in low
            for word in SOURCE_WORDS
        ) and len(line) < 120:

            continue

        clean_lines.append(
            line.strip()
        )

    return " ".join(
        clean_lines
    ).strip()


# =========================================================
# RSS
# =========================================================

def get_rss_items(url):

    print("")
    print(
        "Reading RSS:",
        url
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            "RSS items:",
            len(feed.entries)
        )

        return feed.entries

    except Exception as e:

        print(
            "RSS ERROR:",
            e
        )

        return []


# =========================================================
# FIND IMAGE
# =========================================================

def extract_rss_image(entry):

    # media_content
    try:

        media = entry.get(
            "media_content"
        )

        if media:

            for item in media:

                url = item.get("url")

                if url:
                    return url

    except Exception:
        pass

    # media_thumbnail
    try:

        thumb = entry.get(
            "media_thumbnail"
        )

        if thumb:

            for item in thumb:

                url = item.get("url")

                if url:
                    return url

    except Exception:
        pass

    # enclosure
    try:

        enclosures = entry.get(
            "enclosures"
        )

        if enclosures:

            for item in enclosures:

                url = (
                    item.get("href")
                    or item.get("url")
                )

                if url:
                    return url

    except Exception:
        pass

    # Image inside RSS HTML
    try:

        raw = (
            entry.get("summary")
            or entry.get("description")
            or ""
        )

        match = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            raw,
            flags=re.I
        )

        if match:

            return match.group(1)

    except Exception:
        pass

    return ""


def extract_og_image(url):

    if not url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,bn;q=0.8"
    }

    try:

        response = requests.get(
            url,
            timeout=15,
            headers=headers,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        page = response.text

        # og:image (standard)
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            page,
            flags=re.I
        )
        if match:
            return html.unescape(match.group(1))

        # og:image (reversed attributes)
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            page,
            flags=re.I
        )
        if match:
            return html.unescape(match.group(1))

        # twitter:image
        match = re.search(
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            page,
            flags=re.I
        )
        if match:
            return html.unescape(match.group(1))

    except Exception as e:

        print(
            "OG image error:",
            e
        )

    return ""


# =========================================================
# UNIQUE FALLBACK IMAGE
# =========================================================

def make_unique_visual(
    category,
    title
):

    seed = make_id(
        category + "|" + title
    )

    number = int(
        seed[:8],
        16
    )

    palettes = [

        ("#991b1b", "#450a0a"),

        ("#1d4ed8", "#172554"),

        ("#047857", "#022c22"),

        ("#7c3aed", "#2e1065"),

        ("#c2410c", "#431407"),

        ("#0369a1", "#082f49"),

        ("#be123c", "#4c0519"),

        ("#4338ca", "#1e1b4b")
    ]

    color1, color2 = palettes[
        number % len(palettes)
    ]

    icons = {
        "বাংলাদেশ": "🇧🇩",
        "বিশ্ব": "🌍",
        "খেলা": "🏆",
        "প্রযুক্তি": "💻"
    }

    icon = icons.get(
        category,
        "📰"
    )

    short = clean_text(title)

    if len(short) > 32:
        short = short[:32] + "…"

    safe_title = (
        short
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    svg = f"""
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width="1200"
        height="675"
        viewBox="0 0 1200 675"
    >

        <defs>

            <linearGradient
                id="g"
                x1="0"
                y1="0"
                x2="1"
                y2="1"
            >

                <stop
                    offset="0%"
                    stop-color="{color1}"
                />

                <stop
                    offset="100%"
                    stop-color="{color2}"
                />

            </linearGradient>

        </defs>

        <rect
            width="1200"
            height="675"
            fill="url(#g)"
        />

        <circle
            cx="{250 + number % 500}"
            cy="100"
            r="180"
            fill="white"
            opacity=".08"
        />

        <circle
            cx="{900 - number % 400}"
            cy="560"
            r="260"
            fill="white"
            opacity=".06"
        />

        <text
            x="600"
            y="270"
            text-anchor="middle"
            font-size="130"
        >
            {icon}
        </text>

        <text
            x="600"
            y="390"
            text-anchor="middle"
            fill="white"
            font-size="42"
            font-family="Arial"
            font-weight="bold"
        >
            {safe_title}
        </text>

        <text
            x="600"
            y="470"
            text-anchor="middle"
            fill="white"
            opacity=".9"
            font-size="28"
            font-family="Arial"
        >
            DOP NEWS 24
        </text>

    </svg>
    """

    return (
        "data:image/svg+xml;charset=UTF-8,"
        + requests.utils.quote(
            svg,
            safe=""
        )
    )


# =========================================================
# GET BEST UNIQUE IMAGE
# =========================================================

def get_best_image(
    entry,
    article_url,
    used_images,
    category,
    title
):

    # 1. RSS Image
    image = extract_rss_image(
        entry
    )

    if image and image not in used_images:
        return image

    # 2. Extract OG Image from Redirect / Article Link
    if article_url:

        og = extract_og_image(
            article_url
        )

        if og and og not in used_images:
            return og

    # 3. Unique SVG Fallback
    return make_unique_visual(
        category,
        title
    )


# =========================================================
# AI WRITER
# =========================================================

def rewrite_with_ai(
    title,
    description,
    category
):

    if not OPENAI_API_KEY:

        print(
            "ERROR: OPENAI_API_KEY missing"
        )

        return None


    title = remove_source_from_title(
        title
    )

    description = remove_source_references(
        description
    )


    prompt = f"""
তুমি DOP NEWS 24-এর নিজস্ব বাংলা সংবাদ সম্পাদক।

বিভাগ:
{category}

মূল তথ্যের শিরোনাম:
{title}

প্রাপ্ত তথ্য:
{description}

এই তথ্যের ভিত্তিতে সম্পূর্ণ নতুনভাবে একটি বাংলা সংবাদ তৈরি করো।

অত্যন্ত গুরুত্বপূর্ণ নিয়ম:

1. কোনো সংবাদপত্র, টিভি চ্যানেল, নিউজ ওয়েবসাইট,
   নিউজ পোর্টাল বা তাদের domain-এর নাম লিখবে না।

2. "সূত্র", "রেফারেন্স", "Source", "Reference"
   লিখবে না।

3. কোনো URL বা ওয়েব লিংক লিখবে না।

4. মূল শিরোনাম হুবহু কপি করবে না।

5. মূল লেখার বাক্য হুবহু কপি করবে না।

6. সংবাদটি 4 থেকে 7টি ছোট অনুচ্ছেদে লিখবে।

7. তথ্য যতটুকু আছে তার ভিত্তিতে বিস্তারিতভাবে
   ব্যাখ্যা করবে।

8. তথ্যের বাইরে নতুন সংখ্যা, নাম, তারিখ,
   উদ্ধৃতি বা ঘটনা বানাবে না।

9. কোনো কাল্পনিক quotation তৈরি করবে না।

10. রাজনৈতিক বিষয় হলে সম্পূর্ণ নিরপেক্ষ ভাষা ব্যবহার করবে।

11. HTML tag, &nbsp;, URL বা অদ্ভুত code রাখবে না।

12. পাঠক যেন সাধারণ সংবাদপত্রের মতো স্বাভাবিক
    বাংলা সংবাদ পড়তে পারে এমনভাবে লিখবে।

শুধু JSON দেবে:

{{
  "title": "নতুন বাংলা সংবাদ শিরোনাম",
  "summary": "বিস্তারিত বাংলা সংবাদ"
}}
"""


    payload = {

        "model": MODEL,

        "input": prompt,

        "text": {

            "format": {

                "type": "json_schema",

                "name":
                "dop_news_article",

                "strict": True,

                "schema": {

                    "type": "object",

                    "properties": {

                        "title": {
                            "type": "string"
                        },

                        "summary": {
                            "type": "string"
                        }

                    },

                    "required": [
                        "title",
                        "summary"
                    ],

                    "additionalProperties":
                    False
                }
            }
        }
    }


    try:

        response = requests.post(

            "https://api.openai.com/v1/responses",

            headers={

                "Authorization":
                f"Bearer {OPENAI_API_KEY}",

                "Content-Type":
                "application/json"
            },

            json=payload,

            timeout=120
        )


        print(
            "OpenAI:",
            response.status_code
        )


        if response.status_code != 200:

            print(
                response.text[:2000]
            )

            return None


        result = response.json()

        output_text = ""


        for output in result.get(
            "output",
            []
        ):

            if output.get(
                "type"
            ) != "message":

                continue


            for content in output.get(
                "content",
                []
            ):

                if content.get(
                    "type"
                ) == "output_text":

                    output_text += (
                        content.get(
                            "text",
                            ""
                        )
                    )


        if not output_text:

            return None


        article = json.loads(
            output_text
        )


        new_title = (
            remove_source_from_title(
                article.get(
                    "title",
                    ""
                )
            )
        )


        new_summary = (
            remove_source_references(
                article.get(
                    "summary",
                    ""
                )
            )
        )


        if not new_title:
            return None

        if not new_summary:
            return None


        return {
            "title": new_title,
            "summary": new_summary
        }


    except Exception as e:

        print(
            "AI ERROR:",
            e
        )

        return None


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "========================================"
    )
    print(
        "DOP NEWS 24 CLEAN AUTO PUBLISHER"
    )
    print(
        "========================================"
    )


    data = load_news()


    old_articles = []

    for article in data.get(
        "articles",
        []
    ):

        article.pop(
            "source_url",
            None
        )

        old_articles.append(
            article
        )


    existing_ids = set()

    used_images = set()


    for article in old_articles:

        sid = article.get(
            "source_id"
        )

        if sid:

            existing_ids.add(
                sid
            )


        image = article.get(
            "image"
        )

        if image:

            used_images.add(
                image
            )


    new_articles = []


    for category, feed_url in FEEDS.items():

        print("")
        print(
            "CATEGORY:",
            category
        )


        entries = get_rss_items(
            feed_url
        )


        if not entries:

            continue


        count = 0


        for entry in entries:

            if count >= MAX_PER_CATEGORY:

                break


            raw_title = clean_text(
                entry.get(
                    "title",
                    ""
                )
            )


            raw_description = clean_text(
                entry.get(
                    "summary",
                    ""
                )
            )


            article_url = entry.get(
                "link",
                ""
            )


            if not raw_title:

                continue


            clean_title = (
                remove_source_from_title(
                    raw_title
                )
            )


            source_id = make_id(
                clean_title +
                "|" +
                article_url
            )


            if source_id in existing_ids:

                print(
                    "Duplicate:",
                    clean_title
                )

                continue


            print(
                "Processing:",
                clean_title
            )


            ai = rewrite_with_ai(
                clean_title,
                raw_description,
                category
            )


            if ai:

                final_title = ai["title"]

                final_summary = ai["summary"]

                print(
                    "AI article OK"
                )

            else:

                fallback_title = (
                    remove_source_from_title(
                        clean_title
                    )
                )

                fallback_summary = (
                    remove_source_references(
                        raw_description
                    )
                )

                if not fallback_summary:

                    print(
                        "Skipped: no clean content"
                    )

                    continue


                final_title = (
                    fallback_title
                )

                final_summary = (
                    fallback_summary
                )

                print(
                    "Clean fallback used"
                )


            image = get_best_image(
                entry,
                article_url,
                used_images,
                category,
                final_title
            )


            used_images.add(
                image
            )


            article = {

                "id":
                make_id(
                    source_id +
                    str(datetime.now())
                ),

                "source_id":
                source_id,

                "category":
                category,

                "title":
                final_title,

                "summary":
                final_summary,

                "image":
                image,

                "published_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
            }


            new_articles.append(
                article
            )


            existing_ids.add(
                source_id
            )


            count += 1


            if len(
                new_articles
            ) >= MAX_TOTAL:

                break


        if len(
            new_articles
        ) >= MAX_TOTAL:

            break


    print("")
    print(
        "New clean articles:",
        len(new_articles)
    )


    combined = (
        new_articles +
        old_articles
    )


    combined = combined[
        :MAX_TOTAL
    ]


    for article in combined:

        article.pop(
            "source_url",
            None
        )


    data["articles"] = combined


    save_news(
        data
    )


    print("")
    print(
        "========================================"
    )
    print(
        "PUBLISH COMPLETE"
    )
    print(
        "========================================"
    )


if __name__ == "__main__":

    main()
