#!/usr/bin/env node
/**
 * vibeguard init
 */

import fs from "fs";
import path from "path";
import os from "os";
import { execSync } from "child_process";
import { fileURLToPath } from "url";
import readline from "readline";
import crypto from "crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const VIBEGUARD_ROOT = path.join(__dirname, "..");

async function main() {
  console.log("\n🛡️  VibeCheck init\n");

  const cwd = process.cwd();
  const hasClaudeDir = fs.existsSync(path.join(cwd, ".claude"));
  const hasClaudeMd = fs.existsSync(path.join(cwd, "CLAUDE.md"));

  if (!hasClaudeDir && !hasClaudeMd) {
    console.warn(
      "⚠️  No .claude/ or CLAUDE.md found. VibeCheck works best inside Claude Code.\n" +
      "   Continuing — will create .claude/ for you.\n"
    );
  }

  // Detect existing tools
  const integrations = detectIntegrations(cwd);
  if (integrations.length > 0) {
    console.log(`🔗 Detected: ${integrations.join(", ")}`);
    console.log("   VibeCheck will use these for better context.\n");
  }

  const nonInteractive = process.argv.includes("--yes") || !process.stdin.isTTY;

  // Telemetry opt-in
  const telemetry = nonInteractive ? false : await askYesNo(
    "📊 Anonymous usage stats? (counts only, no code, no paths)\n" +
    "   This helps improve VibeCheck. Off by default. (y/N): ",
    false
  );

  // Global registry opt-in
  const globalRegistry = nonInteractive ? false : await askYesNo(
    "\n📁 Global project registry? (lets `vibeguard list` show all your projects)\n" +
    "   Stores ONLY: project name, ID, path, git remote in ~/.vibeguard/registry.json.\n" +
    "   No code, no findings, no secrets. (y/N): ",
    false
  );

  console.log();

  // Compute project ID and name (used everywhere)
  const projectId = computeProjectId(cwd);
  const projectName = computeProjectName(cwd);
  console.log(`✓ Project ID: ${projectId} (${projectName})`);

  // Create .vibeguard/
  const vgDir = path.join(cwd, ".vibeguard");
  ["", "patterns", "proposed_skills"].forEach((sub) =>
    fs.mkdirSync(path.join(vgDir, sub), { recursive: true })
  );
  console.log("✓ Created .vibeguard/");

  // Initialize JSON data files
  const now = new Date().toISOString();

  fs.writeFileSync(path.join(vgDir, "project_id.txt"), projectId);

  writeIfMissing(path.join(vgDir, "findings.json"), "[]");
  writeIfMissing(
    path.join(vgDir, "timeline.json"),
    JSON.stringify([{
      ts: now, type: "installed", version: "0.1.0", project_id: projectId,
      project_name: projectName, telemetry, global_registry: globalRegistry,
      integrations,
    }], null, 2)
  );
  writeIfMissing(
    path.join(vgDir, "memory.json"),
    JSON.stringify({
      project: {name: projectName, id: projectId},
      stack: [], features: [], decisions: [], known_risks: [],
      last_updated: now,
    }, null, 2)
  );
  writeIfMissing(
    path.join(vgDir, "summary.json"),
    JSON.stringify({
      counts: { CRITICAL: 0, PITFALL: 0, HYGIENE: 0, GOOD_TO_HAVE: 0 },
      total_open: 0, total_all: 0, updated_at: now,
    }, null, 2)
  );

  // Config (with project_id pinned)
  const config = {
    project_id: projectId,
    project_name: projectName,
    model: "haiku",
    model_id: "claude-haiku-4-5-20251001",
    telemetry,
    global_registry: globalRegistry,
    integrations,
    version: "0.1.0",
    installed_at: now,
  };
  fs.writeFileSync(path.join(vgDir, "config.json"), JSON.stringify(config, null, 2));
  console.log("✓ Created .vibeguard/config.json");

  // Set up .claude/
  const claudeDir = path.join(cwd, ".claude");
  ["agents", "skills", "hooks", "hooks/lib"].forEach((sub) =>
    fs.mkdirSync(path.join(claudeDir, sub), { recursive: true })
  );

  // Copy lib files
  const libFiles = [
    "store.py", "static_checks.py", "patterns.py", "guardrails.py",
    "project.py", "project_map.py", "file_selection.py",
    "integrations.py", "health_report.py", "ignore.py", "metrics.py",
    "context_extractor.py",
  ];
  libFiles.forEach((f) => {
    copyFile(
      path.join(VIBEGUARD_ROOT, "lib", f),
      path.join(claudeDir, "hooks", "lib", f)
    );
  });
  console.log("✓ Installed lib → .claude/hooks/lib/");

  // Copy agents
  copyFile(
    path.join(VIBEGUARD_ROOT, "agents", "analyzer.md"),
    path.join(claudeDir, "agents", "vibeguard-analyzer.md")
  );
  copyFile(
    path.join(VIBEGUARD_ROOT, "agents", "scanner.md"),
    path.join(claudeDir, "agents", "vibeguard-scanner.md")
  );
  console.log("✓ Installed agents → .claude/agents/");

  // Copy skill (context for Claude about VibeCheck)
  copyFile(
    path.join(VIBEGUARD_ROOT, "vibecheck.md"),
    path.join(claudeDir, "skills", "vibecheck.md")
  );
  console.log("✓ Installed skill → .claude/skills/vibecheck.md");

  // Copy slash commands (/vibecheck, /vibecheck-detail, /vibecheck-resolve, /vibecheck-scan, /vibecheck-status)
  const commandsDir = path.join(claudeDir, "commands");
  fs.mkdirSync(commandsDir, { recursive: true });
  const commandFiles = ["vibecheck.md", "vibecheck-detail.md", "vibecheck-resolve.md", "vibecheck-scan.md", "vibecheck-status.md"];
  for (const f of commandFiles) {
    copyFile(path.join(VIBEGUARD_ROOT, "commands", f), path.join(commandsDir, f));
  }
  console.log("✓ Installed commands → .claude/commands/ (/vibecheck, /vibecheck-detail, /vibecheck-resolve, /vibecheck-scan, /vibecheck-status)");

  // Copy hooks
  copyFile(
    path.join(VIBEGUARD_ROOT, "hooks", "stop.py"),
    path.join(claudeDir, "hooks", "vibeguard_stop.py")
  );
  copyFile(
    path.join(VIBEGUARD_ROOT, "hooks", "session_start.py"),
    path.join(claudeDir, "hooks", "vibeguard_session_start.py")
  );
  copyFile(
    path.join(VIBEGUARD_ROOT, "hooks", "post_tool.py"),
    path.join(claudeDir, "hooks", "vibeguard_post_tool.py")
  );
  ["vibeguard_stop.py", "vibeguard_session_start.py", "vibeguard_post_tool.py"].forEach((f) =>
    fs.chmodSync(path.join(claudeDir, "hooks", f), 0o755)
  );
  console.log("✓ Installed hooks → .claude/hooks/");

  // Wire hooks into settings.json
  wireHooks(claudeDir);
  console.log("✓ Registered hooks in .claude/settings.json");

  // Update CLAUDE.md
  addToClaudeMd(cwd, hasClaudeMd);
  console.log("✓ Updated CLAUDE.md");

  // .gitignore
  updateGitignore(cwd);

  // .vibeguardignore (default content if missing)
  const vgIgnorePath = path.join(cwd, ".vibeguardignore");
  if (!fs.existsSync(vgIgnorePath)) {
    const defaultContent = `# VibeCheck ignore patterns
# Like .gitignore — patterns to skip during analysis.
# Defaults are applied automatically (node_modules/, dist/, .git/, etc).
# Add project-specific overrides below.

# Examples:
# docs/                    # skip the entire docs directory
# *.generated.ts           # skip auto-generated TypeScript
# scripts/migrations/      # skip migration scripts
# !docs/architecture.md    # but DO analyze this specific file (negation)
# legacy/                  # skip legacy code we're not actively touching
`;
    fs.writeFileSync(vgIgnorePath, defaultContent);
    console.log("✓ Created .vibeguardignore (customize what to skip)");
  }

  // Build initial project map (background, doesn't block)
  console.log("📚 Building lightweight project map...");
  try {
    const buildResult = execSync(
      `PYTHONPATH=.claude/hooks/lib python3 -c "import sys; sys.path.insert(0, '.claude/hooks/lib'); from pathlib import Path; import project_map; m = project_map.build_full_map(Path('.')); print(len(m['files']))"`,
      { cwd, encoding: "utf8", timeout: 30_000, stdio: ["pipe", "pipe", "pipe"] }
    );
    const fileCount = parseInt(buildResult.trim()) || 0;
    console.log(`   Indexed ${fileCount} source files (offline, no LLM)`);
  } catch {
    console.log("   (project map will build on first analysis)");
  }

  // Register globally if opted in
  if (globalRegistry) {
    try {
      execSync(
        `PYTHONPATH=.claude/hooks/lib python3 -c "import sys; sys.path.insert(0, '.claude/hooks/lib'); from pathlib import Path; import project; project.registry_register(Path('.'))"`,
        { cwd, stdio: ["pipe", "pipe", "pipe"] }
      );
      console.log("✓ Registered in global registry (~/.vibeguard/registry.json)");
    } catch {
      console.log("⚠️  Could not register globally");
    }
  }

  console.log(`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ VibeCheck active in: ${projectName}
   Project ID: ${projectId}
   ${integrations.length > 0 ? `Integrations: ${integrations.join(", ")}` : "No external tools detected"}

After each task Claude finishes, you'll see:
  [VibeCheck] 🔴 1 critical · 💡 3 suggestions · /vg to review

Commands:
  /vg                   View findings with fix prompts
  /vg-detail [id]       Full detail on one finding
  /vg-resolve [id]      Mark fixed
  /vg-scan              Scan existing codebase
  /vg-report            Open health dashboard
  /vg-timeline          Activity log
  /vg-status            Project health overview
  /vg-skills            Review proposed skills
  /vg-promote-skill     Promote a proposed skill to active
  /vg-model [model]     Switch model (haiku|sonnet)

Model: Claude Haiku · ~$0.001-0.002 per analysis
.vibeguard/ is in .gitignore. Findings stay local.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`);

  if (detectExistingCode(cwd)) {
    console.log(
      "💡 Existing code detected. Run `npx vibeguard scan` to analyze your history.\n"
    );
  }

  // Fire init telemetry event (fire-and-forget, silently ignored if disabled)
  if (telemetry) {
    fireTelemetryEvent("vibecheck_init", {
      has_integrations: integrations.length > 0,
      global_registry: globalRegistry,
    }).catch(() => {});
  }
}

async function fireTelemetryEvent(event, properties = {}) {
  const POSTHOG_KEY = "REPLACE_WITH_POSTHOG_PROJECT_KEY";
  const POSTHOG_HOST = "https://us.i.posthog.com";
  if (POSTHOG_KEY === "REPLACE_WITH_POSTHOG_PROJECT_KEY") return;

  const idFile = path.join(os.homedir(), ".vibecheck", "id");
  let machineId;
  try {
    fs.mkdirSync(path.dirname(idFile), { recursive: true });
    if (fs.existsSync(idFile)) {
      machineId = fs.readFileSync(idFile, "utf8").trim();
    } else {
      machineId = crypto.randomUUID();
      fs.writeFileSync(idFile, machineId);
    }
  } catch {
    machineId = "unknown";
  }

  const payload = JSON.stringify({
    api_key: POSTHOG_KEY,
    event,
    distinct_id: machineId,
    properties: { ...properties, $ip: null, vibecheck_version: "0.1.0" },
  });

  const url = new URL(`${POSTHOG_HOST}/capture/`);
  const mod = await import("https:" === url.protocol ? "https" : "http");
  return new Promise((resolve) => {
    const req = mod.request(
      { hostname: url.hostname, path: url.pathname, method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) },
        timeout: 1000 },
      (res) => { res.resume(); resolve(); }
    );
    req.on("error", resolve);
    req.on("timeout", () => { req.destroy(); resolve(); });
    req.write(payload);
    req.end();
  });
}

function detectIntegrations(cwd) {
  const integrations = [];
  if (fs.existsSync(path.join(cwd, "graphify-out", "graph.json"))) integrations.push("graphify");
  if (fs.existsSync(path.join(cwd, "openspec")) &&
      (fs.existsSync(path.join(cwd, "openspec", "specs")) ||
       fs.existsSync(path.join(cwd, "openspec", "changes")))) integrations.push("openspec");
  if (fs.existsSync(path.join(cwd, ".claude-mem")) ||
      fs.existsSync(path.join(os.homedir(), ".claude-mem"))) integrations.push("claude-mem");
  if (fs.existsSync(path.join(os.homedir(), ".icm")) ||
      fs.existsSync(path.join(cwd, ".icm"))) integrations.push("icm");
  return integrations;
}

function computeProjectId(cwd) {
  // Try git remote first
  try {
    const url = execSync("git config --get remote.origin.url",
      { cwd, encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }).trim();
    if (url) {
      let n = url.toLowerCase();
      ["https://", "http://", "git@", "ssh://"].forEach((p) => {
        if (n.startsWith(p)) n = n.slice(p.length);
      });
      n = n.replace(/:/g, "/").replace(/\.git$/, "").replace(/\/+$/, "");
      return "git-" + crypto.createHash("sha1").update(n).digest("hex").slice(0, 12);
    }
  } catch {}
  // First commit
  try {
    const commit = execSync("git rev-list --max-parents=0 HEAD",
      { cwd, encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }).trim().split("\n")[0];
    if (commit) return "commit-" + commit.slice(0, 12);
  } catch {}
  // Path hash
  return "path-" + crypto.createHash("sha1").update(path.resolve(cwd)).digest("hex").slice(0, 12);
}

function computeProjectName(cwd) {
  try {
    const pkg = path.join(cwd, "package.json");
    if (fs.existsSync(pkg)) {
      const data = JSON.parse(fs.readFileSync(pkg, "utf8"));
      if (data.name) return data.name;
    }
  } catch {}
  return path.basename(cwd);
}

function wireHooks(claudeDir) {
  // Project-level settings: only env, no hooks.
  // Hooks go in ~/.claude/settings.json (user-level) so they fire from worktrees too.
  const settingsPath = path.join(claudeDir, "settings.json");
  let settings = {};
  if (fs.existsSync(settingsPath)) {
    try { settings = JSON.parse(fs.readFileSync(settingsPath, "utf8")); }
    catch { settings = {}; }
  }
  if (!settings.env) settings.env = {};
  settings.env.VIBEGUARD_DEBUG = "1";
  fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));

  // Wire hooks into ~/.claude/settings.json
  const userSettingsPath = path.join(os.homedir(), ".claude", "settings.json");
  let userSettings = {};
  if (fs.existsSync(userSettingsPath)) {
    try { userSettings = JSON.parse(fs.readFileSync(userSettingsPath, "utf8")); }
    catch { userSettings = {}; }
  }
  if (!userSettings.hooks) userSettings.hooks = {};

  const rootExpr = `ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)`;

  const stopHook = {
    hooks: [{
      type: "command",
      command: `${rootExpr} && [ -f "$ROOT/.claude/hooks/vibeguard_stop.py" ] && VIBEGUARD_DEBUG=1 PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/vibeguard_stop.py"`,
      async: false, timeout: 60,
    }],
  };
  if (!userSettings.hooks.Stop) userSettings.hooks.Stop = [];
  if (!userSettings.hooks.Stop.some((h) => JSON.stringify(h).includes("vibeguard_stop"))) {
    userSettings.hooks.Stop.push(stopHook);
  }

  const startHook = {
    hooks: [{
      type: "command",
      command: `${rootExpr} && [ -f "$ROOT/.claude/hooks/vibeguard_session_start.py" ] && VIBEGUARD_DEBUG=1 PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/vibeguard_session_start.py"`,
      async: false, timeout: 35,
    }],
  };
  if (!userSettings.hooks.SessionStart) userSettings.hooks.SessionStart = [];
  if (!userSettings.hooks.SessionStart.some((h) => JSON.stringify(h).includes("vibeguard_session_start"))) {
    userSettings.hooks.SessionStart.push(startHook);
  }

  const postToolHook = {
    matcher: "Read|Write|Edit|MultiEdit",
    hooks: [{
      type: "command",
      command: `${rootExpr} && [ -f "$ROOT/.claude/hooks/vibeguard_post_tool.py" ] && VIBEGUARD_DEBUG=1 PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/vibeguard_post_tool.py"`,
      async: true,
    }],
  };
  if (!userSettings.hooks.PostToolUse) userSettings.hooks.PostToolUse = [];
  if (!userSettings.hooks.PostToolUse.some((h) => JSON.stringify(h).includes("vibeguard_post_tool"))) {
    userSettings.hooks.PostToolUse.push(postToolHook);
  }

  fs.writeFileSync(userSettingsPath, JSON.stringify(userSettings, null, 2));
  console.log("✓ Registered hooks in ~/.claude/settings.json");
}

function addToClaudeMd(cwd, exists) {
  const claudeMdPath = path.join(cwd, "CLAUDE.md");
  // Read the canonical template from the package
  const templatePath = path.join(VIBEGUARD_ROOT, "CLAUDE.template.md");
  let block;
  if (fs.existsSync(templatePath)) {
    block = "\n" + fs.readFileSync(templatePath, "utf8");
  } else {
    // Inline fallback — kept in sync with CLAUDE.template.md
    block = `
## VibeCheck (active) — runs after every code change

After ANY response where you used Write, Edit, or MultiEdit tools, do this at the END of your response — after completing the user's request:

1. Read \`.vibeguard/findings.json\` to get existing findings and next ID
2. Read each file you just modified (you know which ones — you edited them this turn)
3. Check for security issues AND dev tips (rules below)
4. Write new security findings to \`.vibeguard/findings.json\`
5. Auto-resolve: for each open finding whose file you read, if issue is gone → set \`status:"resolved"\`, add \`resolved_at\`, \`resolution_note:"auto-resolved"\`
6. Always end your response with a VibeCheck footer (format below)

**CRITICAL** — flag only if you can state a concrete exploit:
- Route handles user data without auth check
- User input in DB query (SQL injection)
- Webhook/payment endpoint without signature verification
- Secret/credential hardcoded in source

**PITFALL** — architectural trap:
- In-memory rate limiting or counters (won't survive restarts)
- Custom auth/JWT instead of using a library

**HYGIENE**: non-trivial feature with no tests · \`await\` without try/catch in payment/auth/DB

**GOOD_TO_HAVE**: missing rate limiting · missing input validation on user-facing forms

**DROP**: large files, console.log (unless leaking secrets), naming style, anything in existing findings.

Finding format: {"id":"vg-NNN","severity":"...","title":"...","file":"path:line","why":"...","fix_prompt":"...","status":"open","source":"live","detected_at":"ISO"}

Dev Tips — show as short witty one-liners after the security check (max 2):
- No tests for new feature · new route not wired to UI · big change (>5 files) → suggest phases
- Duplicate logic elsewhere · no git commit · backward compat risk · ops complexity

Footer — be the witty senior dev friend (memes, movie refs ok):
If issues: \`---\\nVibeCheck: 🔴 N critical · ⚡ N pitfalls · 🧹 N hygiene\\n💡 [dev tip]\`
If clean: \`---\\nVibeCheck: ✅ [witty one-liner — e.g. "This is the way." / "No issues. Chef's kiss."]\\n💡 [dev tip if applicable]\`

Commands: \`/vg\` · \`/vg-detail <id>\` · \`/vg-resolve <id>\` · \`/vg-status\`
`;
  }

  if (exists) {
    const current = fs.readFileSync(claudeMdPath, "utf8");
    if (!current.includes("VibeCheck")) fs.appendFileSync(claudeMdPath, block);
  } else {
    fs.writeFileSync(claudeMdPath, `# Project\n${block}`);
  }

  // Commit CLAUDE.md so git worktrees (used by Claude Code's Code tab) inherit it
  try {
    execSync(`git add "${claudeMdPath}"`, { cwd, stdio: ["pipe", "pipe", "ignore"] });
    execSync(`git commit -m "Add VibeCheck security rules to CLAUDE.md"`, {
      cwd, stdio: ["pipe", "pipe", "ignore"],
    });
  } catch {
    // Not a git repo, or nothing to commit — silently continue
  }
}

function updateGitignore(cwd) {
  const gitignorePath = path.join(cwd, ".gitignore");
  const entry = "\n# VibeCheck — local findings, not committed\n.vibeguard/\n";
  if (fs.existsSync(gitignorePath)) {
    const content = fs.readFileSync(gitignorePath, "utf8");
    if (!content.includes(".vibeguard")) {
      fs.appendFileSync(gitignorePath, entry);
      console.log("✓ Added .vibeguard/ to .gitignore");
    }
  } else {
    fs.writeFileSync(gitignorePath, entry);
    console.log("✓ Created .gitignore");
  }
}

function detectExistingCode(cwd) {
  try {
    const result = execSync(
      `find . -name "*.js" -o -name "*.ts" -o -name "*.py" | grep -v node_modules | grep -v .git | head -5`,
      { cwd, encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }
    );
    return result.trim().split("\n").filter(Boolean).length >= 3;
  } catch { return false; }
}

function askYesNo(question, defaultYes) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => {
      rl.close();
      const trimmed = answer.trim().toLowerCase();
      if (defaultYes) resolve(trimmed !== "n" && trimmed !== "no");
      else resolve(trimmed === "y" || trimmed === "yes");
    });
  });
}

function writeIfMissing(filePath, content) {
  if (!fs.existsSync(filePath)) fs.writeFileSync(filePath, content);
}

function copyFile(src, dest) {
  if (!fs.existsSync(src)) throw new Error(`Missing: ${src}`);
  fs.copyFileSync(src, dest);
}

main();
