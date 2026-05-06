#!/usr/bin/env node
/**
 * vibecheck doctor
 *
 * Checks whether VibeCheck is installed correctly in the current project.
 * Reports what's working, what's missing, and how to fix each issue.
 */

import fs from "fs";
import path from "path";
import os from "os";
import { execSync } from "child_process";

const cwd = process.cwd();
const claudeDir = path.join(cwd, ".claude");
const vgDir = path.join(cwd, ".vibecheck");
const hooksDir = path.join(claudeDir, "hooks");
const libDir = path.join(hooksDir, "lib");
const commandsDir = path.join(claudeDir, "commands");
const userSettingsPath = path.join(os.homedir(), ".claude", "settings.json");

let ok = 0, warn = 0, fail = 0;

function pass(msg) { ok++;   console.log(`  ✅ ${msg}`); }
function warning(msg, fix) { warn++; console.log(`  ⚠️  ${msg}`); if (fix) console.log(`     Fix: ${fix}`); }
function error(msg, fix)   { fail++; console.log(`  ❌ ${msg}`); if (fix) console.log(`     Fix: ${fix}`); }

console.log("\n🛡️  VibeCheck doctor\n");

// 1. Data directory
if (fs.existsSync(vgDir)) {
  pass(".vibecheck/ data directory exists");
} else {
  error(".vibecheck/ not found — VibeCheck not initialized", "npx vibecheck init");
}

// 2. Hook files
const hookFiles = [
  "vibecheck_stop.py",
  "vibecheck_session_start.py",
  "vibecheck_post_tool.py",
];
for (const f of hookFiles) {
  const p = path.join(hooksDir, f);
  if (fs.existsSync(p)) {
    pass(`.claude/hooks/${f}`);
  } else {
    error(`.claude/hooks/${f} missing`, "npx vibecheck update");
  }
}

// 3. Lib files (spot-check key ones)
const keyLibFiles = [
  "store.py", "static_checks.py", "patterns.py", "telemetry.py",
  "detection_engine.py", "capability.py", "async_detection.py",
];
const missingLib = keyLibFiles.filter(f => !fs.existsSync(path.join(libDir, f)));
if (missingLib.length === 0) {
  pass(".claude/hooks/lib/ — all key lib files present");
} else {
  error(`.claude/hooks/lib/ — missing: ${missingLib.join(", ")}`, "npx vibecheck update");
}

// 4. Command files
const allCommands = [
  "vibecheck.md", "vibecheck-detail.md", "vibecheck-resolve.md",
  "vibecheck-scan.md", "vibecheck-status.md", "vibecheck-report.md",
  "vibecheck-timeline.md", "vibecheck-skills.md", "vibecheck-promote-skill.md",
  "vibecheck-model.md",
];
const missingCmds = allCommands.filter(f => !fs.existsSync(path.join(commandsDir, f)));
if (missingCmds.length === 0) {
  pass(".claude/commands/ — all command files present");
} else {
  error(`.claude/commands/ — missing: ${missingCmds.join(", ")}`, "npx vibecheck update");
}

// 5. Global hooks in ~/.claude/settings.json
if (fs.existsSync(userSettingsPath)) {
  try {
    const settings = JSON.parse(fs.readFileSync(userSettingsPath, "utf8"));
    const hooks = settings.hooks || {};
    const hasStop  = (hooks.Stop || []).some(h => JSON.stringify(h).includes("vibecheck_stop"));
    const hasStart = (hooks.SessionStart || []).some(h => JSON.stringify(h).includes("vibecheck_session_start"));
    const hasPost  = (hooks.PostToolUse || []).some(h => JSON.stringify(h).includes("vibecheck_post_tool"));

    if (hasStop && hasStart && hasPost) {
      pass("~/.claude/settings.json — all 3 hooks registered (Stop, SessionStart, PostToolUse)");
    } else {
      const missing = [
        !hasStop  ? "Stop"         : null,
        !hasStart ? "SessionStart" : null,
        !hasPost  ? "PostToolUse"  : null,
      ].filter(Boolean);
      error(`~/.claude/settings.json — missing hooks: ${missing.join(", ")}`, "npx vibecheck update  (or re-run init)");
    }
  } catch {
    warning("~/.claude/settings.json exists but could not be parsed", "Check for JSON syntax errors");
  }
} else {
  error("~/.claude/settings.json not found — hooks won't fire", "npx vibecheck init  (or re-run init)");
}

// 6. CLAUDE.md
const claudeMdPath = path.join(cwd, "CLAUDE.md");
if (fs.existsSync(claudeMdPath)) {
  const content = fs.readFileSync(claudeMdPath, "utf8");
  if (content.includes("VibeCheck (active)")) {
    pass("CLAUDE.md — VibeCheck section present");
  } else {
    warning("CLAUDE.md exists but VibeCheck section not found",
      "Run init again, or manually add the VibeCheck block from CLAUDE.template.md");
  }
} else {
  warning("CLAUDE.md not found", "Run npx vibecheck init to create it");
}

// 7. Python 3
try {
  const ver = execSync("python3 --version 2>&1", { encoding: "utf8" }).trim();
  pass(`Python 3 available — ${ver}`);
} catch {
  error("python3 not found in PATH", "Install Python 3.8+ and ensure it's in PATH");
}

// 8. Capability tier (Basic / Enhanced / Pro)
function shellHas(cmd) {
  try { execSync(`which ${cmd} 2>/dev/null`, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }); return true; }
  catch { return false; }
}
const hasSemgrep  = shellHas("semgrep");
const hasGitleaks = shellHas("gitleaks");
const hasGraphify = fs.existsSync(path.join(cwd, "graphify-out", "graph.json"));
const tier = (hasSemgrep && (hasGitleaks || hasGraphify)) ? "pro"
           : hasSemgrep ? "enhanced"
           : "basic";
const tierIcon = tier === "basic" ? "⚠️ " : "✅";
console.log(`  ${tierIcon} Capability tier: ${tier.toUpperCase()} — ${
  tier === "basic"    ? "regex only (zero deps)" :
  tier === "enhanced" ? "regex + Semgrep AST analysis" :
                        "regex + Semgrep + Gitleaks/Graphify"
}`);
if (!hasSemgrep)  console.log("     → Install Semgrep for Enhanced tier: pip install semgrep");
if (hasSemgrep && !hasGitleaks && !hasGraphify)
  console.log("     → Install Gitleaks for Pro tier: brew install gitleaks");

// 9. findings.json readable
const findingsPath = path.join(vgDir, "findings.json");
if (fs.existsSync(findingsPath)) {
  try {
    const findings = JSON.parse(fs.readFileSync(findingsPath, "utf8"));
    const open = (Array.isArray(findings) ? findings : findings.findings || [])
      .filter(f => f.status === "open").length;
    pass(`findings.json — ${open} open finding(s)`);
  } catch {
    warning("findings.json exists but has invalid JSON", "Delete .vibecheck/findings.json to reset");
  }
} else if (fs.existsSync(vgDir)) {
  pass("findings.json — not yet created (no findings)");
}

// Summary
console.log();
const total = ok + warn + fail;
if (fail === 0 && warn === 0) {
  console.log(`✅ All ${total} checks passed — VibeCheck is healthy.`);
} else if (fail === 0) {
  console.log(`⚠️  ${ok}/${total} checks passed, ${warn} warning(s). Run \`npx vibecheck update\` if unsure.`);
} else {
  console.log(`❌ ${fail} check(s) failed. Run \`npx vibecheck init\` to fix most issues.`);
}
console.log();
