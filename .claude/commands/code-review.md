# Code Review

Review all modified files from git diff and check for design pattern violations, efficiency issues, and security problems.

## Step 1 — Collect the diff

Run:
```bash
git diff HEAD
git diff HEAD --name-only
```

If no output, try `git diff --cached`. If not in a git repo, ask the user to paste the code.

If diff is >500 lines, process one file at a time.

---

## Step 2 — Detect language per file

| Extension | Language |
|---|---|
| `.py` | Python |
| `.js` `.mjs` `.cjs` | JavaScript |
| `.ts` `.tsx` | TypeScript |
| `.jsx` | React |
| `.java` | Java |
| `.go` | Go |
| `.rs` | Rust |
| `.rb` | Ruby |
| `.php` | PHP |
| `.cs` | C# |
| `.cpp` `.cc` `.h` | C++ |
| `.swift` | Swift |
| `.kt` | Kotlin |

Apply language-specific rules below. For unlisted languages, apply universal rules only.

---

## Step 3 — Review across 3 dimensions

### A. Design Patterns

**Universal (all languages)**
- **DRY**: Duplicated logic that should be extracted
- **Single Responsibility**: Functions/classes doing too many things
- **Naming**: Unclear or inconsistent names
- **Magic values**: Hardcoded strings/numbers that should be constants
- **Dead code**: Unused variables, imports, functions
- **Long functions**: >40 lines without clear justification
- **Deep nesting**: >3 levels — suggest early returns or extraction

**OOP (Python, Java, C#, Kotlin, Ruby, PHP, Swift, C++)**
- **SRP**: Class handles business logic AND persistence AND formatting → split it
- **OCP**: Long if/switch chains checking type to decide behavior → suggest polymorphism
- **LSP**: Subclass overrides method with `NotImplementedError` or empty body → flag it
- **ISP**: Fat interfaces where implementors leave half the methods empty → split the interface
- **DIP**: High-level class directly instantiates `new ConcreteDB()` → suggest injection
- **God classes**: One class doing everything → flag for decomposition
- **Inappropriate inheritance**: Favor composition where the subclass relationship isn't a true "is-a"

**JavaScript / TypeScript**
- Mutating state directly instead of returning new values
- Side effects in functions that should be pure
- Callback hell → suggest async/await
- Avoid `any` in TS — use proper types or `unknown` with narrowing

**React / JSX**
- Missing `key` props on lists
- Missing `useMemo`/`useCallback` for expensive computations or callbacks passed as props
- State updates causing unnecessary re-renders

---

### B. Efficiency

**Universal**
- O(n²) patterns: nested loops over the same data — flag and suggest a Map/Set
- Repeated computation inside a loop that could be hoisted out
- N+1 DB queries: query inside a loop → suggest batching
- Fetching/passing more data than needed

**Python**
- String concatenation in loops → use `"".join(list)`
- `range(len(x))` → use `enumerate(x)`
- Building large lists when a generator would do
- `any()`/`all()` preferred over manual boolean loops

**JavaScript / TypeScript**
- `.find()` inside `.map()/.filter()` → O(n²), use a Map instead
- `JSON.parse(JSON.stringify(x))` for cloning → use `structuredClone()`
- Missing debounce/throttle on scroll/resize/input handlers
- Large arrays using `.includes()` for membership checks → use `Set`

---

### C. Security

**Universal**
- **Hardcoded secrets**: API keys, passwords, tokens in source — flag immediately 🔴
- **Injection**: Unsanitized user input in SQL, shell commands, eval, innerHTML
- **Insecure defaults**: Debug mode on, verbose errors exposed to client, weak crypto
- **Broken auth**: Auth checks skipped, tokens not validated, roles not enforced
- **Path traversal**: User-controlled file paths without sanitization
- **Sensitive data in logs**: Passwords, tokens, or PII being logged

**Python**
- `eval()`/`exec()` on user input → always critical 🔴
- `subprocess` with `shell=True` and user input → critical 🔴
- `random` for tokens → use `secrets` module
- f-string SQL queries → use parameterized queries
- `pickle` on untrusted data → arbitrary code execution risk

**JavaScript / TypeScript**
- `innerHTML`/`document.write`/`eval()` with user data → critical 🔴
- Tokens in `localStorage` → use `httpOnly` cookies
- Stack traces or internal errors exposed to client
- Client-side-only validation (always validate server-side too)
- String-concatenated SQL → use parameterized queries

---

## Step 4 — Output format

```
## Code Review — <date>

### Files Reviewed
- path/to/file.py
- path/to/file.ts

---

### 🔴 Critical Issues
**[Security] src/auth.py:42**
> Hardcoded API key in source file.
> Anyone with repo access can use this key.
> Fix: Move to environment variable and add to .gitignore.

### 🟡 Warnings
**[Design] src/user_service.py:10**
> UserService handles DB access, email sending, and validation — violates SRP.
> Fix: Extract EmailService and split validation into a separate validator.

### 🟢 Suggestions
**[Efficiency] src/utils.js:88**
> `.find()` called inside `.map()` — O(n²). Use a Map keyed by ID instead.

---

### Summary
1 critical · 2 warnings · 1 suggestion
Recommendation: Fix critical issues before committing.
```

**Severity:**
- 🔴 Critical: Security vulnerabilities, data loss, crashes — fix before committing
- 🟡 Warning: Design violations, inefficiencies, code smells — fix soon
- 🟢 Suggestion: Minor improvements, optional refactors

---

## Edge Cases

- **Binary / compiled files**: Skip silently
- **Generated files** (`package-lock.json`, `*.min.js`, DB migrations): Note as auto-generated, skip deep review
- **Config files** (`.env.example`, `docker-compose.yml`): Security checks only
- **Test files**: Check for missing assertions, relax design pattern rules
- **Empty diff**: Tell the user and suggest `git diff --cached` or `git status`

---

After the report, offer to help fix any specific issue.
