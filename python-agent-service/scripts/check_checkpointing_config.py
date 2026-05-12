#!/usr/bin/env python3
"""Simple script to check checkpointing configuration.

This script checks:
1. Database configuration
2. Checkpointing settings
3. Dependencies availability
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_dependencies():
    """Check if required dependencies are installed."""
    print("="*60)
    print("1. Checking Dependencies")
    print("="*60)
    
    dependencies = {
        "langgraph-checkpoint-postgres": "langgraph.checkpoint.postgres",
        "langgraph": "langgraph",
        "psycopg": "psycopg",
    }
    
    all_ok = True
    for package_name, import_name in dependencies.items():
        try:
            __import__(import_name)
            print(f"[OK] {package_name} installed")
        except ImportError as e:
            print(f"[FAIL] {package_name} NOT installed")
            if "psycopg" in package_name:
                print(f"  Note: Install psycopg-binary for Windows: pip install psycopg-binary")
            all_ok = False
    
    return all_ok


def check_config():
    """Check configuration settings."""
    print("\n" + "="*60)
    print("2. Checking Configuration")
    print("="*60)
    
    # Check environment variables
    env_vars = {
        "ENABLE_CHECKPOINTING": os.getenv("ENABLE_CHECKPOINTING", "true"),
        "CHECKPOINT_BACKEND": os.getenv("CHECKPOINT_BACKEND", "postgres"),
        "DATABASE_MODE": os.getenv("DATABASE_MODE", "local"),
        "LOCAL_DB_HOST": os.getenv("LOCAL_DB_HOST", "localhost"),
        "LOCAL_DB_PORT": os.getenv("LOCAL_DB_PORT", "5432"),
        "LOCAL_DB_NAME": os.getenv("LOCAL_DB_NAME", "secmanus"),
        "LOCAL_DB_USER": os.getenv("LOCAL_DB_USER", "postgres"),
        "LOCAL_DB_PASSWORD": os.getenv("LOCAL_DB_PASSWORD", ""),
    }
    
    print("Environment Variables:")
    for key, value in env_vars.items():
        if "PASSWORD" in key:
            display_value = "***" if value else "(not set)"
        else:
            display_value = value or "(not set)"
        print(f"  {key}: {display_value}")
    
    # Check checkpointing settings
    enable_checkpointing = env_vars["ENABLE_CHECKPOINTING"].lower() == "true"
    checkpoint_backend = env_vars["CHECKPOINT_BACKEND"]
    
    print(f"\n[OK] Checkpointing enabled: {enable_checkpointing}")
    print(f"[OK] Checkpoint backend: {checkpoint_backend}")
    
    if checkpoint_backend == "postgres":
        db_password = env_vars["LOCAL_DB_PASSWORD"]
        if not db_password:
            print("[WARN] Database password not set (LOCAL_DB_PASSWORD)")
            print("  Checkpointing will fallback to MemorySaver")
            return False
        
        db_url = (
            f"postgresql://{env_vars['LOCAL_DB_USER']}:{db_password}"
            f"@{env_vars['LOCAL_DB_HOST']}:{env_vars['LOCAL_DB_PORT']}"
            f"/{env_vars['LOCAL_DB_NAME']}"
        )
        print(f"[OK] Database URL configured: postgresql://...@{env_vars['LOCAL_DB_HOST']}:{env_vars['LOCAL_DB_PORT']}/{env_vars['LOCAL_DB_NAME']}")
        return True
    else:
        print("[OK] Using MemorySaver (state will be lost on restart)")
        return True


def check_database_connection():
    """Check database connection (if PostgreSQL)."""
    print("\n" + "="*60)
    print("3. Checking Database Connection")
    print("="*60)
    
    checkpoint_backend = os.getenv("CHECKPOINT_BACKEND", "postgres")
    
    if checkpoint_backend != "postgres":
        print("[SKIP] Not using PostgreSQL, skipping database connection test")
        return True
    
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        import asyncio
        
        db_url = (
            f"postgresql://{os.getenv('LOCAL_DB_USER', 'postgres')}:"
            f"{os.getenv('LOCAL_DB_PASSWORD', '')}"
            f"@{os.getenv('LOCAL_DB_HOST', 'localhost')}:"
            f"{os.getenv('LOCAL_DB_PORT', '5432')}/"
            f"{os.getenv('LOCAL_DB_NAME', 'secmanus')}"
        )
        
        print(f"[TEST] Testing connection to: {os.getenv('LOCAL_DB_HOST', 'localhost')}:{os.getenv('LOCAL_DB_PORT', '5432')}")
        
        async def test_connection():
            try:
                checkpointer = PostgresSaver.from_conn_string(db_url)
                # Setup creates table if not exists
                async with checkpointer.setup() as setup_result:
                    print("[OK] Database connection successful")
                    print("[OK] Checkpoint table ready")
                return True
            except Exception as e:
                print(f"[FAIL] Database connection failed: {e}")
                print("\nTroubleshooting:")
                print("  1. Is PostgreSQL running?")
                print("  2. Are credentials correct?")
                print("  3. Can you connect manually?")
                print(f"     psql -h {os.getenv('LOCAL_DB_HOST', 'localhost')} -U {os.getenv('LOCAL_DB_USER', 'postgres')} -d {os.getenv('LOCAL_DB_NAME', 'secmanus')}")
                print("\nNote: Table will be created automatically on first use")
                return False
        
        return asyncio.run(test_connection())
        
    except ImportError as e:
        print("[FAIL] langgraph-checkpoint-postgres not installed")
        print("  Install with: pip install langgraph-checkpoint-postgres")
        print(f"  Error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False


def main():
    """Run all checks."""
    print("\n" + "="*60)
    print("LangGraph Checkpointing Configuration Check")
    print("="*60)
    
    results = []
    
    # Check dependencies
    results.append(check_dependencies())
    
    # Check configuration
    results.append(check_config())
    
    # Check database connection
    results.append(check_database_connection())
    
    # Summary
    print("\n" + "="*60)
    print("Summary")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nChecks passed: {passed}/{total}")
    
    if passed == total:
        print("\n[SUCCESS] All checks passed! Checkpointing is ready to use.")
        print("\nNext steps:")
        print("  1. Start your application")
        print("  2. Checkpointing will automatically save state")
        print("  3. State will persist across server restarts")
    else:
        print("\n[WARN] Some checks failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("  1. Install dependencies: pip install langgraph-checkpoint-postgres")
        print("  2. For Windows, install: pip install psycopg-binary")
        print("  3. Configure database in .env file")
        print("  4. Ensure PostgreSQL is running")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
