#!/bin/bash
# Safe poetry wrapper that fixes lock file issues automatically

# Pass all arguments to poetry
poetry "$@"
POETRY_EXIT_CODE=$?

# If the command was 'lock' or 'install' and it succeeded, run the fix
if [[ "$1" == "lock" || "$1" == "install" ]] && [ $POETRY_EXIT_CODE -eq 0 ]; then
    ./fix_poetry_lock.sh
fi

# If the command was 'install' and the fix was applied, run install again
if [[ "$1" == "install" ]] && grep -q "Fixed empty constraints" <<< "$FIX_OUTPUT"; then
    echo "Re-running poetry install with fixed lock file..."
    poetry install
fi

exit $POETRY_EXIT_CODE