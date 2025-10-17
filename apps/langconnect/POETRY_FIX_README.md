# Poetry Lock File Fix for Empty Constraints Issue

## Problem
When using Poetry 2.1.2 with certain packages (like `unstructured` and `mem0ai` that depend on `transformers`), Poetry generates malformed lock files with `<empty>` version constraints. This causes the error:
```
Could not parse version constraint: <empty>
```

This happens because `transformers` has optional dependencies (like `optax`) with no version specified, and Poetry 2.1.2 has a bug handling these.

## Root Cause
- **Poetry Version**: 2.1.2 has a known bug with empty version constraints
- **Problematic Packages**:
  - `transformers` (pulled in by `unstructured` and `mem0ai`)
  - Has optional dependencies with unspecified versions (`optax`, etc.)

## Solutions Implemented

### 1. Automatic Fix Script (`fix_poetry_lock.sh`)
Automatically fixes `<empty>` constraints in the lock file:
```bash
./fix_poetry_lock.sh
```

### 2. Poetry Wrapper Script (`poetry-safe.sh`)
Runs poetry commands and automatically fixes the lock file:
```bash
./poetry-safe.sh install
./poetry-safe.sh lock
```

### 3. Shell Aliases (`.poetry_aliases`)
Load convenient aliases in your shell:
```bash
source .poetry_aliases

# Then use:
poetry-lock     # Run poetry lock and fix
poetry-install  # Fix then install
poetry-update   # Update and fix
```

## How to Use

### Quick Fix (One-time)
```bash
./fix_poetry_lock.sh && poetry install
```

### For Repeated Use
Add to your shell profile (`.bashrc`, `.zshrc`, etc.):
```bash
alias poetry-install='cd /path/to/langconnect && ./fix_poetry_lock.sh && poetry install'
```

Or source the aliases:
```bash
source /path/to/langconnect/.poetry_aliases
```

## Long-term Solution
Consider upgrading Poetry to version 2.2+ where this bug is fixed:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

## If the Issue Persists
1. Delete `poetry.lock`
2. Run `poetry lock`
3. Run `./fix_poetry_lock.sh`
4. Run `poetry install`

## Technical Details
The issue occurs in these lines of `poetry.lock`:
- Lines around 6566, 6573, 6576 containing `"optax (<empty>)"`
- The fix replaces all instances of `"optax (<empty>)"` with `"optax"`