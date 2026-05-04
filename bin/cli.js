#!/usr/bin/env node
import { fileURLToPath } from "url";
import { execSync } from "child_process";
import path from "path";
import fs from "fs";
import os from "os";

const command = process.argv[2];
const flags = process.argv.slice(3);

if (!command || command === "init") {
  await import("./init.js");
} else if (command === "uninstall") {
  await import("./uninstall.js");
} else if (command === "update") {
  await import("./update.js");
} else if (command === "scan") {
  await import("./scan.js");
} else if (command === "doctor") {
  await import("./doctor.js");
} else if (command === "list") {
  showProjectList(flags.includes("--prune"));
} else if (command === "status") {
  showStatus();
} else if (command === "--version" || command === "-v") {
  const pkg = JSON.parse(
    fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "package.json"), "utf8")
  );
  console.log(pkg.version);
} else {
  showHelp();
}

function showHelp() {
  console.log(`
VibeCheck — background safety agent for vibe coders

Setup:
  npx vibecheck init              Set up VibeCheck in this project
  npx vibecheck update            Update hooks and lib to latest version
  npx vibecheck uninstall         Remove VibeCheck from this project
  npx vibecheck uninstall --keep-data   Remove hooks but keep .vibecheck/ findings
  npx vibecheck scan              Scan existing codebase for risks
  npx vibecheck doctor            Check installation health
  npx vibecheck status            Show health metrics for this project

Multi-project (if global registry enabled):
  npx vibecheck list              List all VibeCheck projects
  npx vibecheck list --prune      Remove projects whose path no longer exists

Inside Claude Code:
  /vibecheck                   See findings with fix prompts
  /vibecheck-detail [id]       Full detail on one finding
  /vibecheck-resolve [id]      Mark a finding as resolved
  /vibecheck-scan              Scan from within Claude Code
  /vibecheck-report            Open health dashboard in browser
  /vibecheck-timeline          Activity log
  /vibecheck-status            Project health metrics
  /vibecheck-skills            Review proposed skills
  /vibecheck-promote-skill     Promote a proposed skill
  /vibecheck-model [model]     Switch model (haiku|sonnet)
`);
}

function showProjectList(prune) {
  const registryPath = path.join(os.homedir(), ".vibecheck", "registry.json");
  if (!fs.existsSync(registryPath)) {
    console.log("No projects registered. Enable global registry during `vibecheck init`.");
    return;
  }

  let data;
  try {
    data = JSON.parse(fs.readFileSync(registryPath, "utf8"));
  } catch (e) {
    console.error("Error reading registry:", e.message);
    return;
  }

  let projects = Object.values(data.projects || {});

  // Prune: remove projects whose path no longer exists OR no longer has .vibecheck/
  if (prune) {
    const initialCount = projects.length;
    const stillValid = {};
    let pruned = [];
    for (const p of projects) {
      const projectExists = p.path && fs.existsSync(p.path);
      const vgInstalled = projectExists && fs.existsSync(path.join(p.path, ".vibecheck"));
      if (projectExists && vgInstalled) {
        stillValid[p.id] = p;
      } else {
        pruned.push(p);
      }
    }
    if (pruned.length > 0) {
      data.projects = stillValid;
      try {
        fs.writeFileSync(registryPath, JSON.stringify(data, null, 2));
        console.log(`Pruned ${pruned.length} stale project${pruned.length === 1 ? '' : 's'}:\n`);
        for (const p of pruned) {
          const reason = !fs.existsSync(p.path) ? "path missing" : "VibeCheck uninstalled";
          console.log(`  ✗ ${p.name} (${reason})`);
          console.log(`     was: ${p.path}\n`);
        }
        projects = Object.values(stillValid);
      } catch (e) {
        console.error("Error writing registry:", e.message);
        return;
      }
    } else {
      console.log("All registered projects are still valid. Nothing to prune.\n");
    }
  }

  if (projects.length === 0) {
    console.log("No projects registered.");
    return;
  }

  projects.sort((a, b) => (b.last_seen || "").localeCompare(a.last_seen || ""));
  console.log("\nVibeCheck projects:\n");
  for (const p of projects) {
    const lastSeen = (p.last_seen || "").slice(0, 10);
    const exists = fs.existsSync(p.path) ? "" : " ⚠️ path missing";
    console.log(`  ${p.name.padEnd(30)} ${p.id.padEnd(20)} ${lastSeen}${exists}`);
    console.log(`  ${" ".repeat(30)} ${p.path}`);
  }
  console.log();
}

function showStatus() {
  const cwd = process.cwd();
  const vgDir = path.join(cwd, ".vibecheck");
  if (!fs.existsSync(vgDir)) {
    console.log("VibeCheck not initialized in this project.\n  Run: npx vibecheck init");
    return;
  }
  // Run Python to get the metrics summary
  try {
    const result = execSync(
      `PYTHONPATH=.claude/hooks/lib python3 -c "
import sys, json
sys.path.insert(0, '.claude/hooks/lib')
from pathlib import Path
import metrics
summary = metrics.get_summary(Path('.'))
signals = metrics.health_signals(Path('.'))
print(json.dumps({'summary': summary, 'signals': signals}, indent=2))
"`,
      { cwd, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }
    );
    const data = JSON.parse(result);
    printStatus(data);
  } catch (e) {
    console.error("Could not read metrics:", e.message);
  }
}

function printStatus(data) {
  const s = data.summary;
  const sig = data.signals;

  console.log("\n🛡️  VibeCheck status\n");

  console.log(`  — LLM analyzer runs (these cost money) —`);
  console.log(`  Total cost:        $${s.total_cost_usd.toFixed(4)}`);
  console.log(`  Last 7 days:       $${s.last_7_days_cost.toFixed(4)} across ${s.last_7_days_analyses} runs`);
  console.log(`  Total runs:        ${s.total_analyses}`);
  console.log(`  Avg latency:       ${s.avg_analyzer_latency_ms}ms\n`);

  console.log(`  — Findings —`);
  console.log(`  Created:           ${s.total_findings}`);
  console.log(`  Open:              ${s.open_findings}`);
  console.log(`  Resolved:          ${s.resolved}  (${(s.resolution_rate*100).toFixed(0)}%)`);
  console.log(`  Dismissed (FP):    ${s.dismissed}  (${(s.false_positive_rate*100).toFixed(0)}%)\n`);

  console.log(`  — Usage (free) —`);
  console.log(`  Tasks with edits:  ${s.tasks_completed}`);
  console.log(`  /vibecheck opened:        ${s.vg_invocations}  (engagement: ${(s.engagement_rate*100).toFixed(0)}%)\n`);

  if (Object.keys(sig).length > 0) {
    console.log("Signals:");
    for (const [key, msg] of Object.entries(sig)) {
      const icon = key.includes("warning") ? "⚠️ " : key.includes("signal") ? "✓ " : "  ";
      console.log(`  ${icon}${msg}`);
    }
    console.log();
  }
}
