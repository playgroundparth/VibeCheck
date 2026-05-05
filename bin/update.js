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

// Update framework files
const frameworkFiles = [
  "event-driven.md", "irreversible-action.md", "billing-pricing.md",
  "async-scheduled.md", "concurrent-state.md", "cross-cutting-state.md",
  "external-service.md", "new-dependency.md", "ugc.md", "user-input.md",
];
const frameworksDir = path.join(libDir, "frameworks");
fs.mkdirSync(frameworksDir, { recursive: true });
for (const f of frameworkFiles) {
  const src = path.join(VIBECHECK_ROOT, "frameworks", f);
  const dst = path.join(frameworksDir, f);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dst);
    updated.push(`frameworks/${f}`);
  }
}

// Update integration skill templates
const skillTemplates = [
  "stripe.md", "supabase.md", "clerk.md", "prisma.md", "openai.md", "vercel.md",
];
const skillTemplatesDir = path.join(libDir, "skills");
fs.mkdirSync(skillTemplatesDir, { recursive: true });
for (const f of skillTemplates) {
  const src = path.join(VIBECHECK_ROOT, "lib", "skills", f);
  const dst = path.join(skillTemplatesDir, f);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dst);
    updated.push(`lib/skills/${f}`);
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
  "vibecheck.md", "vibecheck-resolve.md", "vibecheck-scan.md",
  "vibecheck-review.md", "vibecheck-stage.md",
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

// Update agent files
const agentFiles = [
  ["agents/scanner.md", "vibecheck-scanner.md"],
  ["agents/scanner-deep.md", "vibecheck-scanner-deep.md"],
];
const agentsDir = path.join(claudeDir, "agents");
fs.mkdirSync(agentsDir, { recursive: true });
for (const [src, dst] of agentFiles) {
  const srcPath = path.join(VIBECHECK_ROOT, src);
  const dstPath = path.join(agentsDir, dst);
  if (fs.existsSync(srcPath)) {
    fs.copyFileSync(srcPath, dstPath);
    updated.push(`agents/${dst}`);
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

// Ensure worktrees have commands symlinked
const worktreesBase = path.join(claudeDir, "worktrees");
if (fs.existsSync(worktreesBase)) {
  let linked = 0;
  for (const wt of fs.readdirSync(worktreesBase, { withFileTypes: true }).filter(d => d.isDirectory()).map(d => d.name)) {
    const wtClaudeDir = path.join(worktreesBase, wt, ".claude");
    if (!fs.existsSync(wtClaudeDir)) continue;
    const target = path.join(wtClaudeDir, "commands");
    if (fs.existsSync(target)) continue;
    try { fs.symlinkSync("../../../commands", target); linked++; } catch {}
  }
  if (linked > 0) console.log(`✓ Linked commands into ${linked} existing worktree(s)`);
}

console.log(`Updated ${updated.length} files in .claude/`);
console.log("\nNot touched: .vibecheck/ data, CLAUDE.md, settings.json\n");
console.log("Restart Claude Code to pick up the changes.");
console.log();
