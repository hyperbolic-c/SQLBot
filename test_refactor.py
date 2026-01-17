#!/usr/bin/env python
"""
Quick test script to verify the refactored modules can be imported.
Run this inside the Docker container.
"""

def test_imports():
    """Test that all refactored modules can be imported."""
    print("Testing imports...")

    try:
        from apps.business_db.context import (
            AlgorithmContext,
            UserContext,
            DatasourceContext,
            AiModelContext,
            TableSchemaContext,
        )
        print("  [OK] business_db.context")
    except Exception as e:
        print(f"  [FAIL] business_db.context: {e}")
        return False

    try:
        from apps.business_db.result import (
            AlgorithmResult,
            ChatLogCreate,
            ChatUpdate,
        )
        print("  [OK] business_db.result")
    except Exception as e:
        print(f"  [FAIL] business_db.result: {e}")
        return False

    try:
        from apps.business_db.repository import BusinessDBRepository
        print("  [OK] business_db.repository")
    except Exception as e:
        print(f"  [FAIL] business_db.repository: {e}")
        return False

    try:
        from apps.business_db.service import BusinessDBService
        print("  [OK] business_db.service")
    except Exception as e:
        print(f"  [FAIL] business_db.service: {e}")
        return False

    try:
        from apps.algorithm.engine import AlgorithmEngine, StreamEvent
        print("  [OK] algorithm.engine")
    except Exception as e:
        print(f"  [FAIL] algorithm.engine: {e}")
        return False

    return True


def test_context_creation():
    """Test creating AlgorithmContext."""
    print("\nTesting context creation...")

    from apps.business_db.context import (
        AlgorithmContext,
        UserContext,
        DatasourceContext,
    )

    try:
        user_ctx = UserContext(id=1, workspace_id=1, oid=1)
        ds_ctx = DatasourceContext(
            id=1,
            name="test",
            type="PostgreSQL",
            description="",
            configuration="{}",
            table_relation=None,
        )
        ctx = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            user_context=user_ctx,
            question="test question",
            datasource=ds_ctx,
        )
        print("  [OK] AlgorithmContext created successfully")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_engine_initialization():
    """Test AlgorithmEngine initialization."""
    print("\nTesting engine initialization...")

    from apps.algorithm.engine import AlgorithmEngine
    from apps.business_db.context import AlgorithmContext

    try:
        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="test",
        )
        engine = AlgorithmEngine(context)
        print("  [OK] AlgorithmEngine created successfully")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_result_creation():
    """Test AlgorithmResult creation."""
    print("\nTesting result creation...")

    from apps.business_db.result import AlgorithmResult, ChatUpdate

    try:
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            sql="SELECT * FROM users",
        )
        print("  [OK] AlgorithmResult created successfully")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def main():
    print("=" * 60)
    print("Refactored Architecture Verification")
    print("=" * 60)

    all_passed = True

    all_passed &= test_imports()
    all_passed &= test_context_creation()
    all_passed &= test_engine_initialization()
    all_passed &= test_result_creation()

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed!")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
