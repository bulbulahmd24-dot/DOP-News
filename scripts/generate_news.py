import os
import json
import hashlib
from datetime import datetime, timezone

import requests
import feedparser


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = "gpt-5.6-luna"

NEWS_FILE = "news.json"

MAX_PER_CATEGORY = 5
MAX_TOTAL = 40


FEEDS = {
    "বাংলাদেশ": "https://news.google.com/rss/search?q=Bangladesh&hl=bn&gl=BD&ceid=BD:bn",
    "বিশ্ব": "https://news.google.com/rss/search?q=World+News&hl=en-US&gl=US&ceid=US:en",
    "খেলা": "https://news.google.com/rss/search?q=Sports&hl=en-US&gl=US&ceid=US:en",
    "প্রযুক্তি": "https://news.google.com/rss/search?q=Technology&hl=en-US&gl=US&ceid=US:en",
}


def load_news():
    if not os.path.exists(NEWS_FILE):
        return {
            "updated_at": "",
            "articles": []
        }

    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"updated_at": "", "articles": []}

        if "articles" not in data:
            data["articles"] = []

        return data

    except Exception as e:
        print("news.json read error:", e)
        return {
            "updated_at": "",
            "articles": []
        }


def save_news(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("news.json saved successfully.")
    print("Total articles:", len(data.get("articles", [])))


def make_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def clean_html(text):
    if not text:
        return ""

    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_rss_items(url):
    print("Reading RSS:", url)

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 DOP-News-24"
            }
        )

        response.raise_for_status()

        feed = feedparser.parse(response.content)

        print("RSS items found:", len(feed.entries))

        return feed.entries

    except Exception as e:
        print("RSS ERROR:", e)
        return []


def rewrite_with_ai(title, description, category):
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY not found.")
        return None

    prompt = f"""
তুমি DOP NEWS 24-এর বাংলা সংবাদ সম্পাদক।

ক্যাটাগরি: {category}

মূল সংবাদ শিরোনাম:
{title}

RSS থেকে পাওয়া সংক্ষিপ্ত তথ্য:
{description}

নির্দেশনা:
- বাংলায় নতুন করে সংবাদটি লিখবে।
- তথ্যের বাইরে কোনো ঘটনা, সংখ্যা, নাম, উদ্ধৃতি বা দাবি বানাবে না।
- মূল লেখার বাক্য কপি করবে না।
- 2 থেকে 4টি ছোট অনুচ্ছেদ লিখবে।
- রাজনৈতিক সংবাদ হলে সম্পূর্ণ নিরপেক্ষ ভাষা ব্যবহার করবে।
- কোনো ওয়েবসাইটের নাম লিখবে না।
- source URL লিখবে না।

শুধু JSON দেবে:
{{
  "title": "নতুন বাংলা শিরোনাম",
  "summary": "নতুনভাবে লেখা সংবাদ"
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
                    "additionalProperties": False
                }
            }
        }
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=90
        )

        print("OpenAI status:", response.status_code)

        if response.status_code != 200:
            print("OPENAI ERROR:")
            print(response.text[:2000])
            return None

        result = response.json()

        output_text = ""

        for output in result.get("output", []):
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        output_text += content.get("text", "")

        if not output_text:
            print("OpenAI returned no text.")
            return None

        parsed = json.loads(output_text)

        if not parsed.get("title") or not parsed.get("summary"):
            return None

        return parsed

    except Exception as e:
        print("AI ERROR:", e)
        return None


def fallback_article(title, description):
    """
    AI কাজ না করলেও যাতে সংবাদ ওয়েবসাইটে দেখা যায়।
    """

    description = clean_html(description)

    if not description:
        description = title

    return {
        "title": title.strip(),
        "summary": description.strip()
    }


def get_image(entry):
    try:
        media = entry.get("media_content")

        if media and isinstance(media, list):
            for item in media:
                if item.get("url"):
                    return item["url"]

        thumbnail = entry.get("media_thumbnail")

        if thumbnail and isinstance(thumbnail, list):
            if thumbnail[0].get("url"):
                return thumbnail[0]["url"]

    except Exception:
        pass

    return "https://picsum.photos/800/450"


def main():

    print("====================================")
    print("DOP NEWS 24 AUTO NEWS STARTED")
    print("====================================")

    data = load_news()

    old_articles = data.get("articles", [])

    existing_ids = set()

    for article in old_articles:
        if article.get("source_id"):
            existing_ids.add(article["source_id"])

    new_articles = []

    for category, feed_url in FEEDS.items():

        print("")
        print("CATEGORY:", category)

        entries = get_rss_items(feed_url)

        if not entries:
            print("No RSS entries for:", category)
            continue

        category_count = 0

        for entry in entries[:10]:

            if category_count >= MAX_PER_CATEGORY:
                break

            title = clean_html(
                entry.get("title", "")
            )

            description = clean_html(
                entry.get("summary", "")
            )

            link = entry.get("link", "")

            if not title:
                continue

            source_id = make_id(
                title + "|" + link
            )

            if source_id in existing_ids:
                print("Duplicate:", title)
                continue

            print("Processing:", title)

            # প্রথমে AI দিয়ে লিখবে
            ai_article = rewrite_with_ai(
                title,
                description,
                category
            )

            # AI কাজ করলে AI লেখা
            # না করলে RSS তথ্য দিয়ে fallback
            if ai_article:
                article_title = ai_article["title"]
                article_summary = ai_article["summary"]
                print("AI article created.")
            else:
                fallback = fallback_article(
                    title,
                    description
                )

                article_title = fallback["title"]
                article_summary = fallback["summary"]

                print("Fallback RSS article created.")

            article = {
                "id": make_id(
                    source_id + str(datetime.now())
                ),

                "source_id": source_id,

                "category": category,

                "title": article_title,

                "summary": article_summary,

                "image": get_image(entry),

                "published_at": datetime.now(
                    timezone.utc
                ).isoformat(),

                "source_url": link
            }

            new_articles.append(article)

            existing_ids.add(source_id)

            category_count += 1

            if len(new_articles) >= MAX_TOTAL:
                break

        if len(new_articles) >= MAX_TOTAL:
            break

    print("")
    print("New articles:", len(new_articles))

    # নতুন সংবাদ সামনে
    all_articles = new_articles + old_articles

    # সর্বোচ্চ 40টি
    all_articles = all_articles[:MAX_TOTAL]

    data["articles"] = all_articles

    save_news(data)

    print("")
    print("====================================")
    print("DOP NEWS 24 AUTO NEWS FINISHED")
    print("====================================")


if __name__ == "__main__":
    main()
