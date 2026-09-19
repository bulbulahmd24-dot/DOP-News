import os
import json
import hashlib
from datetime import datetime, timezone

import requests
import feedparser


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

MODEL = "gpt-5.6-luna"

NEWS_FILE = "news.json"

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
            return json.load(f)
    except Exception:
        return {
            "updated_at": "",
            "articles": []
        }


def save_news(data):
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def article_id(title):
    return hashlib.sha256(
        title.strip().lower().encode("utf-8")
    ).hexdigest()[:16]


def rewrite_with_ai(category, title, description):
    url = "https://api.openai.com/v1/responses"

    prompt = f"""
তুমি DOP NEWS 24-এর একজন বাংলা সংবাদ সম্পাদক।

নিচের RSS সংবাদ তথ্য ব্যবহার করে সম্পূর্ণ নতুন ভাষায় একটি সংক্ষিপ্ত বাংলা সংবাদ তৈরি করো।

বিভাগ: {category}

মূল শিরোনাম:
{title}

মূল বিবরণ:
{description}

নিয়ম:
1. মূল লেখার বাক্য কপি করবে না।
2. বাক্য ধরে ধরে অনুবাদ বা paraphrase করবে না।
3. নিজের ভাষায় নতুনভাবে সংবাদটি লিখবে।
4. শুধু দেওয়া তথ্যের ভিত্তিতে লিখবে।
5. কোনো তথ্য বানিয়ে লিখবে না।
6. কোনো কাল্পনিক উদ্ধৃতি তৈরি করবে না।
7. রাজনৈতিক সংবাদ হলে নিরপেক্ষ ভাষা ব্যবহার করবে।
8. ১টি নতুন বাংলা শিরোনাম তৈরি করবে।
9. ২-৪টি ছোট অনুচ্ছেদে সংবাদ লিখবে।
10. সংবাদে কোনো ওয়েবসাইটের নাম, URL বা source link লিখবে না।

শুধু নিচের JSON format-এ উত্তর দাও:

{{
  "title": "নতুন বাংলা শিরোনাম",
  "summary": "সংবাদটির নতুনভাবে লেখা বাংলা বিবরণ"
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "input": prompt
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    result = response.json()

    text = result.get("output_text", "").strip()

    if not text:
        raise ValueError("AI কোনো লেখা ফেরত দেয়নি।")

    # যদি ```json ... ``` আসে, সেটি সরানো
    text = text.replace("```json", "")
    text = text.replace("```", "")
    text = text.strip()

    return json.loads(text)


def get_image(entry):
    try:
        if "media_content" in entry:
            media = entry["media_content"]

            if media and "url" in media[0]:
                return media[0]["url"]

        if "media_thumbnail" in entry:
            media = entry["media_thumbnail"]

            if media and "url" in media[0]:
                return media[0]["url"]

    except Exception:
        pass

    return "https://picsum.photos/900/500"


def main():

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY পাওয়া যায়নি। GitHub Secret সেট করুন।"
        )

    data = load_news()

    existing_ids = {
        article.get("source_id")
        for article in data.get("articles", [])
    }

    new_articles = []

    for category, feed_url in FEEDS.items():

        print(f"সংবাদ সংগ্রহ করা হচ্ছে: {category}")

        feed = feedparser.parse(feed_url)

        count = 0

        for entry in feed.entries[:10]:

            if count >= 5:
                break

            original_title = entry.get("title", "").strip()
            description = entry.get(
                "summary",
                entry.get("description", "")
            ).strip()

            if not original_title:
                continue

            source_id = article_id(original_title)

            if source_id in existing_ids:
                continue

            try:

                ai_article = rewrite_with_ai(
                    category,
                    original_title,
                    description
                )

                title = ai_article.get("title", "").strip()
                summary = ai_article.get("summary", "").strip()

                if not title or not summary:
                    continue

                article = {
                    "id": article_id(
                        title + datetime.now(timezone.utc).isoformat()
                    ),
                    "source_id": source_id,
                    "category": category,
                    "title": title,
                    "summary": summary,
                    "image": get_image(entry),
                    "published_at": datetime.now(
                        timezone.utc
                    ).isoformat()
                }

                new_articles.append(article)
                existing_ids.add(source_id)

                count += 1

                print("নতুন সংবাদ:", title)

            except Exception as e:
                print("AI processing error:", e)

    # নতুন সংবাদ সামনে রাখুন
    data["articles"] = (
        new_articles + data.get("articles", [])
    )

    # সর্বোচ্চ ৪০টি সংবাদ রাখুন
    data["articles"] = data["articles"][:40]

    data["updated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    save_news(data)

    print(
        f"সম্পন্ন। নতুন সংবাদ যোগ হয়েছে: {len(new_articles)}"
    )


if __name__ == "__main__":
    main()
