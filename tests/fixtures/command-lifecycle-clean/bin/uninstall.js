// Fixture: uninstall.js includes foo.md (correct — no drift)
const commandFiles = ["bar.md", "baz.md", "foo.md"];
for (const f of commandFiles) {
  fs.rmSync(`.claude/commands/${f}`);
}
