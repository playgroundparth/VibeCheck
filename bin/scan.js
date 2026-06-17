#!/usr/bin/env node
/**
 * vibecheck scan
 * One-time scan of an existing codebase.
 * Shows cost estimate, lets user pick model + depth, then runs.
 */

import fs from "fs";
import path from "path";
import { execSync, spawn } from "child_process";
import readline from "readline";

// Pricing per 1M tokens (as of 2025)
const MODELS = {
  haiku: {
    id: "claude-haiku-4-5-20251001",
    label: "Claude Haiku 4.5",
    note: "fast · cheapest",
    input_per_m: 0.80,
    output_per_m: 4.00,
  },
  sonnet: {
    id: "claude-sonnet-4-6",
    label: "Claude Sonnet 4.6",
    note: "deeper analysis · ~5x cost",
    input_per_m: 3.00,
    output_per_m: 15.00,
  },
};

const DEPTHS = {
  quick:    { label: "Quick",    files: 10,  note: "10 key files — fastest, cheapest" },
  standard: { label: "Standard", files: 20,  note: "20 strategic files — recommended" },
  deep:     { label: "Deep",     files: 50,  note: "50 files — thorough coverage" },
  full:     { label: "Full repo",files: 999, note: "all files — slowest, most complete" },
};

const AVG_TOKENS_PER_FILE = 2000;
const OUTPUT_TOKENS = 2500;

function estimateCost(model, files) {
  const inputTokens = files * AVG_TOKENS_PER_FILE;
  const cost = (inputTokens / 1_000_000) * model.input_per_m
             + (OUTPUT_TOKENS / 1_000_000) * model.output_per_m;
  return cost;
}

async function main() {
  const cwd = process.cwd();
  const vcDir = path.join(cwd, ".vibecheck");

  if (!fs.existsSync(vcDir)) {
    console.error("❌ VibeCheck not initialized.\n   Run: npx github:playgroundparth/VibeCheck init");
    process.exit(1);
  }

  // Count source files
  let fileCount = 0;
  try {
    const result = execSync(
      `find . -type f \\( -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" -o -name "*.py" -o -name "*.go" -o -name "*.rb" \\) | grep -v node_modules | grep -v .git | grep -v dist | grep -v .next | wc -l`,
      { cwd, encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }
    );
    fileCount = parseInt(result.trim()) || 0;
  } catch {
    fileCount = 0;
  }

  // Model selection
  console.log(`
🛡️  VibeCheck Scan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Source files found: ~${fileCount || "unknown"}

Select model:
  1) ${MODELS.haiku.label.padEnd(26)} ${MODELS.haiku.note}
  2) ${MODELS.sonnet.label.padEnd(26)} ${MODELS.sonnet.note}
`);

  const modelChoice = await ask("Model (1/2, default 1): ");
  const modelKey = modelChoice === "2" ? "sonnet" : "haiku";
  const model = MODELS[modelKey];

  // Depth selection
  const maxFiles = Math.min(fileCount || 20, 999);
  console.log(`
Select scan depth:
  1) ${DEPTHS.quick.label.padEnd(12)} ~${DEPTHS.quick.files} files    ${DEPTHS.quick.note}
  2) ${DEPTHS.standard.label.padEnd(12)} ~${DEPTHS.standard.files} files    ${DEPTHS.standard.note}
  3) ${DEPTHS.deep.label.padEnd(12)} ~${DEPTHS.deep.files} files    ${DEPTHS.deep.note}
  4) ${DEPTHS.full.label.padEnd(12)} ~${Math.min(fileCount, 999)} files  ${DEPTHS.full.note}
`);

  const depthChoice = await ask("Depth (1/2/3/4, default 2): ");
  const depthMap = { "1": "quick", "3": "deep", "4": "full" };
  const depthKey = depthMap[depthChoice] || "standard";
  const depth = DEPTHS[depthKey];
  const filesToRead = Math.min(depth.files, maxFiles);

  // Cost estimate
  const costLow = estimateCost(model, Math.max(filesToRead * 0.7, 5));
  const costHigh = estimateCost(model, filesToRead);
  const inputTokens = filesToRead * AVG_TOKENS_PER_FILE;

  console.log(`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Model:          ${model.label}
Depth:          ${depth.label} (~${filesToRead} files)
Tokens (est):   ~${(inputTokens / 1000).toFixed(0)}K input + ~${(OUTPUT_TOKENS / 1000).toFixed(1)}K output
Cost (est):     ~$${costLow.toFixed(3)}–$${costHigh.toFixed(3)}
Time (est):     ${depthKey === "full" ? "2–5 min" : depthKey === "deep" ? "60–120s" : "30–60s"}

Checks: auth, payments, database, routes, secrets,
        tests, repo hygiene, common pitfalls.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);

  const confirmed = await confirm("Run scan? (yes/no): ");
  if (!confirmed) {
    console.log("\nCancelled. Type /vibecheck-scan inside Claude Code to run from there.");
    process.exit(0);
  }

  console.log("\nStarting scan...");
  await runWithSpinner(cwd, vcDir, model, modelKey, depthKey, filesToRead);
}

function runWithSpinner(cwd, vcDir, model, modelKey, depthKey, filesToRead) {
  return new Promise((resolve) => {
    const frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    let i = 0;
    const messages = [
      "Reading project structure...",
      "Sampling key files...",
      "Analyzing auth & payments...",
      "Checking for security issues...",
      "Looking for common pitfalls...",
      "Writing findings...",
    ];
    let msgIdx = 0;

    const spinner = setInterval(() => {
      const frame = frames[i++ % frames.length];
      const msg = messages[Math.min(msgIdx, messages.length - 1)];
      process.stdout.write(`\r${frame} ${msg}   `);
      if (i % 20 === 0) msgIdx++;
    }, 80);

    const claudeBin = findClaude();
    if (!claudeBin) {
      clearInterval(spinner);
      process.stdout.write("\r");
      console.error(
        "❌ `claude` CLI not found.\n" +
        "   Fix: echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.zshrc && source ~/.zshrc\n" +
        "   Or run /vibecheck-scan inside an active Claude Code session."
      );
      process.exit(1);
    }

    const depthInstruction = depthKey === "full"
      ? `Read as many files as needed (no file limit). Be thorough.`
      : `Read at most ${filesToRead} files total. Be strategic.`;

    const proc = spawn(
      claudeBin,
      [
        "-p",
        `Run a full VibeCheck scan of this codebase. ${depthInstruction} Analyze for all finding types: security risks, pitfalls, testing gaps, hygiene issues. Write findings to .vibecheck/findings.json`,
        "--agent", "vibecheck-scanner",
        "--model", model.id,
        "--dangerously-skip-permissions",
      ],
      {
        cwd,
        stdio: ["ignore", "pipe", "pipe"],
        timeout: 300_000,
      }
    );

    let stderr = "";
    proc.stderr.on("data", (d) => { stderr += d.toString(); });

    proc.on("error", (err) => {
      clearInterval(spinner);
      process.stdout.write("\r");
      if (err.code === "ENOENT") {
        console.error("❌ `claude` CLI not found. Make sure Claude Code is installed and in your PATH.");
      } else {
        console.error("❌ Scan error:", err.message);
      }
      process.exit(1);
    });

    proc.on("close", (code) => {
      clearInterval(spinner);
      process.stdout.write("\r" + " ".repeat(60) + "\r");

      // claude -p can exit non-zero even when the agent completed successfully.
      // Treat a written findings.json as the real success signal.
      const findingsPath = path.join(vcDir, "findings.json");
      const findingsWritten = fs.existsSync(findingsPath);

      if (code !== 0 && !findingsWritten) {
        console.error("❌ Scan failed. Make sure Claude Code CLI is installed and authenticated.");
        if (stderr) console.error(stderr.slice(0, 500));
        process.exit(1);
      }

      // Count from findings.json directly (summary.json is updated by the stop hook, not the scanner)
      const findings = readFindings(vcDir);
      const open = findings.filter(f => f.status !== "resolved" && f.status !== "dismissed");
      const counts = {};
      for (const f of open) counts[f.severity] = (counts[f.severity] || 0) + 1;

      const critical = counts.CRITICAL || 0;
      const pitfall  = counts.PITFALL  || 0;
      const hygiene  = counts.HYGIENE  || 0;
      const good     = counts.GOOD_TO_HAVE || 0;
      const total    = open.length;

      // Record scan cost in metrics
      recordScanMetric(vcDir, modelKey, filesToRead);

      console.log("✅ Scan complete.\n");
      if (total > 0) {
        const parts = [];
        if (critical) parts.push(`🔴 ${critical} critical`);
        if (pitfall)  parts.push(`⚡ ${pitfall} pitfall${pitfall !== 1 ? "s" : ""}`);
        if (hygiene)  parts.push(`🧹 ${hygiene} hygiene`);
        if (good)     parts.push(`💡 ${good} suggestion${good !== 1 ? "s" : ""}`);
        console.log(`Found: ${parts.join(" · ")}\n`);
        console.log(`Type \`/vibecheck\` inside Claude Code to review with fix prompts.`);
      } else {
        console.log("No findings. Your codebase looks clean.");
      }
      resolve();
    });
  });
}

function recordScanMetric(vcDir, modelKey, filesRead) {
  try {
    const metricsPath = path.join(vcDir, "metrics.json");
    const AVG_TOKENS_PER_FILE = 2000;
    const OUTPUT_TOKENS = 2500;
    const INPUT_RATE = modelKey === "sonnet" ? 3.00 : 0.80;
    const OUTPUT_RATE = modelKey === "sonnet" ? 15.00 : 4.00;
    const inputTokens = filesRead * AVG_TOKENS_PER_FILE;
    const cost = (inputTokens / 1_000_000) * INPUT_RATE + (OUTPUT_TOKENS / 1_000_000) * OUTPUT_RATE;

    let m = {};
    try { m = JSON.parse(fs.readFileSync(metricsPath, "utf8")); } catch {}
    if (!m.totals) m.totals = { analyses_run: 0, tokens_consumed: 0, cost_usd: 0.0, findings_created: 0, findings_resolved: 0, findings_dismissed: 0, vc_invocations: 0, tasks_completed: 0, sessions: 0, static_checks_run: 0 };
    if (!m.by_day) m.by_day = {};
    if (!m.latencies) m.latencies = { analyzer_ms: [], static_check_ms: [], hook_overhead_ms: [] };

    m.totals.analyses_run += 1;
    m.totals.tokens_consumed += inputTokens;
    m.totals.cost_usd = Math.round((m.totals.cost_usd + cost) * 10000) / 10000;

    const today = new Date().toISOString().slice(0, 10);
    if (!m.by_day[today]) m.by_day[today] = { analyses: 0, static_runs: 0, tasks: 0, tokens: 0, cost: 0.0, findings_created: 0, resolved: 0, dismissed: 0, vc_invocations: 0 };
    m.by_day[today].analyses += 1;
    m.by_day[today].tokens += inputTokens;
    m.by_day[today].cost = Math.round((m.by_day[today].cost + cost) * 10000) / 10000;

    if (!m.first_seen) m.first_seen = new Date().toISOString();
    m.last_updated = new Date().toISOString();
    m.version = 1;

    fs.writeFileSync(metricsPath, JSON.stringify(m, null, 2));
  } catch {}
}

function findClaude() {
  const candidates = [
    process.env.CLAUDE_BIN,
    `${process.env.HOME}/.local/bin/claude`,
    "/usr/local/bin/claude",
    "/opt/homebrew/bin/claude",
  ].filter(Boolean);

  for (const p of candidates) {
    try {
      fs.accessSync(p, fs.constants.X_OK);
      return p;
    } catch {}
  }

  try {
    return execSync("which claude", { encoding: "utf8" }).trim();
  } catch {}

  return null;
}

function ask(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => { rl.close(); resolve(answer.trim()); });
  });
}

function confirm(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim().toLowerCase() === "yes" || answer.trim().toLowerCase() === "y");
    });
  });
}

function readConfig(vcDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(vcDir, "config.json"), "utf8"));
  } catch {
    return { model: "haiku" };
  }
}

function readFindings(vcDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(vcDir, "findings.json"), "utf8"));
  } catch {
    return [];
  }
}

main();
