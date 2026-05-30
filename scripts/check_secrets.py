import os
import sys


required = ["WP_URL", "WP_USERNAME", "WP_APP_PASSWORD", "OPENAI_API_KEY"]
missing = [name for name in required if not os.getenv(name)]

if missing:
    for name in missing:
        print(f"::error title=Missing GitHub Secret::{name} is not set or is empty.")
    print("Add the missing values in GitHub: Settings -> Secrets and variables -> Actions -> Repository secrets.")
    sys.exit(1)

print("All required secrets are present.")

