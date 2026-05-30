# BooxGen Blog Automations

Daily GitHub Actions automation for creating and publishing SEO blog posts to BooxGen WordPress.

## Schedule

Runs every day at **11:00 PM India time**.

GitHub Actions uses UTC, so the workflow cron is:

```yaml
30 17 * * *
```

## Required Secrets

Add these in GitHub:

`Settings -> Secrets and variables -> Actions -> New repository secret`

- `WP_URL`: `https://booxgen.tech`
- `WP_USERNAME`: WordPress username, for example `codex`
- `WP_APP_PASSWORD`: WordPress Application Password
- `OPENAI_API_KEY`: OpenAI API key

Optional repository variable:

- `OPENAI_MODEL`: default is `gpt-5-mini`
- `DRY_RUN`: set to `true` to create drafts instead of publishing

## What It Does

- Checks recent BooxGen posts to avoid duplicate topics.
- Builds a keyword brief before writing.
- Uses a primary focus keyword, related keywords, topic entities, and buyer questions.
- Follows Google Search Central people-first content and spam-policy guidance.
- Writes a publish-ready SEO blog aligned with BooxGen services.
- Adds Rank Math metadata: focus keyword, SEO title, SEO description, and pillar flag.
- Creates a branded featured image and uploads it to WordPress.
- Adds focus keyword in title, meta description, slug, intro, headings, content, and image alt text.
- Adds internal BooxGen links, external authoritative links, short paragraphs, TOC, FAQs, and CTA.
- Publishes the post and verifies the public URL.

## Manual Run

Open the workflow in GitHub Actions and click **Run workflow**.
