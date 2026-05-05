#!/usr/bin/env node
/**
 * Test runner — delegates to Python test suite and reports exit code.
 * Run: npm test  OR  node tests/run.js
 */

import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const result = spawnSync(
  "python3",
  [join(__dirname, "test_project_map.py")],
  { stdio: "inherit" }
);

process.exit(result.status ?? 1);
