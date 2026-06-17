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
const vcDir = path.join(cwd, ".vibecheck");

if (!fs.existsSync(vcDir)) {
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

  const appConfigs = [
    { name: "Claude Code", dir: ".claude", globalSettingsPath: path.join(os.homedir(), ".claude", "settings.json") },
    { name: "Antigravity/Gemini", dir: ".agents", globalSettingsPath: path.join(os.homedir(), ".gemini", "settings.json") },
    { name: "Codex", dir: ".codex", globalSettingsPath: path.join(os.homedir(), ".codex", "hooks.json") }
  ];

  for (const app of appConfigs) {
    const appDir = path.join(cwd, app.dir);
    if (!fs.existsSync(appDir)) continue;

    // 1. Remove hooks from local config if present
    const localSettingsPath = path.join(appDir, "settings.json");
    if (fs.existsSync(localSettingsPath)) {
      if (removeVibeCheckHooks(localSettingsPath)) {
        removed.push(`${app.dir}/settings.json (hooks removed)`);
      }
    }
    const localHooksPath = path.join(appDir, "hooks.json");
    if (fs.existsSync(localHooksPath)) {
      if (removeVibeCheckHooks(localHooksPath)) {
        removed.push(`${app.dir}/hooks.json (hooks removed)`);
      }
    }

    // Remove from global settings
    if (fs.existsSync(app.globalSettingsPath)) {
      if (removeVibeCheckHooks(app.globalSettingsPath)) {
        removed.push(`${app.globalSettingsPath.replace(os.homedir(), "~")} (hooks removed)`);
      }
    }

    // 2. Remove hook files
    const hookFiles = ["vibecheck_stop.py", "vibecheck_session_start.py", "vibecheck_post_tool.py"];
    const hooksDir = path.join(appDir, "hooks");
    for (const f of hookFiles) {
      const p = path.join(hooksDir, f);
      if (fs.existsSync(p)) {
        fs.rmSync(p);
        removed.push(`${app.dir}/hooks/${f}`);
      }
    }

    // Remove lib files
    const libFiles = [
      "store.py", "static_checks.py", "patterns.py", "guardrails.py",
      "project.py", "project_map.py", "health_report.py", "ignore.py",
      "metrics.py", "context_extractor.py", "vc_display.py", "telemetry.py",
      "graphify_query.py", "detection_engine.py", "capability.py", "async_detection.py",
    ];
    const libDir = path.join(hooksDir, "lib");
    if (fs.existsSync(libDir)) {
      for (const f of libFiles) {
        const p = path.join(libDir, f);
        if (fs.existsSync(p)) fs.rmSync(p);
      }
      // Remove skills/frameworks directory
      const skillTemplatesDir = path.join(libDir, "skills");
      if (fs.existsSync(skillTemplatesDir)) {
        fs.rmSync(skillTemplatesDir, { recursive: true });
      }
      const frameworksDir = path.join(libDir, "frameworks");
      if (fs.existsSync(frameworksDir)) {
        fs.rmSync(frameworksDir, { recursive: true });
      }
      // Remove lib dir if now empty (ignoring __pycache__)
      try {
        const remaining = fs.readdirSync(libDir).filter(f => f !== "__pycache__");
        if (remaining.length === 0) {
          fs.rmSync(libDir, { recursive: true });
          removed.push(`${app.dir}/hooks/lib/`);
        } else {
          removed.push(`${app.dir}/hooks/lib/ (VibeCheck files removed, other files kept)`);
        }
      } catch {}
    }

    // Remove auto-installed integration skills
    const skillsDir = path.join(appDir, "skills");
    if (fs.existsSync(skillsDir)) {
      try {
        const integrationSkills = fs.readdirSync(skillsDir).filter(f => f.startsWith("check-") && f.endsWith("-integration.md"));
        for (const f of integrationSkills) {
          fs.rmSync(path.join(skillsDir, f));
          removed.push(`${app.dir}/skills/${f}`);
        }
      } catch {}
    }

    // 3. Remove agents/prompts
    const agentsDir = path.join(appDir, "agents");
    if (fs.existsSync(agentsDir)) {
      const agentFiles = ["vibecheck-scanner.md", "vibecheck-scanner-deep.md", "vibecheck-scanner-opus.md"];
      for (const f of agentFiles) {
        const p = path.join(agentsDir, f);
        if (fs.existsSync(p)) {
          fs.rmSync(p);
          removed.push(`${app.dir}/agents/${f}`);
        }
      }
    }
    const promptsDir = path.join(appDir, "prompts");
    if (fs.existsSync(promptsDir)) {
      const agentFiles = ["vibecheck-scanner.md", "vibecheck-scanner-deep.md", "vibecheck-scanner-opus.md"];
      for (const f of agentFiles) {
        const p = path.join(promptsDir, f);
        if (fs.existsSync(p)) {
          fs.rmSync(p);
          removed.push(`${app.dir}/prompts/${f}`);
        }
      }
    }

    // 4. Remove commands
    const commandsDir = path.join(appDir, "commands");
    if (fs.existsSync(commandsDir)) {
      const commandFiles = [
        "vibecheck.md", "vibecheck-detail.md", "vibecheck-resolve.md", "vibecheck-scan.md",
        "vibecheck-review.md", "vibecheck-stage.md", "vibecheck-status.md", "vibecheck-report.md",
        "vibecheck-timeline.md", "vibecheck-skills.md", "vibecheck-promote-skill.md", "vibecheck-model.md",
        "vibecheck-help.md"
      ];
      for (const f of commandFiles) {
        const p = path.join(commandsDir, f);
        if (fs.existsSync(p)) {
          fs.rmSync(p);
          removed.push(`${app.dir}/commands/${f}`);
        }
      }
    }

    // 5. Remove launch.json
    const launchPath = path.join(appDir, "launch.json");
    if (fs.existsSync(launchPath)) {
      try {
        const launch = JSON.parse(fs.readFileSync(launchPath, "utf8"));
        const before = (launch.configurations || []).length;
        launch.configurations = (launch.configurations || []).filter(c => c.name !== "vibecheck-report");
        if (launch.configurations.length < before) {
          if (launch.configurations.length === 0) {
            fs.rmSync(launchPath);
            removed.push(`${app.dir}/launch.json (removed — was only vibecheck-report)`);
          } else {
            fs.writeFileSync(launchPath, JSON.stringify(launch, null, 2));
            removed.push(`${app.dir}/launch.json (vibecheck-report entry removed)`);
          }
        }
      } catch {}
    }

    // Clean up parent directory if empty
    try {
      const remaining = fs.readdirSync(appDir);
      if (remaining.length === 0) {
        fs.rmdirSync(appDir);
        removed.push(`${app.dir}/ (directory removed)`);
      }
    } catch {}
  }

// 6. Strip VibeCheck sections from CLAUDE.md
const claudeMdPath = path.join(cwd, "CLAUDE.md");
if (fs.existsSync(claudeMdPath)) {
  if (stripClaudeMd(claudeMdPath)) {
    removed.push("CLAUDE.md (VibeCheck sections removed)");
  } else {
    skipped.push("CLAUDE.md (no VibeCheck sections found)");
  }
}

// 7. Remove from global registry
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

// 8. Remove .vibecheck/ unless --keep-data
if (!keepData) {
  if (fs.existsSync(vcDir)) {
    fs.rmSync(vcDir, { recursive: true });
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
