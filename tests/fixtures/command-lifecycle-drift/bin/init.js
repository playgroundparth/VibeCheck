// Minimal fixture — init.js includes foo.md in the install list
const commandFiles = ["bar.md", "baz.md", "foo.md"];
for (const f of commandFiles) {
  copyFile(`commands/${f}`, `.claude/commands/${f}`);
}
