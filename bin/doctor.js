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
const vgDir = path.join(cwd, ".vibecheck");

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

const apps = [
  {
    name: "Claude Code",
    dir: path.join(cwd, ".claude"),
    relDir: ".claude",
    globalSettingsPath: path.join(os.homedir(), ".claude", "settings.json"),
    globalSettingsLabel: "~/.claude/settings.json",
    hookKeys: ["Stop", "SessionStart", "PostToolUse"],
    hookSubstring: "vibecheck"
  },
  {
    name: "Antigravity/Gemini",
    dir: path.join(cwd, ".agents"),
    relDir: ".agents",
    globalSettingsPath: path.join(os.homedir(), ".gemini", "settings.json"),
    globalSettingsLabel: "~/.gemini/settings.json",
    hookKeys: ["SessionEnd", "SessionStart", "AfterTool"],
    hookSubstring: "vibecheck"
  },
  {
    name: "Codex",
    dir: path.join(cwd, ".codex"),
    relDir: ".codex",
    globalSettingsPath: path.join(os.homedir(), ".codex", "hooks.json"),
    globalSettingsLabel: "~/.codex/hooks.json",
    hookKeys: ["Stop", "SessionStart", "PostToolUse"],
    hookSubstring: "vibecheck"
  }
];

for (const app of apps) {
  console.log(`\n🔍 Checking ${app.name}...`);
  if (!fs.existsSync(app.dir)) {
    error(`${app.relDir}/ directory not found`, "npx vibecheck init");
    continue;
  }
  pass(`${app.relDir}/ directory exists`);

  // 2. Hook files
  const hookFiles = [
    "vibecheck_stop.py",
    "vibecheck_session_start.py",
    "vibecheck_post_tool.py",
  ];
  for (const f of hookFiles) {
    const p = path.join(app.dir, "hooks", f);
    if (fs.existsSync(p)) {
      pass(`${app.relDir}/hooks/${f} exists`);
    } else {
      error(`${app.relDir}/hooks/${f} missing`, "npx vibecheck update");
    }
  }

  // 3. Lib files (spot-check key ones)
  const keyLibFiles = [
    "store.py", "static_checks.py", "patterns.py", "telemetry.py",
    "detection_engine.py", "capability.py", "async_detection.py",
  ];
  const missingLib = keyLibFiles.filter(f => !fs.existsSync(path.join(app.dir, "hooks", "lib", f)));
  if (missingLib.length === 0) {
    pass(`${app.relDir}/hooks/lib/ — all key lib files present`);
  } else {
    error(`${app.relDir}/hooks/lib/ — missing: ${missingLib.join(", ")}`, "npx vibecheck update");
  }

  // 4. Command files
  const allCommands = [
    "vibecheck.md", "vibecheck-scan.md", "vibecheck-review.md",
    "vibecheck-skills.md", "vibecheck-help.md"
  ];
  const missingCmds = allCommands.filter(f => !fs.existsSync(path.join(app.dir, "commands", f)));
  if (missingCmds.length === 0) {
    pass(`${app.relDir}/commands/ — all command files present`);
  } else {
    error(`${app.relDir}/commands/ — missing: ${missingCmds.join(", ")}`, "npx vibecheck update");
  }

  // 5. Global hooks
  if (fs.existsSync(app.globalSettingsPath)) {
    try {
      const settings = JSON.parse(fs.readFileSync(app.globalSettingsPath, "utf8"));
      const hooks = settings.hooks || {};
      const checks = app.hookKeys.map(k => {
        return {
          key: k,
          ok: (hooks[k] || []).some(h => JSON.stringify(h).includes(app.hookSubstring))
        };
      });
      const missing = checks.filter(c => !c.ok).map(c => c.key);
      if (missing.length === 0) {
        pass(`${app.globalSettingsLabel} — all ${app.hookKeys.length} hooks registered (${app.hookKeys.join(", ")})`);
      } else {
        error(`${app.globalSettingsLabel} — missing hooks: ${missing.join(", ")}`, "npx vibecheck update (or re-run init)");
      }
    } catch {
      warning(`${app.globalSettingsLabel} exists but could not be parsed`, "Check for JSON syntax errors");
    }
  } else {
    error(`${app.globalSettingsLabel} not found — hooks won't fire`, "npx vibecheck init (or re-run init)");
  }
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
