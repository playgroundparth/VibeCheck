// Minimal fixture — update.js includes foo.md in the copy list
const commandFiles = ["bar.md", "baz.md", "foo.md"];
for (const f of commandFiles) {
  fs.copyFileSync(`commands/${f}`, `.claude/commands/${f}`);
}
