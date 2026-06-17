#!/usr/bin/env node
/**
 * vibecheck init
 */

import fs from "fs";
import path from "path";
import os from "os";
import { execSync } from "child_process";
import { fileURLToPath } from "url";
import readline from "readline";
import crypto from "crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const VIBECHECK_ROOT = path.join(__dirname, "..");

/**
 * Find the main repo root from any directory, including git worktrees.
 * --git-common-dir always points to the shared .git dir of the main repo.
 */
function findRepoRoot(fromDir) {
  try {
    const gitCommonDir = execSync("git rev-parse --git-common-dir", {
      cwd: fromDir, stdio: ["ignore", "pipe", "ignore"],
    }).toString().trim();
    const gitCommonPath = path.isAbsolute(gitCommonDir)
      ? gitCommonDir
      : path.join(fromDir, gitCommonDir);
    const repoRoot = path.dirname(path.resolve(gitCommonPath));
    if (fs.existsSync(repoRoot)) return repoRoot;
  } catch {}
  try {
    return execSync("git rev-parse --show-toplevel", {
      cwd: fromDir, stdio: ["ignore", "pipe", "ignore"],
    }).toString().trim();
  } catch {}
  return fromDir;
}

async function main() {
  console.log("\n🛡️  VibeCheck init\n");

  const cwd = findRepoRoot(process.cwd());
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
    "\n📁 Global project registry? (lets `vibecheck list` show all your projects)\n" +
    "   Stores ONLY: project name, ID, path, git remote in ~/.vibecheck/registry.json.\n" +
    "   No code, no findings, no secrets. (y/N): ",
    false
  );

  console.log();

  // Compute project ID and name (used everywhere)
  const projectId = computeProjectId(cwd);
  const projectName = computeProjectName(cwd);
  console.log(`✓ Project ID: ${projectId} (${projectName})`);

  // Create .vibecheck/
  const vcDir = path.join(cwd, ".vibecheck");
  ["", "patterns", "proposed_skills"].forEach((sub) =>
    fs.mkdirSync(path.join(vcDir, sub), { recursive: true })
  );
  console.log("✓ Created .vibecheck/");

  // Initialize JSON data files
  const now = new Date().toISOString();

  fs.writeFileSync(path.join(vcDir, "project_id.txt"), projectId);

  writeIfMissing(path.join(vcDir, "findings.json"), "[]");
  writeIfMissing(
    path.join(vcDir, "timeline.json"),
    JSON.stringify([{
      ts: now, type: "installed", version: "0.1.0", project_id: projectId,
      project_name: projectName, telemetry, global_registry: globalRegistry,
      integrations,
    }], null, 2)
  );
  writeIfMissing(
    path.join(vcDir, "memory.json"),
    JSON.stringify({
      project: {name: projectName, id: projectId},
      stack: [], features: [], decisions: [], known_risks: [],
      last_updated: now,
    }, null, 2)
  );
  writeIfMissing(
    path.join(vcDir, "summary.json"),
    JSON.stringify({
      counts: { CRITICAL: 0, PITFALL: 0, HYGIENE: 0, GOOD_TO_HAVE: 0 },
      total_open: 0, total_all: 0, updated_at: now,
    }, null, 2)
  );

  // Config (with project_id pinned)
  const config = {
    project_id: projectId,
    project_name: projectName,
    mode: "full",
    telemetry,
    global_registry: globalRegistry,
    integrations,
    version: "0.1.0",
    installed_at: now,
  };
  fs.writeFileSync(path.join(vcDir, "config.json"), JSON.stringify(config, null, 2));
  console.log("✓ Created .vibecheck/config.json");

  const libFiles = [
    "store.py", "static_checks.py", "patterns.py", "guardrails.py",
    "project.py", "project_map.py", "health_report.py", "ignore.py",
    "metrics.py", "context_extractor.py", "vc_display.py", "telemetry.py",
    "graphify_query.py", "detection_engine.py", "capability.py", "async_detection.py",
  ];
  const skillTemplates = [
    "stripe.md", "supabase.md", "clerk.md", "prisma.md", "openai.md", "vercel.md",
  ];
  const frameworkFiles = [
    "event-driven.md", "irreversible-action.md", "billing-pricing.md",
    "async-scheduled.md", "concurrent-state.md", "cross-cutting-state.md",
    "external-service.md", "new-dependency.md", "ugc.md", "user-input.md",
  ];
  const commandFiles = [
    "vibecheck.md", "vibecheck-scan.md", "vibecheck-review.md",
    "vibecheck-skills.md", "vibecheck-help.md",
  ];

  const appConfigs = [
    { name: "Claude Code", dir: ".claude", requiresPrompts: false },
    { name: "Antigravity/Gemini", dir: ".agents", requiresPrompts: false },
    { name: "Codex", dir: ".codex", requiresPrompts: true },
  ];

  appConfigs.forEach((app) => {
    const appDir = path.join(cwd, app.dir);
    const subdirs = ["agents", "skills", "hooks", "hooks/lib", "commands"];
    if (app.requiresPrompts) {
      subdirs.push("prompts");
    }
    subdirs.forEach((sub) =>
      fs.mkdirSync(path.join(appDir, sub), { recursive: true })
    );

    // Copy lib files
    libFiles.forEach((f) => {
      copyFile(
        path.join(VIBECHECK_ROOT, "lib", f),
        path.join(appDir, "hooks", "lib", f),
        ".claude", app.dir
      );
    });

    // Copy integration skill templates
    const skillTemplatesDir = path.join(appDir, "hooks", "lib", "skills");
    fs.mkdirSync(skillTemplatesDir, { recursive: true });
    skillTemplates.forEach((f) => {
      copyFile(path.join(VIBECHECK_ROOT, "lib", "skills", f), path.join(skillTemplatesDir, f), ".claude", app.dir);
    });

    // Copy framework files
    const frameworksDir = path.join(appDir, "hooks", "lib", "frameworks");
    fs.mkdirSync(frameworksDir, { recursive: true });
    frameworkFiles.forEach((f) => {
      copyFile(path.join(VIBECHECK_ROOT, "frameworks", f), path.join(frameworksDir, f), ".claude", app.dir);
    });

    // Copy agents
    copyFile(
      path.join(VIBECHECK_ROOT, "agents", "scanner.md"),
      path.join(appDir, "agents", "vibecheck-scanner.md"),
      ".claude", app.dir
    );
    copyFile(
      path.join(VIBECHECK_ROOT, "agents", "scanner-deep.md"),
      path.join(appDir, "agents", "vibecheck-scanner-deep.md"),
      ".claude", app.dir
    );
    copyFile(
      path.join(VIBECHECK_ROOT, "agents", "scanner-opus.md"),
      path.join(appDir, "agents", "vibecheck-scanner-opus.md"),
      ".claude", app.dir
    );

    if (app.requiresPrompts) {
      // Copy to prompts/ too for Codex
      copyFile(
        path.join(VIBECHECK_ROOT, "agents", "scanner.md"),
        path.join(appDir, "prompts", "vibecheck-scanner.md"),
        ".claude", app.dir
      );
      copyFile(
        path.join(VIBECHECK_ROOT, "agents", "scanner-deep.md"),
        path.join(appDir, "prompts", "vibecheck-scanner-deep.md"),
        ".claude", app.dir
      );
      copyFile(
        path.join(VIBECHECK_ROOT, "agents", "scanner-opus.md"),
        path.join(appDir, "prompts", "vibecheck-scanner-opus.md"),
        ".claude", app.dir
      );
    }

    // Copy skill
    copyFile(
      path.join(VIBECHECK_ROOT, "vibecheck.md"),
      path.join(appDir, "skills", "vibecheck.md"),
      ".claude", app.dir
    );

    // Copy slash commands
    const commandsDir = path.join(appDir, "commands");
    for (const f of commandFiles) {
      copyFile(path.join(VIBECHECK_ROOT, "commands", f), path.join(commandsDir, f), ".claude", app.dir);
    }

    // Copy hooks
    copyFile(
      path.join(VIBECHECK_ROOT, "hooks", "stop.py"),
      path.join(appDir, "hooks", "vibecheck_stop.py"),
      ".claude", app.dir
    );
    copyFile(
      path.join(VIBECHECK_ROOT, "hooks", "session_start.py"),
      path.join(appDir, "hooks", "vibecheck_session_start.py"),
      ".claude", app.dir
    );
    copyFile(
      path.join(VIBECHECK_ROOT, "hooks", "post_tool.py"),
      path.join(appDir, "hooks", "vibecheck_post_tool.py"),
      ".claude", app.dir
    );
    ["vibecheck_stop.py", "vibecheck_session_start.py", "vibecheck_post_tool.py"].forEach((f) =>
      fs.chmodSync(path.join(appDir, "hooks", f), 0o755)
    );

    // Symlink commands into worktrees
    wireCommandsIntoWorktrees(appDir);

    // Wire preview server for HTML report
    wireLaunchJson(appDir);

    console.log(`✓ Installed files in workspace for ${app.name} (${app.dir}/)`);
  });

  // Wire hooks globally
  wireHooks();

  // Update CLAUDE.md
  addToClaudeMd(cwd, hasClaudeMd);
  console.log("✓ Updated CLAUDE.md");

  // .gitignore
  updateGitignore(cwd);

  // .vibecheck-ignore (default content if missing)
  const vcIgnorePath = path.join(cwd, ".vibecheck-ignore");
  if (!fs.existsSync(vcIgnorePath)) {
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
    fs.writeFileSync(vcIgnorePath, defaultContent);
    console.log("✓ Created .vibecheck-ignore (customize what to skip)");
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

  // Seed artifact groups — lifecycle relationships between files
  seedArtifactGroups(cwd, vcDir);

  // Register globally if opted in
  if (globalRegistry) {
    try {
      execSync(
        `PYTHONPATH=.claude/hooks/lib python3 -c "import sys; sys.path.insert(0, '.claude/hooks/lib'); from pathlib import Path; import project; project.registry_register(Path('.'))"`,
        { cwd, stdio: ["pipe", "pipe", "pipe"] }
      );
      console.log("✓ Registered in global registry (~/.vibecheck/registry.json)");
    } catch {
      console.log("⚠️  Could not register globally");
    }
  }

  console.log(`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ VibeCheck installed in: ${projectName}
   ${integrations.length > 0 ? `Integrations: ${integrations.join(", ")}` : "No external tools detected"}

⚠️  Restart Claude Code now (quit fully and reopen).
   Commands and hooks won't appear until after a restart.
   On Mac: Cmd+Q, then reopen. On Windows: close from taskbar.

After restarting, type /vibecheck in the chat to confirm it's working.

Commands (type / to browse):
  /vibecheck                   View open findings dashboard
  /vibecheck [id]              Full detail on one finding
  /vibecheck resolve [id]      Mark a finding as resolved
  /vibecheck-scan              Full repo scan (options: --deep, --pro)
  /vibecheck-review            On-demand code review of current diff
  /vibecheck-skills            Manage integration context skills
  /vibecheck-help              Quick reference help guide

After each task Claude finishes, you'll see a VibeCheck footer automatically.
.vibecheck/ is in .gitignore. Findings stay local.

Next: commit CLAUDE.md so future branches inherit the VibeCheck rules:
  git add CLAUDE.md && git commit -m "Add VibeCheck to CLAUDE.md"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`);

  if (detectExistingCode(cwd)) {
    console.log(
      "💡 Existing code detected. Run `npx github:playgroundparth/VibeCheck scan` to analyze your history.\n"
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

function seedArtifactGroups(cwd, vcDir) {
  const mapPath = path.join(vcDir, "project_map.json");
  let existing = {};
  try { existing = JSON.parse(fs.readFileSync(mapPath, "utf8")); } catch {}

  // Don't overwrite existing artifact_groups — user or scanner may have enriched them
  if (existing.artifact_groups && Object.keys(existing.artifact_groups).length > 0) return;

  const groups = {};

  const now = new Date().toISOString();

  function makeGroup(fields) {
    const mustCheckKeys = ["installed_by", "removed_by", "wired_by"];
    const niceCheckKeys = ["documented_in", "updated_by", "auth_checked_by", "migrations_in", "seed_in"];
    return {
      ...fields,
      must_check: mustCheckKeys.filter(k => fields[k]),
      nice_check: niceCheckKeys.filter(k => fields[k]),
      confidence: "seeded",
      evidence: ["detected at init time from project directory structure"],
      times_confirmed: 0,
      created_at: now,
      last_confirmed: null,
    };
  }

  // Slash commands pattern (VibeCheck-style or similar tool)
  if (fs.existsSync(path.join(cwd, "commands"))) {
    const hasBin = fs.existsSync(path.join(cwd, "bin", "init.js")) ||
                   fs.existsSync(path.join(cwd, "bin", "install.js"));
    if (hasBin) {
      groups["slash_commands"] = makeGroup({
        description: "Slash command files — installed, updated, and removed by lifecycle scripts",
        source_glob: "commands/*.md",
        installed_by: ["bin/init.js", "bin/update.js"],
        updated_by: ["bin/update.js"],
        removed_by: ["bin/uninstall.js"],
        documented_in: ["README.md", "bin/cli.js"],
      });
    }
  }

  // Hooks pattern
  if (fs.existsSync(path.join(cwd, "hooks")) &&
      fs.existsSync(path.join(cwd, "bin", "init.js"))) {
    groups["hooks"] = makeGroup({
      description: "Hook files — installed and wired into settings by lifecycle scripts",
      source_glob: "hooks/*.py",
      installed_by: ["bin/init.js", "bin/update.js"],
      updated_by: ["bin/update.js"],
      removed_by: ["bin/uninstall.js"],
      wired_by: ["bin/init.js"],
    });
  }

  // Next.js App Router API routes
  if (fs.existsSync(path.join(cwd, "app", "api"))) {
    groups["api_routes"] = makeGroup({
      description: "Next.js API route handlers — must have auth middleware",
      source_glob: "app/api/**/*.ts",
      auth_checked_by: ["middleware.ts", "lib/auth.ts", "lib/middleware.ts"],
      documented_in: ["README.md"],
    });
  }

  // Next.js Pages Router API routes
  if (!groups["api_routes"] && fs.existsSync(path.join(cwd, "pages", "api"))) {
    groups["api_routes"] = makeGroup({
      description: "Next.js API route handlers — must have auth middleware",
      source_glob: "pages/api/**/*.ts",
      auth_checked_by: ["middleware.ts", "lib/auth.ts"],
    });
  }

  // Prisma schema — changes require migrations
  if (fs.existsSync(path.join(cwd, "prisma", "schema.prisma"))) {
    groups["db_schema"] = makeGroup({
      description: "Database schema — changes must have a corresponding migration",
      source_glob: "prisma/schema.prisma",
      migrations_in: ["prisma/migrations/"],
      seed_in: ["prisma/seed.ts", "prisma/seed.js"],
    });
  }

  // Express/Fastify routes
  if (!groups["api_routes"] && (fs.existsSync(path.join(cwd, "src", "routes")) ||
      fs.existsSync(path.join(cwd, "routes")))) {
    const routeDir = fs.existsSync(path.join(cwd, "src", "routes")) ? "src/routes" : "routes";
    groups["api_routes"] = makeGroup({
      description: "API route handlers — must have auth middleware",
      source_glob: `${routeDir}/**/*.{js,ts}`,
      auth_checked_by: ["middleware/auth.js", "middleware/auth.ts", "src/middleware/auth.ts"],
    });
  }

  if (Object.keys(groups).length === 0) return;

  existing.artifact_groups = groups;
  if (!existing.version) existing.version = 1;
  existing.last_built = existing.last_built || now;

  try {
    fs.writeFileSync(mapPath, JSON.stringify(existing, null, 2));
    const n = Object.keys(groups).length;
    console.log(`✓ Seeded ${n} artifact group(s) in project_map.json (slash_commands, hooks, etc.)`);
  } catch {}
}

function wireCommandsIntoWorktrees(appDir) {
  const appBaseName = path.basename(appDir); // e.g. ".claude", ".agents", ".codex"
  const worktreesBase = path.join(appDir, "worktrees");
  if (!fs.existsSync(worktreesBase)) return;
  const worktrees = fs.readdirSync(worktreesBase, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
  let linked = 0;
  for (const wt of worktrees) {
    const wtAppDir = path.join(worktreesBase, wt, appBaseName);
    if (!fs.existsSync(wtAppDir)) continue;
    const target = path.join(wtAppDir, "commands");
    if (fs.existsSync(target)) continue; // already linked or has own commands dir
    try {
      fs.symlinkSync("../../../commands", target);
      linked++;
    } catch {}
  }
  if (linked > 0) console.log(`✓ Linked commands into ${linked} existing worktree(s) in ${appBaseName}`);
}

function wireHooks() {
  const rootExpr = `export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" && ROOT=$(dirname "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null)`;

  console.log();
  console.log("⚠️  VibeCheck writes hooks to global user-level configs (e.g. ~/.claude/settings.json).");
  console.log("   This is required for hooks to fire in git worktrees and desktop apps.");
  console.log("   The hooks check for VibeCheck before running — they no-op in other projects.");
  console.log();

  // 1. Claude
  try {
    const claudeSettingsPath = path.join(os.homedir(), ".claude", "settings.json");
    fs.mkdirSync(path.dirname(claudeSettingsPath), { recursive: true });
    let settings = {};
    if (fs.existsSync(claudeSettingsPath)) {
      try { settings = JSON.parse(fs.readFileSync(claudeSettingsPath, "utf8")); } catch { settings = {}; }
    }
    if (!settings.hooks) settings.hooks = {};

    const stopHook = {
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.claude/hooks/vibecheck_stop.py" ] && PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/vibecheck_stop.py"`,
        async: false, timeout: 60,
      }],
    };
    if (!settings.hooks.Stop) settings.hooks.Stop = [];
    if (!settings.hooks.Stop.some((h) => JSON.stringify(h).includes("vibecheck_stop"))) {
      settings.hooks.Stop.push(stopHook);
    }

    const startHook = {
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.claude/hooks/vibecheck_session_start.py" ] && PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/vibecheck_session_start.py"`,
        async: false, timeout: 35,
      }],
    };
    if (!settings.hooks.SessionStart) settings.hooks.SessionStart = [];
    if (!settings.hooks.SessionStart.some((h) => JSON.stringify(h).includes("vibecheck_session_start"))) {
      settings.hooks.SessionStart.push(startHook);
    }

    const postToolHook = {
      matcher: "Read|Write|Edit|MultiEdit",
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.claude/hooks/vibecheck_post_tool.py" ] && PYTHONPATH="$ROOT/.claude/hooks/lib" python3 "$ROOT/.claude/hooks/vibecheck_post_tool.py"`,
        async: true,
      }],
    };
    if (!settings.hooks.PostToolUse) settings.hooks.PostToolUse = [];
    if (!settings.hooks.PostToolUse.some((h) => JSON.stringify(h).includes("vibecheck_post_tool"))) {
      settings.hooks.PostToolUse.push(postToolHook);
    }

    fs.writeFileSync(claudeSettingsPath, JSON.stringify(settings, null, 2));
    console.log("✓ Registered hooks in ~/.claude/settings.json");
  } catch (e) {
    console.log("⚠️  Could not wire hooks in ~/.claude/settings.json:", e.message);
  }

  // 2. Antigravity/Gemini
  try {
    const geminiSettingsPath = path.join(os.homedir(), ".gemini", "settings.json");
    fs.mkdirSync(path.dirname(geminiSettingsPath), { recursive: true });
    let settings = {};
    if (fs.existsSync(geminiSettingsPath)) {
      try { settings = JSON.parse(fs.readFileSync(geminiSettingsPath, "utf8")); } catch { settings = {}; }
    }
    if (!settings.hooks) settings.hooks = {};

    const stopHook = {
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.agents/hooks/vibecheck_stop.py" ] && PYTHONPATH="$ROOT/.agents/hooks/lib" python3 "$ROOT/.agents/hooks/vibecheck_stop.py"`,
        async: false, timeout: 60,
      }],
    };
    if (!settings.hooks.SessionEnd) settings.hooks.SessionEnd = [];
    if (!settings.hooks.SessionEnd.some((h) => JSON.stringify(h).includes("vibecheck_stop"))) {
      settings.hooks.SessionEnd.push(stopHook);
    }

    const startHook = {
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.agents/hooks/vibecheck_session_start.py" ] && PYTHONPATH="$ROOT/.agents/hooks/lib" python3 "$ROOT/.agents/hooks/vibecheck_session_start.py"`,
        async: false, timeout: 35,
      }],
    };
    if (!settings.hooks.SessionStart) settings.hooks.SessionStart = [];
    if (!settings.hooks.SessionStart.some((h) => JSON.stringify(h).includes("vibecheck_session_start"))) {
      settings.hooks.SessionStart.push(startHook);
    }

    const postToolHook = {
      matcher: "view_file|write_to_file|replace_file_content|multi_replace_file_content",
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.agents/hooks/vibecheck_post_tool.py" ] && PYTHONPATH="$ROOT/.agents/hooks/lib" python3 "$ROOT/.agents/hooks/vibecheck_post_tool.py"`,
        async: true,
      }],
    };
    if (!settings.hooks.AfterTool) settings.hooks.AfterTool = [];
    if (!settings.hooks.AfterTool.some((h) => JSON.stringify(h).includes("vibecheck_post_tool"))) {
      settings.hooks.AfterTool.push(postToolHook);
    }

    fs.writeFileSync(geminiSettingsPath, JSON.stringify(settings, null, 2));
    console.log("✓ Registered hooks in ~/.gemini/settings.json");
  } catch (e) {
    console.log("⚠️  Could not wire hooks in ~/.gemini/settings.json:", e.message);
  }

  // 3. Codex
  try {
    const codexSettingsPath = path.join(os.homedir(), ".codex", "hooks.json");
    fs.mkdirSync(path.dirname(codexSettingsPath), { recursive: true });
    let settings = {};
    if (fs.existsSync(codexSettingsPath)) {
      try { settings = JSON.parse(fs.readFileSync(codexSettingsPath, "utf8")); } catch { settings = {}; }
    }
    if (!settings.hooks) settings.hooks = {};

    const stopHook = {
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.codex/hooks/vibecheck_stop.py" ] && PYTHONPATH="$ROOT/.codex/hooks/lib" python3 "$ROOT/.codex/hooks/vibecheck_stop.py"`,
        async: false, timeout: 60,
      }],
    };
    if (!settings.hooks.Stop) settings.hooks.Stop = [];
    if (!settings.hooks.Stop.some((h) => JSON.stringify(h).includes("vibecheck_stop"))) {
      settings.hooks.Stop.push(stopHook);
    }

    const startHook = {
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.codex/hooks/vibecheck_session_start.py" ] && PYTHONPATH="$ROOT/.codex/hooks/lib" python3 "$ROOT/.codex/hooks/vibecheck_session_start.py"`,
        async: false, timeout: 35,
      }],
    };
    if (!settings.hooks.SessionStart) settings.hooks.SessionStart = [];
    if (!settings.hooks.SessionStart.some((h) => JSON.stringify(h).includes("vibecheck_session_start"))) {
      settings.hooks.SessionStart.push(startHook);
    }

    const postToolHook = {
      matcher: "apply_patch|write_file|read_file",
      hooks: [{
        type: "command",
        command: `${rootExpr} && [ -f "$ROOT/.codex/hooks/vibecheck_post_tool.py" ] && PYTHONPATH="$ROOT/.codex/hooks/lib" python3 "$ROOT/.codex/hooks/vibecheck_post_tool.py"`,
        async: true,
      }],
    };
    if (!settings.hooks.PostToolUse) settings.hooks.PostToolUse = [];
    if (!settings.hooks.PostToolUse.some((h) => JSON.stringify(h).includes("vibecheck_post_tool"))) {
      settings.hooks.PostToolUse.push(postToolHook);
    }

    fs.writeFileSync(codexSettingsPath, JSON.stringify(settings, null, 2));
    console.log("✓ Registered hooks in ~/.codex/hooks.json");
  } catch (e) {
    console.log("⚠️  Could not wire hooks in ~/.codex/hooks.json:", e.message);
  }
}

function addToClaudeMd(cwd, exists) {
  const claudeMdPath = path.join(cwd, "CLAUDE.md");
  // Read the canonical template from the package — no fallback, template must ship with the package
  const templatePath = path.join(VIBECHECK_ROOT, "CLAUDE.template.md");
  if (!fs.existsSync(templatePath)) {
    console.error("❌ CLAUDE.template.md not found in package. Installation may be incomplete.");
    process.exit(1);
  }
  const block = "\n" + fs.readFileSync(templatePath, "utf8");

  if (exists) {
    const current = fs.readFileSync(claudeMdPath, "utf8");
    if (!current.includes("VibeCheck (active)")) fs.appendFileSync(claudeMdPath, block);
  } else {
    fs.writeFileSync(claudeMdPath, `# Project\n${block}`);
  }

  // Note: CLAUDE.md is NOT auto-committed. Commit it yourself so future branches
  // (and their worktrees) inherit the VibeCheck block:
  //   git add CLAUDE.md && git commit -m "Add VibeCheck to CLAUDE.md"

  // Patch any existing worktrees — Claude Code's Code tab opens each branch in its own
  // worktree at .claude/worktrees/<name>/, which has its own CLAUDE.md checked out from
  // that branch. Those branches may predate this install, so the VibeCheck block won't
  // be there. Append it directly so Claude sees the rules immediately without a merge.
  const worktreesBase = path.join(cwd, ".claude", "worktrees");
  if (fs.existsSync(worktreesBase)) {
    // Extract everything from the Engineering Standards section onward (includes VibeCheck)
    const templatePath = path.join(VIBECHECK_ROOT, "CLAUDE.template.md");
    if (!fs.existsSync(templatePath)) return;
    const templateLines = fs.readFileSync(templatePath, "utf8").split("\n");
    // Prefer starting at Engineering Standards (if present), fall back to VibeCheck section
    let vcStart = templateLines.findIndex((l) => l.startsWith("## Engineering standards"));
    if (vcStart === -1) vcStart = templateLines.findIndex((l) => l.startsWith("## VibeCheck (active)"));
    if (vcStart === -1) return;
    const vcBlock = "\n---\n" + templateLines.slice(vcStart).join("\n");

    const worktrees = fs.readdirSync(worktreesBase, { withFileTypes: true })
      .filter((d) => d.isDirectory()).map((d) => d.name);

    let patched = 0;
    for (const wt of worktrees) {
      const wtClaudeMd = path.join(worktreesBase, wt, "CLAUDE.md");
      if (!fs.existsSync(wtClaudeMd)) continue;
      const content = fs.readFileSync(wtClaudeMd, "utf8");
      if (content.includes("VibeCheck (active)")) continue; // already has it
      fs.appendFileSync(wtClaudeMd, vcBlock);
      // Commit to the worktree's branch so it survives future checkouts
      try {
      } catch {}
      patched++;
    }
    if (patched > 0) console.log(`✓ Patched VibeCheck rules into ${patched} existing worktree CLAUDE.md(s)`);
  }
}

function updateGitignore(cwd) {
  const gitignorePath = path.join(cwd, ".gitignore");
  const entry = "\n# VibeCheck — local findings, not committed\n.vibecheck/\n";
  if (fs.existsSync(gitignorePath)) {
    const content = fs.readFileSync(gitignorePath, "utf8");
    if (!content.includes(".vibecheck")) {
      fs.appendFileSync(gitignorePath, entry);
      console.log("✓ Added .vibecheck/ to .gitignore");
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

function copyFile(src, dest, search, replace) {
  if (!fs.existsSync(src)) throw new Error(`Missing: ${src}`);
  if (search && replace) {
    let content = fs.readFileSync(src, "utf8");
    content = content.split(search).join(replace);
    fs.writeFileSync(dest, content);
  } else {
    fs.copyFileSync(src, dest);
  }
}

function wireLaunchJson(claudeDir) {
  const launchPath = path.join(claudeDir, "launch.json");
  let launch = { version: "0.0.1", configurations: [] };
  if (fs.existsSync(launchPath)) {
    try { launch = JSON.parse(fs.readFileSync(launchPath, "utf8")); } catch {}
  }
  launch.configurations = (launch.configurations || []).filter(c => c.name !== "vibecheck-report");
  launch.configurations.push({
    name: "vibecheck-report",
    runtimeExecutable: "python3",
    runtimeArgs: ["-m", "http.server", "7337", "--directory", ".vibecheck"],
    port: 7337,
  });
  fs.writeFileSync(launchPath, JSON.stringify(launch, null, 2));
}

main();
