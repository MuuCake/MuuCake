
name: Daily GitHub Project Snapshot

on:
  schedule:
    # 09:05 - 09:55 KST, every 5 minutes
    - cron: '5-55/5 0 * * *'

    # Backups: 12:17 and 18:17 KST
    - cron: '17 3,9 * * *'

  workflow_dispatch:

permissions:
  contents: write

# Prevent simultaneous commits
concurrency:
  group: daily-project-snapshot-main
  cancel-in-progress: false

jobs:
  daily-update:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      # Get latest main branch
      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          ref: main

      # Generate the real statistics
      - name: Update daily statistics
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python scripts/daily_stats.py

      # Verify the snapshot has today's UTC date
      - name: Verify UTC date
        shell: bash
        run: |
          set -euo pipefail

          TODAY="$(date -u +%Y-%m-%d)"

          grep -Fqx \
            "# Daily GitHub Snapshot — $TODAY" \
            activity/latest.md

          grep -Fqx \
            "Date: $TODAY (UTC)" \
            activity/latest.md

          echo "UTC date verified: $TODAY"

      # Commit and retry if a push conflicts
      - name: Commit daily update
        shell: bash
        env:
          COMMIT_EMAIL: ${{ vars.COMMIT_EMAIL }}
        run: |
          set -euo pipefail

          TODAY="$(date -u +%Y-%m-%d)"

          if [ -z "$COMMIT_EMAIL" ]; then
            echo "::error::COMMIT_EMAIL is missing"
            exit 1
          fi

          git config user.name "MuuCake"
          git config user.email "$COMMIT_EMAIL"

          git add activity/latest.md

          # Already updated today
          if git diff --cached --quiet; then
            echo "ALREADY_UPDATED: $TODAY"

            echo "### ✅ Already updated" >> "$GITHUB_STEP_SUMMARY"
            echo "- UTC date: $TODAY" >> "$GITHUB_STEP_SUMMARY"
            echo "- No new commit needed" >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi

          # Create today's commit
          git commit -m "docs: update daily GitHub stats"

          # Retry push at most 3 times
          for attempt in 1 2 3; do
            if git push origin HEAD:main; then
              echo "COMMITTED: $TODAY"

              echo "### ✅ Committed" >> "$GITHUB_STEP_SUMMARY"
              echo "- UTC date: $TODAY" >> "$GITHUB_STEP_SUMMARY"
              echo "- Commit: $(git rev-parse --short HEAD)" >> "$GITHUB_STEP_SUMMARY"
              exit 0
            fi

            if [ "$attempt" -eq 3 ]; then
              echo "::error::Push failed after 3 attempts"
              exit 1
            fi

            echo "Push failed. Retrying: $attempt"

            git fetch origin main
            git rebase FETCH_HEAD

            sleep $((attempt * 5))
          done

      # Show a clear failure summary
      - name: Report failure
        if: failure()
        shell: bash
        run: |
          echo "### ❌ Failed" >> "$GITHUB_STEP_SUMMARY"
          echo "- UTC date: $(date -u +%Y-%m-%d)" >> "$GITHUB_STEP_SUMMARY"
          echo "- Trigger: $GITHUB_EVENT_NAME" >> "$GITHUB_STEP_SUMMARY"
          echo "- Review the failed step logs" >> "$GITHUB_STEP_SUMMARY"
