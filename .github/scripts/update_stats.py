#!/usr/bin/env python3
"""
Updates the {REPOS}/{COMMITS}/{LOC} lines inside the neofetch-style README
code block with live GitHub stats, keeping the dot-leader alignment intact.

Runs inside GitHub Actions. Requires env vars:
  GITHUB_TOKEN  - provided automatically by Actions
  GH_USERNAME   - the GitHub username (e.g. GraceyDugar)
"""

import json
import os
import re
import sys
import time
import urllib.request

USERNAME = os.environ.get("GH_USERNAME", "GraceyDugar")
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com"
INFO_W = 50  # must match the width used to generate the README block


def gh(url):
    """GET a GitHub API URL, returns (status, parsed_json)."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None


def get_all_repos():
    repos, page = [], 1
    while True:
        status, data = gh(f"{API}/users/{USERNAME}/repos?per_page=100&page={page}&type=owner")
        if status != 200 or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def get_contributor_stats(full_name):
    """Returns (commits, additions, deletions) for USERNAME in this repo.
    The stats endpoint returns 202 while GitHub computes stats; retry briefly."""
    url = f"{API}/repos/{full_name}/stats/contributors"
    for _ in range(5):
        status, data = gh(url)
        if status == 202:
            time.sleep(3)
            continue
        if status != 200 or not isinstance(data, list):
            return 0, 0, 0
        for contributor in data:
            author = (contributor.get("author") or {}).get("login", "")
            if author.lower() == USERNAME.lower():
                commits = contributor.get("total", 0)
                adds = sum(w.get("a", 0) for w in contributor.get("weeks", []))
                dels = sum(w.get("d", 0) for w in contributor.get("weeks", []))
                return commits, adds, dels
        return 0, 0, 0
    return 0, 0, 0


def contributed_repo_count():
    """Repos (not owned) where the user has merged PRs, for the {Contributed: N} touch."""
    status, data = gh(
        f"{API}/search/issues?q=author:{USERNAME}+type:pr+is:merged&per_page=1"
    )
    if status == 200 and data:
        return data.get("total_count", 0)
    return 0


def leader(label, value, width=INFO_W):
    dots = width - len(label) - len(value) - 2
    if dots < 1:
        return f"{label}: {value}"
    return f"{label}: {'.' * dots} {value}"


def rewrite_readme(path, repos_v, commits_v, loc_v):
    text = open(path, encoding="utf-8").read()

    replacements = {
        "Repos": repos_v,
        "Commits": commits_v,
        "Lines of Code": loc_v,
    }
    for label, value in replacements.items():
        # Match the stat line: leading whitespace + "Label: ....... old-value"
        pattern = re.compile(rf"^([ ]*){re.escape(label)}: \.+ .*$", re.MULTILINE)
        text, n = pattern.subn(lambda m: m.group(1) + leader(label, value), text, count=1)
        if n == 0:
            print(f"warning: line for '{label}' not found in README", file=sys.stderr)

    open(path, "w", encoding="utf-8").write(text)


def main():
    readme = sys.argv[1] if len(sys.argv) > 1 else "README.md"

    repos = get_all_repos()
    repo_count = len(repos)

    total_commits = total_add = total_del = 0
    for r in repos:
        if r.get("fork"):
            continue  # skip forks; drop this line if you want them counted
        c, a, d = get_contributor_stats(r["full_name"])
        total_commits += c
        total_add += a
        total_del += d

    contributed = contributed_repo_count()
    loc = total_add - total_del

    repos_v = f"{repo_count} {{Contributed: {contributed}}}"
    commits_v = f"{total_commits:,}"
    loc_v = f"{loc:,} ({total_add:,}++, {total_del:,}--)"

    print(f"Repos: {repos_v} | Commits: {commits_v} | LOC: {loc_v}")
    rewrite_readme(readme, repos_v, commits_v, loc_v)
    print("README updated.")


if __name__ == "__main__":
    main()
