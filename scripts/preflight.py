import base64
import os
import sys

import requests


def error(title, message):
    print(f"::error title={title}::{message}")


wp_url = os.environ["WP_URL"].rstrip("/")
wp_username = os.environ["WP_USERNAME"]
wp_app_password = os.environ["WP_APP_PASSWORD"]
openai_key = os.environ["OPENAI_API_KEY"]
openai_model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

failed = False

token = base64.b64encode(f"{wp_username}:{wp_app_password}".encode()).decode()
try:
    response = requests.get(
        f"{wp_url}/wp-json/wp/v2/users/me",
        headers={"Authorization": f"Basic {token}"},
        timeout=30,
    )
    if response.status_code != 200:
        failed = True
        error("WordPress auth failed", f"WordPress returned HTTP {response.status_code}: {response.text[:250]}")
    else:
        user = response.json()
        print(f"WordPress auth OK for user: {user.get('slug') or user.get('name')}")
except Exception as exc:
    failed = True
    error("WordPress check failed", str(exc))

try:
    response = requests.get(
        f"https://api.openai.com/v1/models/{openai_model}",
        headers={"Authorization": f"Bearer {openai_key}"},
        timeout=30,
    )
    if response.status_code != 200:
        failed = True
        error("OpenAI model/key failed", f"OpenAI returned HTTP {response.status_code}: {response.text[:300]}")
    else:
        print(f"OpenAI access OK for model: {openai_model}")
except Exception as exc:
    failed = True
    error("OpenAI check failed", str(exc))

if failed:
    sys.exit(1)

print("Preflight passed.")
