# Framework: New External Dependency

**Trigger detection:** new entry in `package.json`, `requirements.txt`, `go.mod`, `Gemfile`, `Cargo.toml`, any new `import` or `require` of a package that wasn't in the project before.

**Questions to ask about the changed code:**

1. What's the bus factor on this package? Is it maintained by one person who might abandon it? Is it widely used enough that security issues will be caught quickly?
2. Is the version pinned? Or will `^1.2.3` silently pull in `1.9.0` in six months with breaking changes?
3. What's the bundle size impact? For frontend packages, is this worth the kilobytes?
4. Is this package doing something you could have done in 10-20 lines without a dependency? The fewer dependencies, the fewer supply-chain attack surfaces.
5. When was this package last updated? Is it actively maintained, or is it abandoned and accumulating unpatched CVEs?
6. Does this package require runtime credentials or network access? If so, what access is it requesting and is that access scoped correctly?

**Red flags (always call out):**
- Package with < 100 weekly downloads or abandoned in the last year
- Package from an organization/account that recently changed ownership (supply chain risk)
- Unversioned install (`npm install pkg` without `--save-exact` or a lockfile)
- Package that duplicates something already in the project under a different name
- Dev dependency installed as a production dependency
