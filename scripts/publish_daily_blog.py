import base64
import io
import json
import os
import random
import re
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import markdown
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from slugify import slugify


WP_URL = os.environ["WP_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

FOCUS_TOPICS = [
    {
        "service": "B2B lead generation",
        "keyword": "B2B Lead Generation Services",
        "angle": "how to build qualified pipeline without wasting sales time",
    },
    {
        "service": "SEO",
        "keyword": "SEO Services for B2B Companies",
        "angle": "how B2B brands turn search intent into demo and enquiry opportunities",
    },
    {
        "service": "website development",
        "keyword": "Website Development Services for Business",
        "angle": "how a faster conversion-focused website supports marketing ROI",
    },
    {
        "service": "LinkedIn handling",
        "keyword": "LinkedIn Marketing Services for B2B",
        "angle": "how founders and brands build trust with decision makers",
    },
    {
        "service": "account based marketing",
        "keyword": "Account Based Marketing Services",
        "angle": "how to target high-value accounts with personalized campaigns",
    },
    {
        "service": "Google and Meta ads",
        "keyword": "Google and Meta Ads Services",
        "angle": "how to combine demand capture and retargeting for better leads",
    },
    {
        "service": "content marketing",
        "keyword": "B2B Content Marketing Services",
        "angle": "how useful content builds trust before a sales call",
    },
    {
        "service": "branding identity",
        "keyword": "Branding Identity Services",
        "angle": "how better positioning and design increase trust and conversion",
    },
]


def wp_headers():
    token = base64.b64encode(f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def request_json(method, path, **kwargs):
    url = f"{WP_URL}/wp-json/{path.lstrip('/')}"
    response = requests.request(method, url, timeout=60, **kwargs)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"WordPress request failed: {method} {url} -> {response.status_code} {response.text[:500]}") from exc
    return response.json()


def get_existing_posts():
    posts = request_json(
        "GET",
        "wp/v2/posts?per_page=20&status=publish,draft,pending,private",
        headers=wp_headers(),
    )
    return [
        {
            "id": post["id"],
            "title": unescape(post["title"]["rendered"]),
            "slug": post["slug"],
            "link": post["link"],
        }
        for post in posts
    ]


def choose_topic(existing_posts):
    used = " ".join(post["title"].lower() + " " + post["slug"].lower() for post in existing_posts)
    available = [
        topic for topic in FOCUS_TOPICS
        if topic["keyword"].lower().replace(" ", "-") not in used
        and topic["service"].lower() not in used[:5000]
    ]
    return random.choice(available or FOCUS_TOPICS)


def fetch_google_update_context():
    urls = [
        "https://developers.google.com/search/blog/rss.xml",
        "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
        "https://developers.google.com/search/docs/essentials/spam-policies",
        "https://developers.google.com/search/docs/crawling-indexing/robots/intro",
    ]
    notes = []
    try:
        feed = requests.get(urls[0], timeout=20)
        if feed.ok:
            root = ET.fromstring(feed.text)
            items = root.findall(".//item")[:5]
            for item in items:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub = item.findtext("pubDate", "").strip()
                if title and link:
                    notes.append(f"- {title} ({pub}) {link}")
    except Exception as exc:
        notes.append(f"- Google Search Central RSS unavailable during this run: {exc}")
    notes.extend([
        "- Follow people-first helpful content guidance: make content useful, original, and satisfying for the intended audience.",
        "- Follow spam policies: avoid scaled low-value content, thin affiliate-like pages, keyword stuffing, doorway pages, cloaking, scraped content, and fake claims.",
        "- Follow indexing basics: avoid noindex on publishable posts, use crawlable links, canonical URLs, and descriptive titles/snippets.",
    ])
    return "\n".join(notes)


def call_openai(prompt):
    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "booxgen_blog_post",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "seo_title": {"type": "string"},
                        "meta_description": {"type": "string"},
                        "slug": {"type": "string"},
                        "focus_keyword": {"type": "string"},
                        "related_keywords": {"type": "array", "items": {"type": "string"}},
                        "entities": {"type": "array", "items": {"type": "string"}},
                        "category": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "excerpt": {"type": "string"},
                        "image_alt": {"type": "string"},
                        "markdown": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "seo_title",
                        "meta_description",
                        "slug",
                        "focus_keyword",
                        "related_keywords",
                        "entities",
                        "category",
                        "tags",
                        "excerpt",
                        "image_alt",
                        "markdown",
                    ],
                },
            }
        },
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"OpenAI request failed: HTTP {response.status_code} {response.text[:800]}") from exc
    data = response.json()
    text = data.get("output_text")
    if not text:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    chunks.append(content.get("text", ""))
        text = "".join(chunks)
    return json.loads(text)


def build_prompt(topic, existing_posts, google_context):
    existing_titles = "\n".join(f"- {post['title']} ({post['slug']})" for post in existing_posts[:12])
    return f"""
You are writing for BooxGen, a web development, branding, marketing, and B2B lead generation agency.

Create one publish-ready SEO blog post.

Topic:
- Service: {topic["service"]}
- Primary focus keyword: {topic["keyword"]}
- Angle: {topic["angle"]}

Avoid duplicating these existing posts:
{existing_titles}

Current Google/Search guidance context:
{google_context}

Rules:
- Write people-first content that follows Google Search Central guidance and spam policies.
- Do not keyword stuff, invent statistics, create doorway content, or write thin generic AI content.
- Include original value: examples, checklists, decision criteria, workflows, and service-specific advice.
- Make the content aligned with BooxGen services: Marketing, Development, Branding Identity, and B2B Service.
- Use the exact focus keyword near the beginning of the SEO title, meta description, slug, first paragraph, at least one H2/H3, image alt text, and naturally in the body.
- Target natural keyword density around 1 percent without awkward repetition.
- Include a manual Table of Contents after the intro.
- Include internal links in markdown to https://booxgen.tech/, https://booxgen.tech/about-us/, https://booxgen.tech/portfolio/, https://booxgen.tech/contact-us/, and https://booxgen.tech/blog/ where natural.
- Include 2-3 external dofollow markdown links to authoritative relevant resources, such as Google Search Central, HubSpot, Think with Google, or LinkedIn business resources.
- Use short paragraphs and clear H2/H3 sections.
- Include FAQs at the end.
- Include a clear CTA to contact BooxGen.
- Keep the article between 1600 and 2300 words.

Return only JSON matching the schema.
"""


def markdown_to_html(markdown_text):
    return markdown.markdown(
        markdown_text,
        extensions=["extra", "toc", "sane_lists"],
        output_format="html5",
    )


def create_featured_image(title, focus_keyword):
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), "#f8f2ea")
    draw = ImageDraw.Draw(image)
    red = "#c91f2e"
    black = "#161616"
    green = "#5c8f3a"
    beige = "#ead6c3"
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 66)
        sub_font = ImageFont.truetype("DejaVuSans.ttf", 34)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except OSError:
        title_font = sub_font = small_font = ImageFont.load_default()

    draw.rounded_rectangle((-120, -80, 520, 230), radius=120, fill=red)
    draw.rounded_rectangle((1150, 680, 1730, 1010), radius=150, fill=red)
    draw.rounded_rectangle((860, 180, 1280, 620), radius=28, fill="#ffffff", outline=beige, width=4)
    draw.rectangle((900, 500, 960, 620), fill=beige)
    draw.rectangle((990, 430, 1050, 620), fill="#e4b7a7")
    draw.rectangle((1080, 350, 1140, 620), fill="#e56b6f")
    draw.line((910, 470, 1018, 410, 1110, 320, 1235, 250), fill=green, width=12)
    draw.polygon([(1235, 250), (1208, 250), (1232, 220)], fill=green)

    for x, y in [(980, 210), (1110, 190), (1210, 310), (1010, 330), (1160, 420)]:
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), fill=red if x % 2 == 0 else black)
        draw.line((x, y, x + 80, y + 50), fill="#b99c8a", width=2)

    draw.text((90, 90), "BooxGen", fill="#ffffff", font=title_font)
    wrapped_title = textwrap.wrap(title, width=28)[:4]
    y = 300
    for line in wrapped_title:
        draw.text((90, y), line, fill=black, font=title_font)
        y += 78
    draw.text((95, y + 20), focus_keyword, fill=red, font=sub_font)
    draw.text((95, 790), "SEO | Development | Branding | B2B Growth", fill=black, font=small_font)

    output = io.BytesIO()
    image.save(output, "PNG", optimize=True)
    output.seek(0)
    return output.getvalue()


def upload_media(image_bytes, filename, alt_text):
    headers = wp_headers()
    headers.update({
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "image/png",
    })
    media = requests.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        headers=headers,
        data=image_bytes,
        timeout=120,
    )
    media.raise_for_status()
    media_json = media.json()
    update = requests.post(
        f"{WP_URL}/wp-json/wp/v2/media/{media_json['id']}",
        headers={**wp_headers(), "Content-Type": "application/json"},
        json={"alt_text": alt_text, "caption": alt_text},
        timeout=60,
    )
    update.raise_for_status()
    return media_json["id"], media_json["source_url"]


def ensure_term(endpoint, name):
    slug = slugify(name)
    existing = request_json("GET", f"wp/v2/{endpoint}?slug={slug}", headers=wp_headers())
    if existing:
        return existing[0]["id"]
    created = requests.post(
        f"{WP_URL}/wp-json/wp/v2/{endpoint}",
        headers={**wp_headers(), "Content-Type": "application/json"},
        json={"name": name, "slug": slug},
        timeout=60,
    )
    if created.status_code == 400:
        data = created.json()
        term_id = data.get("data", {}).get("term_id")
        if term_id:
            return term_id
    created.raise_for_status()
    return created.json()["id"]


def set_rank_math_meta(post_id, focus_keyword, seo_title, meta_description):
    payload = {
        "objectType": "post",
        "objectID": post_id,
        "meta": {
            "rank_math_focus_keyword": focus_keyword,
            "rank_math_title": seo_title,
            "rank_math_description": meta_description,
            "rank_math_pillar_content": "on",
        },
    }
    response = requests.post(
        f"{WP_URL}/wp-json/rankmath/v1/updateMeta",
        headers={**wp_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if response.status_code not in (200, 201):
        print(f"Rank Math update skipped: {response.status_code} {response.text[:300]}")


def publish_post(article, featured_media_id, media_url):
    category_id = ensure_term("categories", article["category"])
    tag_ids = [ensure_term("tags", tag) for tag in article["tags"][:8]]
    markdown_text = article["markdown"]
    if media_url not in markdown_text:
        paragraphs = markdown_text.split("\n\n")
        image_markdown = f"![{article['image_alt']}]({media_url})"
        insert_at = 2 if len(paragraphs) > 2 else 1
        paragraphs.insert(insert_at, image_markdown)
        markdown_text = "\n\n".join(paragraphs)
    html = markdown_to_html(markdown_text)
    slug = slugify(article["slug"] or article["focus_keyword"])
    existing = request_json(
        "GET",
        f"wp/v2/posts?slug={slug}&status=publish,draft,pending,private",
        headers=wp_headers(),
    )
    payload = {
        "title": article["title"],
        "slug": slug,
        "status": "draft" if DRY_RUN else "publish",
        "content": html,
        "excerpt": article["excerpt"],
        "featured_media": featured_media_id,
        "categories": [category_id],
        "tags": tag_ids,
    }
    if existing:
        post_id = existing[0]["id"]
        post = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
            headers={**wp_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    else:
        post = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            headers={**wp_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    post.raise_for_status()
    post_json = post.json()
    set_rank_math_meta(
        post_json["id"],
        article["focus_keyword"],
        article["seo_title"],
        article["meta_description"],
    )
    return post_json


def verify_post(url, focus_keyword):
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    checks = {
        "focus_keyword_present": focus_keyword.lower() in soup.get_text(" ").lower(),
        "has_image": bool(soup.find("img")),
        "has_internal_booxgen_links": "booxgen.tech/contact-us" in html or "booxgen.tech/about-us" in html,
        "has_external_links": any(
            a.get("href", "").startswith("https://") and "booxgen.tech" not in a.get("href", "")
            for a in soup.find_all("a")
        ),
    }
    return checks


def save_local_copy(article, post=None):
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}-{slugify(article['slug'])}.json"
    payload = {"article": article, "post": post}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main():
    existing_posts = get_existing_posts()
    topic = choose_topic(existing_posts)
    google_context = fetch_google_update_context()
    prompt = build_prompt(topic, existing_posts, google_context)
    article = call_openai(prompt)

    # Defensive normalization for Rank Math checks.
    article["focus_keyword"] = article["focus_keyword"] or topic["keyword"]
    if not article["seo_title"].lower().startswith(article["focus_keyword"].lower()):
        article["seo_title"] = f"{article['focus_keyword']}: {article['seo_title']}"
    article["slug"] = slugify(article["slug"] or article["focus_keyword"])
    if slugify(article["focus_keyword"]) not in article["slug"]:
        article["slug"] = slugify(article["focus_keyword"])
    if article["focus_keyword"].lower() not in article["meta_description"].lower():
        article["meta_description"] = f"{article['focus_keyword']} from BooxGen: {article['meta_description']}"
    if article["focus_keyword"].lower() not in article["image_alt"].lower():
        article["image_alt"] = f"{article['focus_keyword']} strategy by BooxGen"

    image_bytes = create_featured_image(article["title"], article["focus_keyword"])
    filename = f"{article['slug']}-featured.png"
    media_id, media_url = upload_media(image_bytes, filename, article["image_alt"])
    post = publish_post(article, media_id, media_url)
    checks = verify_post(post["link"], article["focus_keyword"])
    local_path = save_local_copy(article, post)

    print(json.dumps({
        "status": post["status"],
        "url": post["link"],
        "focus_keyword": article["focus_keyword"],
        "related_keywords": article["related_keywords"],
        "entities": article["entities"],
        "featured_image": media_url,
        "verification": checks,
        "local_copy": str(local_path),
    }, indent=2))


if __name__ == "__main__":
    main()
