---
description: How to commit and push implementation changes to GitHub with proper branching
---

# Implementation Update Workflow

Follow these steps after completing each module/feature implementation.

## Steps

1. **Update walkthrough** — update or create `walkthrough.md` in the brain artifacts directory with what was implemented, files created/modified, and key design decisions.

2. **Create feature branch** from master with a descriptive name:
// turbo
```bash
git checkout master
git checkout -b feature/<module-name>
```
Example branch names:
- `feature/module-8-reference-workflow`
- `feature/module-9-test-suite`
- `feature/phase-4a-tech-department`

3. **Stage relevant files** — only add files related to the current implementation:
```bash
git add <specific files and directories>
```

4. **Commit with descriptive message** using conventional commits format:
```bash
git commit -m "feat: <module/feature name>

- Bullet point summary of changes
- Key files created
- Key files modified"
```

5. **Push feature branch**:
// turbo
```bash
git push -u origin feature/<module-name>
```

6. **Merge to master** with --no-ff (no fast-forward) to preserve branch history:
```bash
git checkout master
git merge feature/<module-name> --no-ff -m "Merge feature/<module-name>: <short description>"
```

7. **Push master**:
```bash
git push origin master
```

8. **Update IMPLEMENTATION_ROADMAP.md** — mark completed items with `[x]` and ✅.

## Branch Naming Convention

| Type | Format | Example |
|------|--------|---------|
| Module | `feature/module-N-<name>` | `feature/module-8-reference-workflow` |
| Phase | `feature/phase-4a-<name>` | `feature/phase-4a-tech-department` |
| Fix | `fix/<description>` | `fix/budget-race-condition` |
| Docs | `docs/<description>` | `docs/update-readme` |

## Commit Message Format

```
<type>: <short description>

<optional body with bullet points>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
