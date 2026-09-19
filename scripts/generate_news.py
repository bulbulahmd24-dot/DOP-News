import os
import json
import hashlib
from datetime import datetime, timezone

import requests
import feedparser


# =========================================================
# SETTINGS
# =========================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

MODEL = "gpt-5.6-luna"

NEWS_FILE = "news.json"

MAX_ARTICLES_PER_CATEGORY = 5
MAX_TOTAL_ARTICLES = 40


# =========================================================
# RSS FEEDS
# =========================================================

FEEDS = {
    "বাংলাদেশ": "https://news.google.com/rss/search?q=Bangladesh&hl=bn&gl=BD&ceid=BD:bn",
    "বিশ্ব": "https://news.google.com/rss/search?q=World+News&hl=en-US&gl=US&ceid=US:en",
    "খেলা": "https://news.google.com/rss/search?q=Sports&hl=en-US&gl=US&ceid=US:en",
    "প্রযুক্তি": "https://news.google.com/rss/search?q=Technology&hl=en-US&gl=US&ceid=US:en",
}


# =========================================================
# LOAD NEWS
# =========================================================

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
            raise ValueError("news.json format ভুল")

        if "articles" not in data:
            data["articles"] = []

        return data

    except Exception as e:

        print("news.json পড়তে সমস্যা:", e)

        return {
            "updated_at": "",
            "articles": []
        }


# =========================================================
# SAVE NEWS
# =========================================================

def save_news(data):

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


# =========================================================
# CREATE ID
# =========================================================

def article_id(text):

    return hashlib.sha256(
        text.strip().lower().encode("utf-8")
    ).hexdigest()[:16]


# =========================================================
# AI REWRITE
# =========================================================

def rewrite_with_ai(
    category,
    title,
    description
):

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY পাওয়া যায়নি।"
        )

    url = "https://api.openai.com/v1/responses"

    prompt = f"""
তুমি DOP NEWS 24-এর একজন পেশাদার বাংলা সংবাদ সম্পাদক।

তোমাকে একটি RSS সংবাদ শিরোনাম ও সংক্ষিপ্ত বিবরণ দেওয়া হচ্ছে।
এসব তথ্যের ভিত্তিতে সম্পূর্ণ নতুন ভাষায় একটি সংক্ষিপ্ত বাংলা সংবাদ তৈরি করো।

বিভাগ:
{category}

মূল শিরোনাম:
{title}

মূল বিবরণ:
{description}

কঠোর নিয়ম:

1. মূল লেখার কোনো বাক্য হুবহু কপি করবে না।
2. বাক্য ধরে ধরে অনুবাদ করবে না।
3. সম্পূর্ণ নতুন বাক্য ও সংবাদভাষা ব্যবহার করবে।
4. দেওয়া তথ্যের বাইরে কোনো তথ্য যোগ করবে না।
5. কোনো তথ্য অনুমান করে লিখবে না।
6. কাল্পনিক ব্যক্তি, সংখ্যা, ঘটনা বা উদ্ধৃতি তৈরি করবে না।
7. রাজনৈতিক সংবাদ হলে সম্পূর্ণ নিরপেক্ষ ভাষা ব্যবহার করবে।
8. নতুন ও স্বাভাবিক বাংলা শিরোনাম তৈরি করবে।
9. সংবাদটি ২ থেকে ৪টি ছোট অনুচ্ছেদে লিখবে।
10. ওয়েবসাইটের নাম, URL বা source link সংবাদে লিখবে না।
11. সংবাদটি তথ্যভিত্তিক ও সহজবোধ্য হবে।
12. অতিরঞ্জিত বা ক্লিকবেইট শিরোনাম ব্যবহার করবে না।

শুধু JSON format-এ উত্তর দাও।
"""


    headers = {
        "Authorization":
            f"Bearer {OPENAI_API_KEY}",

        "Content-Type":
            "application/json"
    }


    # Structured JSON output
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


    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120
    )


    # API error হলে বিস্তারিত দেখাবে
    if not response.ok:

        print(
            "OpenAI API Error:",
            response.status_code
        )

        print(
            response.text[:3000]
        )

        response.raise_for_status()


    result = response.json()


    # Responses API-এর output থেকে text বের করা
    text = ""


    for output_item in result.get(
        "output",
        []
    ):

        if output_item.get(
            "type"
        ) != "message":

            continue


        for content_item in output_item.get(
            "content",
            []
        ):

            if content_item.get(
                "type"
            ) == "output_text":

                text = content_item.get(
                    "text",
                    ""
                )

                break


        if text:
            break


    if not text:

        raise ValueError(
            "OpenAI কোনো output text ফেরত দেয়নি।"
        )


    text = text.strip()


    try:

        return json.loads(text)

    except json.JSONDecodeError:

        print(
            "AI response JSON ছিল না:"
        )

        print(text[:3000])

        raise


# =========================================================
# IMAGE
# =========================================================

def get_image(entry):

    try:

        media = entry.get(
            "media_content"
        )

        if media:

            for item in media:

                if item.get("url"):

                    return item["url"]


        thumbnail = entry.get(
            "media_thumbnail"
        )

        if thumbnail:

            for item in thumbnail:

                if item.get("url"):

                    return item["url"]


    except Exception as e:

        print(
            "Image পাওয়া যায়নি:",
            e
        )


    # fallback
    return "https://picsum.photos/900/500"


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print("=" * 60)
    print("DOP NEWS 24 - AI NEWS GENERATOR")
    print("=" * 60)
    print("")


    if not OPENAI_API_KEY:

        raise RuntimeError(
            "OPENAI_API_KEY পাওয়া যায়নি। "
            "GitHub Settings → Secrets and variables → Actions "
            "থেকে OPENAI_API_KEY সেট করুন।"
        )


    data = load_news()


    existing_ids = {

        article.get("source_id")

        for article in data.get(
            "articles",
            []
        )

        if article.get("source_id")
    }


    new_articles = []


    # =====================================================
    # EACH CATEGORY
    # =====================================================

    for category, feed_url in FEEDS.items():

        print("")
        print(
            f"সংবাদ সংগ্রহ করা হচ্ছে: {category}"
        )


        try:

            feed = feedparser.parse(
                feed_url
            )

        except Exception as e:

            print(
                "RSS Error:",
                e
            )

            continue


        if not feed.entries:

            print(
                "এই বিভাগে RSS সংবাদ পাওয়া যায়নি।"
            )

            continue


        count = 0


        # প্রতি category থেকে সর্বোচ্চ ১০টি source পরীক্ষা
        for entry in feed.entries[:10]:

            if count >= MAX_ARTICLES_PER_CATEGORY:

                break


            original_title = (
                entry.get(
                    "title",
                    ""
                )
                .strip()
            )


            description = (
                entry.get(
                    "summary",
                    entry.get(
                        "description",
                        ""
                    )
                )
                .strip()
            )


            if not original_title:

                continue


            source_id = article_id(
                original_title
            )


            # আগে নেওয়া সংবাদ বাদ
            if source_id in existing_ids:

                print(
                    "Duplicate বাদ:",
                    original_title
                )

                continue


            print(
                "AI দিয়ে তৈরি হচ্ছে:",
                original_title
            )


            try:

                ai_article = rewrite_with_ai(

                    category,

                    original_title,

                    description

                )


                title = (
                    ai_article
                    .get(
                        "title",
                        ""
                    )
                    .strip()
                )


                summary = (
                    ai_article
                    .get(
                        "summary",
                        ""
                    )
                    .strip()
                )


                if not title or not summary:

                    print(
                        "AI title/summary দেয়নি।"
                    )

                    continue


                now = datetime.now(
                    timezone.utc
                ).isoformat()


                article = {

                    "id": article_id(
                        title + now
                    ),

                    "source_id": source_id,

                    "category": category,

                    "title": title,

                    "summary": summary,

                    "image": get_image(
                        entry
                    ),

                    "published_at": now

                }


                new_articles.append(
                    article
                )


                existing_ids.add(
                    source_id
                )


                count += 1


                print(
                    "✅ নতুন সংবাদ:",
                    title
                )


            except Exception as e:

                print(
                    "❌ AI processing error:",
                    e
                )

                continue


    # =====================================================
    # SAVE
    # =====================================================

    old_articles = data.get(
        "articles",
        []
    )


    data["articles"] = (
        new_articles +
        old_articles
    )


    # সর্বোচ্চ ৪০টি সংবাদ
    data["articles"] = (
        data["articles"]
        [:MAX_TOTAL_ARTICLES]
    )


    data["updated_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )


    save_news(data)


    print("")
    print("=" * 60)

    print(
        "✅ কাজ সম্পন্ন"
    )

    print(
        f"নতুন সংবাদ যোগ হয়েছে: "
        f"{len(new_articles)}"
    )

    print(
        f"মোট সংবাদ: "
        f"{len(data['articles'])}"
    )

    print("=" * 60)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
