"""Read-only audit: compare a daily snapshot commit with counted profile contributions."""
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "MuuCake/MuuCake")
OWNER = REPOSITORY.split("/", 1)[0]
TOKEN = os.environ["GH_TOKEN"]
TARGET = date.fromisoformat(
    os.environ.get("TARGET_DAY") or
    (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
)
START = datetime.combine(TARGET, time.min, timezone.utc)
END = START + timedelta(days=1)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def github_json(path, payload=None):
    url = "https://api.github.com/" + path.lstrip("/")
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MuuCake-Contribution-Verification",
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {details}") from exc


def report(status, detail, sha="", total=0, repo_count=0):
    commit_label = (
        f"[{sha[:10]}](https://github.com/{REPOSITORY}/commit/{sha})"
        if sha else "not found"
    )
    text = (
        f"### {status} — {TARGET} UTC\n"
        f"- Daily statistics commit: {commit_label}\n"
        f"- Profile contributions that day: {total}\n"
        f"- Counted commits from {REPOSITORY}: {repo_count}\n"
        f"- Result: {detail}\n"
    )
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(text)


def find_snapshot_commit():
    for page in range(1, 21):
        query = urlencode({
            "sha": "main", "since": iso(START), "until": iso(END),
            "per_page": 100, "page": page,
        })
        batch = github_json(f"repos/{REPOSITORY}/commits?{query}")
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected commits API result")
        for entry in batch:
            data = entry["commit"]
            subject = data["message"].splitlines()[0]
            authored = datetime.fromisoformat(
                data["author"]["date"].replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            if subject != "docs: update daily GitHub stats":
                continue
            if authored.date() != TARGET:
                continue
            if (entry.get("author") or {}).get("login", "").lower() != OWNER.lower():
                report("❌ Incorrect author attribution",
                       "Commit author is not linked to the profile", entry["sha"])
                return None, True
            return (entry["sha"], authored), False
        if len(batch) < 100:
            break
    return None, False


def counted_contributions():
    query = """query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar { weeks { contributionDays { date contributionCount } } }
          commitContributionsByRepository(maxRepositories:100) {
            repository { nameWithOwner }
            contributions(first:50) { nodes { occurredAt commitCount } }
          }
        }
      }
    }"""
    answer = github_json("graphql", {
        "query": query,
        "variables": {
            "login": OWNER,
            "from": iso(START),
            "to": iso(END - timedelta(seconds=1)),
        },
    })
    if answer.get("errors"):
        raise RuntimeError(f"GraphQL errors: {answer['errors']}")
    user = (answer.get("data") or {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user {OWNER} not found")
    collection = user["contributionsCollection"]
    days = [
        day for week in collection["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    total = next(
        (day["contributionCount"] for day in days if day["date"] == TARGET.isoformat()),
        0,
    )
    repo_count = 0
    for group in collection["commitContributionsByRepository"]:
        if group["repository"]["nameWithOwner"].lower() != REPOSITORY.lower():
            continue
        # GraphQL already limits this collection to the target day.
        # occurredAt is not reliably at midnight UTC.
        repo_count += sum(
            node["commitCount"] for node in group["contributions"]["nodes"]
        )
    return total, repo_count


def main():
    if TARGET > datetime.now(timezone.utc).date():
        raise ValueError("Target date cannot be in the future")

    repo = github_json(f"repos/{REPOSITORY}")
    if repo["fork"] or repo["default_branch"] != "main":
        report("❌ Ineligible branch/repository",
               "Default branch must be main and repository must not be a fork")
        return 1

    commit, invalid_author = find_snapshot_commit()
    if invalid_author:
        return 1
    if not commit:
        if datetime.now(timezone.utc) <= END:
            report("⏳ Awaiting daily commit", "UTC day has not ended yet")
            return 0
        report("❌ No daily snapshot commit",
               "No qualifying daily statistics commit found on main")
        return 1

    sha, committed_at = commit
    total, repo_count = counted_contributions()
    if repo_count > 0:
        report("✅ Counted by GitHub",
               "GitHub reports counted commits from this repository on the target date",
               sha, total, repo_count)
        return 0
    if datetime.now(timezone.utc) - committed_at < timedelta(hours=24):
        report("⏳ Waiting for GitHub sync",
               "Snapshot commit exists but profile may still be updating (<24 hours)",
               sha, total, repo_count)
        return 0
    report("❌ Contribution needs review",
           "Snapshot commit is over 24 hours old but GitHub reports no counted commits from this repository",
           sha, total, repo_count)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, RuntimeError, URLError) as exc:
        report("❌ Verification could not run", str(exc))
        sys.exit(1)
