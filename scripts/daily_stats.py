
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

# GitHub account
username = os.environ["GITHUB_REPOSITORY_OWNER"]
token = os.environ["GH_TOKEN"]

# Korea time
today = datetime.now(
    ZoneInfo("Asia/Seoul")
).strftime("%Y-%m-%d")

# Only one file is updated
output = Path("activity/latest.md")
title = f"# Daily GitHub Snapshot — {today}"

# Avoid duplicate commits on the same day
if output.exists():
    old = output.read_text(encoding="utf-8")
    if old.startswith(title + "\n"):
        print("Already updated today.")
        raise SystemExit(0)

# Fetch real GitHub project statistics
repos = []
page = 1

while True:
    url = (
        f"https://api.github.com/users/{username}/repos"
        f"?type=owner&per_page=100&page={page}"
    )

    request = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Daily-GitHub-Snapshot"
    })

    with urlopen(request, timeout=30) as response:
        batch = json.load(response)

    repos.extend(batch)

    if len(batch) < 100:
        break

    page += 1

stars = sum(r["stargazers_count"] for r in repos)
forks = sum(r["forks_count"] for r in repos)

content = [
    title,
    "",
    f"Date: {today} (KST)",
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

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    "\n".join(content) + "\n",
    encoding="utf-8"
)

print("Daily snapshot updated successfully.")
