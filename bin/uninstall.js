#!/usr/bin/env node
/**
 * vibecheck uninstall
 *
 * Cleanly removes VibeCheck from a project:
 *   - Removes hooks from .claude/settings.json
 *   - Deletes .claude/hooks/vibecheck_*.py and .claude/hooks/lib/ VibeCheck files
 *   - Deletes .claude/commands/vibecheck*.md
 *   - Strips VibeCheck sections from CLAUDE.md
 *   - Removes from global registry if registered
 *   - Optionally removes .vibecheck/ data (--keep-data to preserve)
 */

import fs from "fs";
import path from "path";
import os from "os";
import readline from "readline";

const keepData = process.argv.includes("--keep-data");
const yes = process.argv.includes("--yes");

const cwd = process.cwd();
const claudeDir = path.join(cwd, ".claude");
const vgDir = path.join(cwd, ".vibecheck");

if (!fs.existsSync(vgDir)) {
  console.log("VibeCheck is not installed in this project.");
  process.exit(0);
}

console.log("\n🗑️  VibeCheck uninstall\n");
console.log(`  Project: ${cwd}`);
if (keepData) {
  console.log("  Mode: remove hooks/commands only (--keep-data: preserving .vibecheck/)");
} else {
  console.log("  Mode: full removal (use --keep-data to preserve findings history)");
}
console.log();

if (!yes) {
  const confirmed = await confirm("Continue? (y/N): ");
  if (!confirmed) {
    console.log("Aborted.");
    process.exit(0);
  }
  console.log();
}

let removed = [];
let skipped = [];

// 1. Remove hooks from .claude/settings.json
const localSettingsPath = path.join(claudeDir, "settings.json");
if (fs.existsSync(localSettingsPath)) {
  if (removeVibeCheckHooks(localSettingsPath)) {
    removed.push(".claude/settings.json (hooks removed)");
  }
}

// Also remove from global settings if present
const globalSettingsPath = path.join(os.homedir(), ".claude", "settings.json");
if (fs.existsSync(globalSettingsPath)) {
  if (removeVibeCheckHooks(globalSettingsPath)) {
    removed.push("~/.claude/settings.json (hooks removed)");
  }
}

// 2. Remove hook files
const hookFiles = ["vibecheck_stop.py", "vibecheck_session_start.py", "vibecheck_post_tool.py"];
const hooksDir = path.join(claudeDir, "hooks");
for (const f of hookFiles) {
  const p = path.join(hooksDir, f);
  if (fs.existsSync(p)) {
    fs.rmSync(p);
    removed.push(`.claude/hooks/${f}`);
  }
}

// Remove lib files installed by VibeCheck
const libFiles = [
  "store.py", "static_checks.py", "patterns.py", "guardrails.py",
  "project.py", "project_map.py", "file_selection.py", "integrations.py",
  "health_report.py", "ignore.py", "metrics.py", "context_extractor.py",
  "vg_display.py", "analyzer_direct.py", "telemetry.py",
];
const libDir = path.join(hooksDir, "lib");
if (fs.existsSync(libDir)) {
  for (const f of libFiles) {
    const p = path.join(libDir, f);
    if (fs.existsSync(p)) fs.rmSync(p);
  }
  // Remove lib dir if now empty (ignoring __pycache__)
  try {
    const remaining = fs.readdirSync(libDir).filter(f => f !== "__pycache__");
    if (remaining.length === 0) {
      fs.rmSync(libDir, { recursive: true });
      removed.push(".claude/hooks/lib/");
    } else {
      removed.push(".claude/hooks/lib/ (VibeCheck files removed, other files kept)");
    }
  } catch {}
}

// 3. Remove commands
const commandFiles = [
  "vibecheck.md", "vibecheck-detail.md", "vibecheck-resolve.md",
  "vibecheck-scan.md", "vibecheck-status.md", "vibecheck-report.md",
  "vibecheck-timeline.md",
];
const commandsDir = path.join(claudeDir, "commands");
for (const f of commandFiles) {
  const p = path.join(commandsDir, f);
  if (fs.existsSync(p)) {
    fs.rmSync(p);
    removed.push(`.claude/commands/${f}`);
  }
}

// 4. Strip VibeCheck sections from CLAUDE.md
const claudeMdPath = path.join(cwd, "CLAUDE.md");
if (fs.existsSync(claudeMdPath)) {
  if (stripClaudeMd(claudeMdPath)) {
    removed.push("CLAUDE.md (VibeCheck sections removed)");
  } else {
    skipped.push("CLAUDE.md (no VibeCheck sections found)");
  }
}

// 5. Remove from global registry
const registryPath = path.join(os.homedir(), ".vibecheck", "registry.json");
if (fs.existsSync(registryPath)) {
  try {
    const reg = JSON.parse(fs.readFileSync(registryPath, "utf8"));
    const projects = reg.projects || {};
    const before = Object.keys(projects).length;
    for (const [id, p] of Object.entries(projects)) {
      if (p.path === cwd) delete projects[id];
    }
    if (Object.keys(projects).length < before) {
      reg.projects = projects;
      fs.writeFileSync(registryPath, JSON.stringify(reg, null, 2));
      removed.push("~/.vibecheck/registry.json (project removed)");
    }
  } catch {}
}

// 6. Remove .vibecheck/ unless --keep-data
if (!keepData) {
  if (fs.existsSync(vgDir)) {
    fs.rmSync(vgDir, { recursive: true });
    removed.push(".vibecheck/");
  }
} else {
  skipped.push(".vibecheck/ (preserved — your findings history is intact)");
}

// Summary
console.log("Removed:");
for (const r of removed) console.log(`  ✓ ${r}`);
if (skipped.length > 0) {
  console.log("\nSkipped:");
  for (const s of skipped) console.log(`  — ${s}`);
}
console.log("\nVibeCheck uninstalled. Restart Claude Code to clear any cached session state.");
if (keepData) {
  console.log("Your findings are in .vibecheck/ if you ever want them back.");
}
console.log();


// ── Helpers ────────────────────────────────────────────────────────────────

function removeVibeCheckHooks(settingsPath) {
  try {
    const settings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
    const hooks = settings.hooks || {};
    let changed = false;

    for (const event of Object.keys(hooks)) {
      const before = hooks[event].length;
      hooks[event] = hooks[event].filter(entry => {
        const cmd = (entry.hooks || []).map(h => h.command || "").join(" ");
        return !cmd.includes("vibecheck");
      });
      if (hooks[event].length < before) changed = true;
      // Clean up empty event arrays
      if (hooks[event].length === 0) delete hooks[event];
    }

    if (changed) {
      settings.hooks = hooks;
      fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));
    }
    return changed;
  } catch {
    return false;
  }
}

function stripClaudeMd(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  // Remove the Context Capture section and VibeCheck section
  // These sections are bounded by the headers we wrote and the next ## header (or EOF)
  const markers = [
    /^## Context Capture — MANDATORY triggers[\s\S]*?(?=^## |\Z)/m,
    /^## VibeCheck \(active\)[\s\S]*?(?=^## |\Z)/m,
  ];

  let updated = content;
  let changed = false;
  for (const marker of markers) {
    const next = updated.replace(marker, "");
    if (next !== updated) {
      updated = next;
      changed = true;
    }
  }

  if (changed) {
    // Clean up multiple blank lines left behind
    updated = updated.replace(/\n{3,}/g, "\n\n").trimEnd() + "\n";
    fs.writeFileSync(filePath, updated);
  }
  return changed;
}

async function confirm(prompt) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(prompt, answer => {
      rl.close();
      resolve(answer.trim().toLowerCase() === "y");
    });
  });
}
