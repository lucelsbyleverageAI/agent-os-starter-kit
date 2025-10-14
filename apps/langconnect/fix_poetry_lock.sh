#!/bin/bash
# Fix Poetry lock file issue with empty version constraints

# Check if poetry.lock exists
if [ -f "poetry.lock" ]; then
    # Fix any <empty> constraints
    if grep -q "<empty>" poetry.lock; then
        echo "Fixing empty version constraints in poetry.lock..."
        sed -i '' 's/"optax (<empty>)"/"optax"/g' poetry.lock
        echo "Fixed empty constraints in poetry.lock"
    else
        echo "No empty constraints found in poetry.lock"
    fi
else
    echo "poetry.lock not found"
fi