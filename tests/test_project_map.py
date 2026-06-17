#!/usr/bin/env python3
"""
Tests for the deterministic parts of the VibeCheck review pipeline.

These tests do not require Claude — they test the Python layer only:
- Artifact group matching (find_artifact_group)
- Lifecycle file identification (lifecycle_files_for_changed)
- Severity classification (severity_for_missing_relationship)
- Confidence upgrade mechanics

The LLM-produced output (finding text, verdict, 🧪 line) is documented in
tests/fixtures/*/expected/finding.json as a golden contract — not asserted here.
"""

import json
import sys
from pathlib import Path

# Make lib importable
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import project_map as pm

FIXTURE_DRIFT  = Path(__file__).parent / "fixtures" / "command-lifecycle-drift"
FIXTURE_CLEAN  = Path(__file__).parent / "fixtures" / "command-lifecycle-clean"

ok = fail = 0

def check(name, condition, detail=""):
    global ok, fail
    if condition:
        print(f"  ✅ {name}")
        ok += 1
    else:
        print(f"  ❌ {name}{' — ' + detail if detail else ''}")
        fail += 1


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_groups(fixture: Path) -> dict:
    return json.loads((fixture / "project_map.json").read_text())["artifact_groups"]


def lifecycle_result(fixture: Path, filename: str) -> dict:
    """Run lifecycle_files_for_changed for a single file in a fixture."""
    groups = load_groups(fixture)
    cwd = fixture

    # Patch load_map so lifecycle_files_for_changed reads from fixture's project_map.json
    original_load = pm.load_map
    pm.load_map = lambda p: json.loads((fixture / "project_map.json").read_text())

    changed = [fixture / filename]
    result = pm.lifecycle_files_for_changed(cwd, changed)

    pm.load_map = original_load
    return result


# ── Suite 1: find_artifact_group ─────────────────────────────────────────────

print("\n── find_artifact_group ──")

groups = load_groups(FIXTURE_DRIFT)

name, group = pm.find_artifact_group("commands/foo.md", groups)
check("commands/foo.md matches slash_commands", name == "slash_commands")
check("group is not None", group is not None)

name2, _ = pm.find_artifact_group("bin/init.js", groups)
check("bin/init.js does not match any source_glob", name2 is None)

name3, _ = pm.find_artifact_group("commands/bar.md", groups)
check("commands/bar.md also matches slash_commands", name3 == "slash_commands")

name4, _ = pm.find_artifact_group("something/unrelated.py", groups)
check("unrelated file matches nothing", name4 is None)


# ── Suite 2: lifecycle_files_for_changed ─────────────────────────────────────

print("\n── lifecycle_files_for_changed (drift fixture) ──")

result = lifecycle_result(FIXTURE_DRIFT, "commands/foo.md")

check("commands/foo.md is in result", "commands/foo.md" in result)

if "commands/foo.md" in result:
    entry = result["commands/foo.md"]
    must = entry["must_check"]
    nice = entry["nice_check"]

    check("group is slash_commands", entry["group"] == "slash_commands")
    check("bin/init.js is in must_check",    "bin/init.js"    in must, f"got: {must}")
    check("bin/update.js is in must_check",  "bin/update.js"  in must, f"got: {must}")
    check("bin/uninstall.js is in must_check","bin/uninstall.js" in must, f"got: {must}")
    check("README.md is in nice_check",      "README.md"      in nice, f"got: {nice}")
    check("bin/cli.js is in nice_check",     "bin/cli.js"     in nice, f"got: {nice}")
    check("must_check does not contain nice files",
          "README.md" not in must, f"got: {must}")


# ── Suite 3: severity_for_missing_relationship ───────────────────────────────

print("\n── severity_for_missing_relationship ──")

groups = load_groups(FIXTURE_DRIFT)
group  = groups["slash_commands"]

check("removed_by gap → PITFALL",
      pm.severity_for_missing_relationship(group, "removed_by") == "PITFALL")
check("installed_by gap → PITFALL",
      pm.severity_for_missing_relationship(group, "installed_by") == "PITFALL")
check("documented_in gap → not PITFALL",
      pm.severity_for_missing_relationship(group, "documented_in") != "PITFALL")
check("documented_in gap → HYGIENE or GOOD_TO_HAVE",
      pm.severity_for_missing_relationship(group, "documented_in") in ("HYGIENE", "GOOD_TO_HAVE"))


# ── Suite 4: confidence upgrade ───────────────────────────────────────────────

print("\n── confidence upgrade ──")

import tempfile, shutil

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    vg  = tmp / ".vibecheck"
    vg.mkdir()

    # Copy drift fixture's project_map.json into temp dir
    shutil.copy(FIXTURE_DRIFT / "project_map.json", vg / "project_map.json")

    # Patch so load_map / save_map use the temp .vibecheck/
    original_map_path = pm.map_path
    pm.map_path = lambda cwd: vg / "project_map.json"

    groups_before = pm.get_artifact_groups(tmp)
    check("confidence starts at seeded",
          groups_before["slash_commands"]["confidence"] == "seeded")
    check("times_confirmed starts at 0",
          groups_before["slash_commands"]["times_confirmed"] == 0)

    promoted = pm.upgrade_group_confidence(
        tmp, "slash_commands",
        evidence_note="bin/init.js copies commands/*.md in commandFiles array"
    )
    check("upgrade returns True (seeded → inferred)", promoted is True)

    groups_after = pm.get_artifact_groups(tmp)
    check("confidence is now inferred",
          groups_after["slash_commands"]["confidence"] == "inferred")
    check("times_confirmed is now 1",
          groups_after["slash_commands"]["times_confirmed"] == 1)
    check("evidence note recorded",
          "bin/init.js copies commands/*.md in commandFiles array"
          in groups_after["slash_commands"]["evidence"])
    check("last_confirmed is set",
          groups_after["slash_commands"]["last_confirmed"] is not None)

    # Second upgrade: inferred → confirmed
    pm.upgrade_group_confidence(tmp, "slash_commands", evidence_note="verified again")
    groups_after2 = pm.get_artifact_groups(tmp)
    check("second upgrade → confirmed",
          groups_after2["slash_commands"]["confidence"] == "confirmed")

    # Third upgrade at max: still increments times_confirmed
    pm.upgrade_group_confidence(tmp, "slash_commands", evidence_note="verified again")
    groups_after3 = pm.get_artifact_groups(tmp)
    check("at max confidence, times_confirmed still increments",
          groups_after3["slash_commands"]["times_confirmed"] == 3)
    check("confidence stays at confirmed (no higher)",
          groups_after3["slash_commands"]["confidence"] == "confirmed")

    pm.map_path = original_map_path


# ── Suite 5: add_inferred_group ───────────────────────────────────────────────

print("\n── add_inferred_group ──")

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    vg  = tmp / ".vibecheck"
    vg.mkdir()

    shutil.copy(FIXTURE_DRIFT / "project_map.json", vg / "project_map.json")

    pm.map_path = lambda cwd: vg / "project_map.json"

    added = pm.add_inferred_group(
        tmp,
        "lib_files",
        {
            "description": "Lib files copied by lifecycle scripts",
            "source_glob": "lib/*.py",
            "installed_by": ["bin/init.js"],
            "removed_by": ["bin/uninstall.js"],
        },
        evidence_note="observed bin/update.js copying lib/*.py"
    )
    check("add_inferred_group returns True", added is True)

    groups = pm.get_artifact_groups(tmp)
    check("lib_files group exists", "lib_files" in groups)
    check("confidence is inferred",
          groups["lib_files"]["confidence"] == "inferred")
    check("must_check populated from known keys",
          "installed_by" in groups["lib_files"]["must_check"])
    check("removed_by in must_check",
          "removed_by" in groups["lib_files"]["must_check"])

    # Adding again should be a no-op
    added2 = pm.add_inferred_group(tmp, "lib_files", {}, "")
    check("adding duplicate returns False", added2 is False)

    pm.map_path = original_map_path


# ── Suite 6: Architecture checks ──────────────────────────────────────────────

print("\n── Architecture checks ──")

import static_checks

# Test Tarjan SCC
graph_cycle = {
    "a.ts": ["b.ts"],
    "b.ts": ["c.ts"],
    "c.ts": ["a.ts"],
    "d.ts": []
}
sccs = static_checks._arch_tarjan_scc(graph_cycle)
check("Tarjan SCC detects a 3-file cycle", len(sccs) == 1)
if len(sccs) == 1:
    check("Cycle contains a.ts", "a.ts" in sccs[0])
    check("Cycle contains b.ts", "b.ts" in sccs[0])
    check("Cycle contains c.ts", "c.ts" in sccs[0])
    check("Cycle does not contain d.ts", "d.ts" not in sccs[0])

# Test Layer Violation
graph_layer = {
    "src/infra/db.ts": ["src/api/auth.ts"],
    "src/api/auth.ts": []
}
layer_findings = static_checks._check_arch_layer_violations(graph_layer)
check("Layer violation detected (infra -> api)", len(layer_findings) == 1)
if len(layer_findings) == 1:
    check("Layer violation identifies src/infra/db.ts", layer_findings[0]["file"] == "src/infra/db.ts")

# Test Dead Files
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    (tmp / "main.ts").write_text("import './a'", encoding="utf-8")
    (tmp / "a.ts").write_text("import './b'", encoding="utf-8")
    (tmp / "b.ts").write_text("", encoding="utf-8")
    (tmp / "dead.ts").write_text("", encoding="utf-8")
    (tmp / "index.ts").write_text("", encoding="utf-8")

    graph_dead = {
        "main.ts": ["a.ts"],
        "a.ts": ["b.ts"],
        "b.ts": [],
        "dead.ts": [],
        "index.ts": []
    }
    dead_findings = static_checks._check_arch_dead_files(graph_dead, tmp)
    check("Dead files detected (dead.ts)", len(dead_findings) == 1, f"got {len(dead_findings)} findings: {dead_findings}")
    if len(dead_findings) == 1:
        check("Dead file is dead.ts", dead_findings[0]["file"] == "dead.ts")




# ── Suite 7: Ecosystem checks ──────────────────────────────────────────────────

print("\n── Ecosystem checks ──")

# 1. Test Zod default/optional ordering
zod_bad = "const schema = z.string().default('x').optional();"
zod_good = "const schema = z.string().optional().default('x');"
zod_findings_bad = static_checks._check_ecosystem_pitfalls(Path("schema.ts"), zod_bad)
zod_findings_good = static_checks._check_ecosystem_pitfalls(Path("schema.ts"), zod_good)
check("Zod ordering bug detected on bad schema", len(zod_findings_bad) == 1)
check("Zod ordering bug NOT detected on good schema", len(zod_findings_good) == 0)

# 2. Test SQLite missing busy_timeout
db_bad = "const db = new Database('file.db');"
db_good = "const db = new Database('file.db'); db.pragma('busy_timeout = 5000');"
db_findings_bad = static_checks._check_ecosystem_pitfalls(Path("db.ts"), db_bad)
db_findings_good = static_checks._check_ecosystem_pitfalls(Path("db.ts"), db_good)
check("SQLite missing busy_timeout detected", len(db_findings_bad) == 1)
check("SQLite busy_timeout present is clean", len(db_findings_good) == 0)

# 3. Test Playwright CDP close leak
pw_bad = "const browser = await connectOverCDP(opts);"
pw_good = "const browser = await connectOverCDP(opts); await browser.close();"
pw_findings_bad = static_checks._check_ecosystem_pitfalls(Path("pw.ts"), pw_bad)
pw_findings_good = static_checks._check_ecosystem_pitfalls(Path("pw.ts"), pw_good)
check("Playwright CDP connection leak detected", len(pw_findings_bad) == 1)
check("Playwright CDP connection close/disconnect is clean", len(pw_findings_good) == 0)

# 4. Test Express server close keep-alive hang
srv_bad = "server.close();"
srv_good = "server.closeAllConnections(); server.close();"
srv_findings_bad = static_checks._check_ecosystem_pitfalls(Path("server.ts"), srv_bad)
srv_findings_good = static_checks._check_ecosystem_pitfalls(Path("server.ts"), srv_good)
check("Express server close keep-alive hang detected", len(srv_findings_bad) == 1)
check("Express server close keep-alive handled is clean", len(srv_findings_good) == 0)


# ── Results ──────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
total = ok + fail
if fail == 0:
    print(f"✅ All {total} tests passed")
else:
    print(f"❌ {fail}/{total} tests FAILED")

sys.exit(0 if fail == 0 else 1)
