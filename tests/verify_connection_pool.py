import asyncio
import sys

from orchestrator.db.connection import get_pool


def check_dependencies():
    """Verify required dependencies are installed."""
    try:
        import langchain_core

        print(f"SUCCESS: langchain_core found (version: {langchain_core.__version__})")
    except ImportError:
        print("FAILED: langchain_core not found")
        sys.exit(1)


async def get_pool_id():
    pool = await get_pool("test_project")
    return id(pool)


def test_pool_separation():
    """Test that pools are different for different loops."""
    check_dependencies()

    # Run in loop 1
    loop1_pool_id = asyncio.run(get_pool_id())

    # Run in loop 2
    loop2_pool_id = asyncio.run(get_pool_id())

    print(f"Loop 1 Pool ID: {loop1_pool_id}")
    print(f"Loop 2 Pool ID: {loop2_pool_id}")

    assert loop1_pool_id != loop2_pool_id, "Pools should be different for different event loops"
    print("SUCCESS: Connection pools are correctly scoped to event loops.")


if __name__ == "__main__":
    try:
        test_pool_separation()
    except Exception as e:
        print(f"FAILED: {e}")
        exit(1)
