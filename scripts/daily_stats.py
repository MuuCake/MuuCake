
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

# GitHub account
username = os.environ["GITHUB_REPOSITORY_OWNER"]
token = os.environ["GH_TOKEN"]

# Use UTC date for GitHub contribution tracking
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Always update the same file
output = Path("activity/latest.md")
title = f"# Daily GitHub Snapshot — {today}"

# Avoid duplicate updates on the same UTC day
if output.exists():
    old = output.read_text(encoding="utf-8")

    if (
        old.startswith(title + "\n")
        and f"Date: {today} (UTC)" in old
    ):
        print("Already updated today (UTC).")
        raise SystemExit(0)

# Fetch real GitHub project statistics
repos = []
page = 1

while True:
    url = (
        f"https://api.github.com/users/{username}/repos"
        f"?type=owner&per_page=100&page={page}"
    )

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Daily-GitHub-Snapshot"
        }
    )

    with urlopen(request, timeout=30) as response:
        batch = json.load(response)

    if not isinstance(batch, list):
        raise RuntimeError("Invalid GitHub API response.")

    repos.extend(batch)

    if len(batch) < 100:
        break

    page += 1

# Calculate statistics
stars = sum(r["stargazers_count"] for r in repos)
forks = sum(r["forks_count"] for r in repos)

# Prepare Markdown content
content = [
    title,
    "",
    f"Date: {today} (UTC)",
    "",
    f"- Public repositories: {len(repos)}",
    f"- Total stars: {stars}",
    f"- Total forks: {forks}",
    "",
    "## Recently Updated Projects",
    ""
]

recent = sorted(
    repos,
    key=lambda r: r.get("pushed_at") or "",
    reverse=True
)

for repo in recent[:5]:
    content.append(
        f"- [{repo['name']}]({repo['html_url']})"
        f" — {repo['stargazers_count']} stars"
    )

# Update existing snapshot file
output.parent.mkdir(parents=True, exist_ok=True)

output.write_text(
    "\n".join(content) + "\n",
    encoding="utf-8"
)

print(f"Daily snapshot updated for {today} (UTC).")
