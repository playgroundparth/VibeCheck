// Fixture: init.js includes foo.md
const commandFiles = ["bar.md", "baz.md", "foo.md"];
for (const f of commandFiles) {
  copyFile(`commands/${f}`, `.claude/commands/${f}`);
}
