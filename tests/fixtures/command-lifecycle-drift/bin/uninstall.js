// Minimal fixture — uninstall.js is MISSING foo.md (the bug)
const commandFiles = ["bar.md", "baz.md"];  // foo.md omitted
for (const f of commandFiles) {
  fs.rmSync(`.claude/commands/${f}`);
}
