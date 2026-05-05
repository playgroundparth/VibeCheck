#!/usr/bin/env node
/**
 * vibecheck update
 *
 * Re-copies hooks, lib, and commands from the package into the project's
 * .claude/ directory. Safe to run anytime — never touches .vibecheck/ data,
 * CLAUDE.md, or settings.json.
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const VIBECHECK_ROOT = path.join(__dirname, "..");

const cwd = process.cwd();
const claudeDir = path.join(cwd, ".claude");
const vgDir = path.join(cwd, ".vibecheck");

if (!fs.existsSync(vgDir)) {
  console.log("VibeCheck is not installed in this project. Run: npx github:playgroundparth/VibeCheck init");
  process.exit(0);
}

if (!fs.existsSync(claudeDir)) {
  console.log("No .claude/ directory found. Something looks wrong — try reinstalling with `init`.");
  process.exit(1);
}

console.log("\n🔄 VibeCheck update\n");

let updated = [];

// Update lib files
const libFiles = [
  "store.py", "static_checks.py", "patterns.py", "guardrails.py",
  "project.py", "project_map.py", "health_report.py", "ignore.py",
  "metrics.py", "context_extractor.py", "vg_display.py", "telemetry.py",
];
const libDir = path.join(claudeDir, "hooks", "lib");
fs.mkdirSync(libDir, { recursive: true });
for (const f of libFiles) {
  const src = path.join(VIBECHECK_ROOT, "lib", f);
  const dst = path.join(libDir, f);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dst);
    updated.push(`lib/${f}`);
  }
}

// Update hook files
const hookFiles = [
  ["hooks/stop.py", "vibecheck_stop.py"],
  ["hooks/session_start.py", "vibecheck_session_start.py"],
  ["hooks/post_tool.py", "vibecheck_post_tool.py"],
];
const hooksDir = path.join(claudeDir, "hooks");
for (const [src, dst] of hookFiles) {
  const srcPath = path.join(VIBECHECK_ROOT, src);
  const dstPath = path.join(hooksDir, dst);
  if (fs.existsSync(srcPath)) {
    fs.copyFileSync(srcPath, dstPath);
    fs.chmodSync(dstPath, 0o755);
    updated.push(dst);
  }
}

// Update command files
const commandFiles = [
  "vibecheck.md", "vibecheck-detail.md", "vibecheck-resolve.md",
  "vibecheck-scan.md", "vibecheck-status.md", "vibecheck-report.md",
  "vibecheck-timeline.md", "vibecheck-skills.md", "vibecheck-promote-skill.md",
  "vibecheck-model.md", "vibecheck-review.md",
];
const commandsDir = path.join(claudeDir, "commands");
fs.mkdirSync(commandsDir, { recursive: true });
for (const f of commandFiles) {
  const src = path.join(VIBECHECK_ROOT, "commands", f);
  const dst = path.join(commandsDir, f);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dst);
    updated.push(`commands/${f}`);
  }
}

// Update skill file
const skillSrc = path.join(VIBECHECK_ROOT, "vibecheck.md");
const skillDst = path.join(claudeDir, "skills", "vibecheck.md");
if (fs.existsSync(skillSrc)) {
  fs.mkdirSync(path.dirname(skillDst), { recursive: true });
  fs.copyFileSync(skillSrc, skillDst);
  updated.push("skills/vibecheck.md");
}

console.log(`Updated ${updated.length} files in .claude/`);
console.log("\nNot touched: .vibecheck/ data, CLAUDE.md, settings.json\n");
console.log("Restart Claude Code to pick up the changes.");
console.log();
