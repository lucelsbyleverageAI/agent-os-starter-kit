"""Test Docker sandbox session persistence."""

import asyncio
import pytest
from mcp_server.tools.nhs_analytics.docker_sandbox import DockerLocalSandbox


@pytest.mark.asyncio
async def test_session_persistence():
    """Test that variables persist between executions in the same sandbox."""

    # Create sandbox
    sandbox = await DockerLocalSandbox.create(
        timeout=60,
        metadata={"test": "session_persistence"}
    )

    try:
        # First execution: Create variables
        code1 = """
import pandas as pd

# Create some variables
x = 42
data = {'a': [1, 2, 3], 'b': [4, 5, 6]}
df = pd.DataFrame(data)

print(f"Created: x={x}, df.shape={df.shape}")
"""
        result1 = await sandbox.run_code(code1)

        assert result1.error is None, f"First execution failed: {result1.error}"
        assert any("Created: x=42" in line for line in result1.logs.stdout), "First execution output not found"
        assert any("Starting fresh session" in line for line in result1.logs.stdout), "Fresh session message not found"

        # Second execution: Use variables from first execution
        code2 = """
# Variables from previous execution should still exist
print(f"Retrieved: x={x}, df.shape={df.shape}")
print(f"df sum: {df['a'].sum()}")

# Modify existing variable
x = x * 2
print(f"Modified: x={x}")
"""
        result2 = await sandbox.run_code(code2)

        assert result2.error is None, f"Second execution failed: {result2.error}"
        assert any("Retrieved: x=42" in line for line in result2.logs.stdout), "Variable x not persisted"
        assert any("df.shape=(3, 2)" in line for line in result2.logs.stdout), "DataFrame not persisted"
        assert any("df sum: 6" in line for line in result2.logs.stdout), "DataFrame computation failed"
        assert any("Modified: x=84" in line for line in result2.logs.stdout), "Variable modification failed"
        assert any("Restored state from previous execution" in line for line in result2.logs.stdout), "State restoration message not found"

        # Third execution: Verify modified state persisted
        code3 = """
print(f"Final check: x={x}")
assert x == 84, f"Expected x=84, got x={x}"
print("✅ Session persistence verified!")
"""
        result3 = await sandbox.run_code(code3)

        assert result3.error is None, f"Third execution failed: {result3.error}"
        assert any("Final check: x=84" in line for line in result3.logs.stdout), "Modified variable not persisted"
        assert any("✅ Session persistence verified!" in line for line in result3.logs.stdout), "Final verification failed"

        print("✅ All session persistence tests passed!")

    finally:
        # Cleanup
        await sandbox.kill()


@pytest.mark.asyncio
async def test_imports_persist():
    """Test that imports persist between executions."""

    sandbox = await DockerLocalSandbox.create(
        timeout=60,
        metadata={"test": "imports_persist"}
    )

    try:
        # First execution: Import libraries
        code1 = """
import pandas as pd
import numpy as np

print("Imported pandas and numpy")
"""
        result1 = await sandbox.run_code(code1)
        assert result1.error is None

        # Second execution: Use imports without re-importing
        code2 = """
# Should be able to use pd and np without importing again
arr = np.array([1, 2, 3])
df = pd.DataFrame({'values': arr})
print(f"Created DataFrame with shape {df.shape} using persisted imports")
"""
        result2 = await sandbox.run_code(code2)
        assert result2.error is None
        assert any("Created DataFrame with shape (3, 1)" in line for line in result2.logs.stdout)

        print("✅ Import persistence test passed!")

    finally:
        await sandbox.kill()


@pytest.mark.asyncio
async def test_error_doesnt_break_persistence():
    """Test that errors don't break session persistence."""

    sandbox = await DockerLocalSandbox.create(
        timeout=60,
        metadata={"test": "error_handling"}
    )

    try:
        # First execution: Create variable
        code1 = "x = 100"
        result1 = await sandbox.run_code(code1)
        assert result1.error is None

        # Second execution: Cause an error
        code2 = """
y = x + 50
z = undefined_variable  # This will cause NameError
"""
        result2 = await sandbox.run_code(code2)
        assert result2.error is not None  # Should have error

        # Third execution: Verify state persisted despite error
        code3 = """
print(f"x = {x}")
print(f"y = {y}")
print("State persisted despite previous error!")
"""
        result3 = await sandbox.run_code(code3)
        assert result3.error is None
        assert any("x = 100" in line for line in result3.logs.stdout)
        assert any("y = 150" in line for line in result3.logs.stdout)

        print("✅ Error handling test passed!")

    finally:
        await sandbox.kill()


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_session_persistence())
    asyncio.run(test_imports_persist())
    asyncio.run(test_error_doesnt_break_persistence())
    print("\n✅ All Docker sandbox persistence tests passed!")
