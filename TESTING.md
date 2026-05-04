# VibeGuard Test Plan — for your 199-file vibe-coded repo

This guide is for testing VibeGuard on a real repository. It assumes you're not a developer and walks through every step.

---

## Before you start

You should have:
- ✅ Claude Code installed and working (you can run `claude` in your terminal)
- ✅ Your project repo on your computer
- ✅ Node.js 18+ (check with `node --version`)
- ✅ Python 3.8+ (check with `python3 --version`)

If you don't have Node or Python, install them first.

---

## Step 1 — Open a terminal in your project

Open Terminal (Mac), Command Prompt (Windows), or your shell of choice.

`cd` into your project directory. For example:
```bash
cd ~/Code/my-vibe-coded-app
```

You should see your project files when you run `ls` (Mac/Linux) or `dir` (Windows).

---

## Step 2 — Install VibeGuard

For now, since this is pre-release, copy the entire `vibeguard/` folder to a known location (e.g., `~/Code/vibeguard/`).

Then from your project directory, run:
```bash
node ~/Code/vibeguard/bin/cli.js init
```

(When VibeGuard is published to npm later, this becomes `npx vibecheck init`.)

You'll see:
```
🛡️  VibeGuard init

🔗 Detected: graphify, openspec
   VibeGuard will use these for better context.

📊 Anonymous usage stats? (counts only, no code, no paths)
   This helps improve VibeGuard. Off by default. (y/N):
```

**My recommendation:** Type `n` for telemetry (you don't owe anyone data), and `y` for global registry (lets `vibeguard list` work later).

The output will look like:
```
✓ Project ID: git-3a4b5c6d7e8f
✓ Created .vibeguard/
✓ Created .vibeguard/config.json
✓ Installed lib → .claude/hooks/lib/
✓ Installed agents → .claude/agents/
✓ Installed skill → .claude/skills/vibeguard.md
✓ Installed hooks → .claude/hooks/
✓ Registered hooks in .claude/settings.json
✓ Updated CLAUDE.md
✓ Added .vibeguard/ to .gitignore
✓ Created .vibeguardignore (customize what to skip)
📚 Building lightweight project map...
   Indexed 199 source files (offline, no LLM)
✓ Registered in global registry

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ VibeGuard active in: my-vibe-coded-app
   Project ID: git-3a4b5c6d7e8f
   Integrations: graphify, openspec
...
```

If the indexing step says "indexed 199 files" — great, the project map worked.

If you see errors, send them to me before continuing.

---

## Step 3 — Customize what to ignore (optional, ~1 minute)

VibeGuard auto-ignores `node_modules/`, `dist/`, `.git/`, and other obvious junk.

Open `.vibeguardignore` (it was just created in your project root) and add anything you want to skip:

```
# Skip docs — usually not relevant for security analysis
docs/

# Skip auto-generated files
*.generated.ts

# Skip tests we wrote a long time ago and don't trust
legacy/tests/

# Skip but keep one specific file
!docs/architecture.md
```

Save the file.

---

## Step 4 — Run the one-time history scan

This analyzes your existing 199 files. **Cost: $0.05–$0.15** on Haiku (default).

```bash
node ~/Code/vibeguard/bin/cli.js scan
```

You'll see:
```
🔍 VibeGuard Scan — Cost Estimate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Source files found:  ~199
Files VibeGuard reads: ~20 (strategic sample, not all files)

Model:           Claude Haiku (fast, cheapest option)
Estimated cost:  ~$0.03–$0.10
Estimated time:  30–60 seconds

Run the scan? (yes/no):
```

Type `yes`.

After 30-60 seconds, you'll see a summary like:
```
VibeGuard scan complete.

Reviewed: ~20 files
Found: 3 critical · 2 pitfalls · 5 hygiene · 4 suggestions

Top finding: Stripe API key hardcoded in src/config.js
```

**This is your first signal that VibeGuard is working.**

---

## Step 5 — View the findings

Open Claude Code in your project directory:
```bash
claude
```

Once Claude is open, type:
```
/vg
```

You should see all findings grouped by severity, with quick wins at the top, plain-English explanations, and ready-to-paste fix prompts for each.

**Try one of the fix prompts.** Pick a quick win, copy the fix prompt, paste it into Claude. See if the fix is good.

---

## Step 6 — Open the health dashboard

Type in Claude:
```
/vg-report
```

You'll see:
```
📊 Health report updated: .vibeguard/health-report.html

Open it in your browser:
  macOS:   open .vibeguard/health-report.html
  ...
```

Open that file in your browser. You'll see the full dashboard with charts, project info, timeline, learned patterns, and all findings.

This is your "is VibeGuard giving me anything useful?" view. Browse it for 2 minutes.

---

## Step 7 — Use it normally for a week

Just code as usual with Claude. After every task, you'll see a one-liner like:
```
[VibeGuard] 🔴 1 critical · 💡 2 suggestions · /vg to review
```

**Don't try to clear all findings immediately.** That defeats the test. Just notice when VibeGuard catches things you wouldn't have thought of.

---

## How to know it's actually working

Run this command anytime to see real metrics:
```bash
node ~/Code/vibeguard/bin/cli.js status
```

You'll see:
```
🛡️  VibeGuard status

  Total cost:        $0.0234
  Last 7 days cost:  $0.0156 (8 analyses)
  Total analyses:    12
  Avg latency:       4200ms

  Findings created:  18
  Open:              11
  Resolved:          5  (28%)
  Dismissed (FP):    2  (11%)

  Tasks completed:   15
  /vg invocations:   7  (engagement: 47%)

Signals:
  ✓ Good signal: 28% of findings have been resolved. VibeCheck is surfacing things you act on.
  ✓ Last 7 days: $0.0156 across 8 analyses (~$0.0020/analysis).
```

### What the numbers mean — the honest interpretation

| Metric | Healthy range | What it means |
|---|---|---|
| **Resolution rate** (resolved / created) | >20% | Findings are real and actionable. Below 10% = noise. |
| **False positive rate** (dismissed / created) | <30% | Tool is calibrated. Above 40% = too noisy, switch to Sonnet. |
| **Engagement rate** (/vg invocations / tasks) | >20% | You're actually looking at findings. Below 10% = ignored. |
| **Avg latency** | <30s | Hook isn't timing out. >60s = serious problem. |
| **Cost per analysis** | <$0.005 (Haiku) | Reasonable. >$0.01 means analyzer is reading too much. |

### Red flags to watch for

- **`resolution_rate` below 10%** — findings aren't actionable. Either Haiku is too dumb or your repo confuses it. Try `/vg-model sonnet`.
- **`false_positive_rate` above 40%** — too much noise. Use `/vg-resolve <id> false positive` to mark them, the patterns will deprioritize over time.
- **`engagement_rate` below 5%** — you're ignoring findings. Either the summary line isn't visible (UX problem) or nothing is being flagged (working but silent).
- **`avg_analyzer_latency_ms` above 60000** — analyzer is timing out. May indicate the subprocess isn't completing properly. Check `.vibeguard/debug.log`.

### Debug mode

If something seems wrong, enable debug logging:
```bash
export VIBEGUARD_DEBUG=1
```
Then use Claude Code normally. Every hook fire writes to `.vibeguard/debug.log`. Check that file for what happened.

---

## Cost estimate for your specific repo

Based on 199 files / 236K words:

| Action | One-time cost | Notes |
|---|---|---|
| `init` | $0 | Pure local setup |
| Project map build | $0 | Regex-based, no LLM |
| `scan` (history scan) | $0.05–$0.15 | Strategic sample of ~20 files |

| Daily usage | Range | Typical |
|---|---|---|
| Light coding (3-5 tasks/day) | $0.02–$0.08 | $0.04/day |
| Heavy coding (15-20 tasks/day) | $0.10–$0.30 | $0.20/day |
| With Sonnet (`/vg-model sonnet`) | 4-5x above | |

**Worst-case ceiling: $1/day on Haiku, $5/day on Sonnet.** If you're seeing higher than that, something's wrong — check `vibeguard status` and the debug log.

---

## What to send me after a week

After 5-7 days of real use, share:

1. **The output of `vibeguard status`** — tells us if metrics look healthy
2. **The contents of `.vibeguard/findings.json`** — let's see what got flagged
3. **3 examples** — pick:
   - One finding that was genuinely useful (caught something you didn't know)
   - One finding that was wrong/noise (false positive)
   - One thing VibeGuard MISSED that should have been flagged
4. **The debug log if anything seemed broken** — `.vibeguard/debug.log`

That's it. Don't pre-clean anything. Real usage data is what we need.

---

## Troubleshooting

**"VibeGuard hasn't run yet" after multiple tasks**

The hooks may not be firing. Check `.claude/settings.json` has the hooks registered. Try `export VIBEGUARD_DEBUG=1` and watch `.vibeguard/debug.log`.

**Subprocess errors / "claude command not found"**

The async analyzer subprocess uses `claude -p`. Make sure the `claude` command works in a normal terminal. If you're using a wrapper or alias, the subprocess won't find it.

**Lock file stuck**

If `.vibeguard/analysis.lock` exists for >2 minutes, it gets auto-cleared. If you see this often, the analyzer is timing out (60s limit). Check the debug log.

**Wildly high cost**

Run `vibeguard status` immediately. If `last_7_days_cost` is unexpected, check the timeline (`/vg-timeline`) for what's been running. The most likely cause is the analyzer running on every tiny file change. We can tune the trigger threshold.

**False positive avalanche**

If VibeGuard flags 20 things in one task, something's miscalibrated. Use `/vg-resolve <id> false positive` to mark each one — the patterns will deprioritize. If it's overwhelming, edit `.vibeguardignore` to add the directory it's getting confused by.
