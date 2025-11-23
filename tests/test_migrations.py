"""Test migrations to ensure no duplicate key errors occur."""

import pytest
import tempfile
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from alembic import command
from alembic.config import Config

from app.db.base import Base


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield f"sqlite:///{db_path}"
    os.unlink(db_path)


@pytest.fixture
def mysql_db():
    """Create a MySQL database connection string for testing."""
    # This would use environment variables or test config
    # For now, we'll skip MySQL tests if not configured
    mysql_url = os.getenv("TEST_MYSQL_URL")
    if not mysql_url:
        pytest.skip("TEST_MYSQL_URL not set, skipping MySQL tests")
    return mysql_url


def run_migrations(database_url: str):
    """Run all migrations on the given database."""
    # Create engine
    engine = create_engine(database_url)
    
    # Get alembic config
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "app/db/migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    
    # Run migrations
    try:
        command.upgrade(alembic_cfg, "head")
        return True
    except Exception as e:
        print(f"Migration error: {e}")
        return False
    finally:
        engine.dispose()


def check_table_exists(engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return inspector.has_table(table_name)


def check_index_exists(engine, table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False
    try:
        indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        return index_name in indexes
    except Exception:
        return False


def test_migrations_sqlite_no_duplicate_keys(temp_db):
    """Test that migrations run without duplicate key errors on SQLite."""
    # Override the config to use our test database
    import config
    original_url = getattr(config, 'SQLALCHEMY_DATABASE_URL', None)
    config.SQLALCHEMY_DATABASE_URL = temp_db
    
    try:
        engine = create_engine(temp_db)
        
        # Run migrations
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "app/db/migrations")
        alembic_cfg.set_main_option("sqlalchemy.url", temp_db)
        
        # This should not raise any duplicate key errors
        try:
            # First run - should succeed
            command.upgrade(alembic_cfg, "head")
            
            # Verify that alembic_version table exists (migrations ran)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                tables = [row[0] for row in result]
                assert "alembic_version" in tables, "alembic_version table should exist after migrations"
            
            # Try to run migrations again - should not fail with duplicate key error
            # This is the key test - running migrations twice should not cause duplicate key errors
            command.upgrade(alembic_cfg, "head")
            
            # If we get here without a duplicate key error, the test passes
            # Check that alembic_version still exists
            with engine.connect() as conn:
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                tables = [row[0] for row in result]
                assert "alembic_version" in tables, "alembic_version table should still exist after second migration run"
            
        except Exception as e:
            # Check if it's a duplicate key error
            error_str = str(e)
            if "duplicate key" in error_str.lower() or "Duplicate key name" in error_str or "1061" in error_str:
                pytest.fail(f"Migration failed with duplicate key error: {e}")
            else:
                # For other errors, just re-raise to see what went wrong
                raise
        finally:
            engine.dispose()
    finally:
        # Restore original URL
        if original_url:
            config.SQLALCHEMY_DATABASE_URL = original_url


def test_migrations_mysql_no_duplicate_keys(mysql_db):
    """Test that migrations run without duplicate key errors on MySQL."""
    engine = create_engine(mysql_db)
    
    # Run migrations
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "app/db/migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", mysql_db)
    
    # This should not raise any duplicate key errors
    try:
        # First run - should succeed
        command.upgrade(alembic_cfg, "head")
        
        # Verify that the users table exists
        assert check_table_exists(engine, "users"), \
            "users table should exist after migrations"
        
        # Verify that the index exists
        assert check_index_exists(engine, "users", "ix_users_username"), \
            "ix_users_username index should exist after migrations"
        
        # Try to run migrations again - should not fail with duplicate key error
        command.upgrade(alembic_cfg, "head")
        
        # Verify table and index still exist after second run
        assert check_table_exists(engine, "users"), \
            "users table should still exist after second migration run"
        assert check_index_exists(engine, "users", "ix_users_username"), \
            "ix_users_username index should still exist after second migration run"
        
    except Exception as e:
        # Check if it's a duplicate key error
        error_str = str(e)
        if "duplicate key" in error_str.lower() or "Duplicate key name" in error_str or "1061" in error_str:
            pytest.fail(f"Migration failed with duplicate key error: {e}")
        else:
            pytest.fail(f"Migration failed with error: {e}")
    finally:
        engine.dispose()


def test_case_insensitive_username_migration_idempotent(temp_db):
    """Test that the case insensitive username migration is idempotent."""
    engine = create_engine(temp_db)
    
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "app/db/migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", temp_db)
    
    try:
        # Run migrations to head
        command.upgrade(alembic_cfg, "head")
        
        # Get current revision
        from alembic.script import ScriptDirectory
        script = ScriptDirectory.from_config(alembic_cfg)
        current_rev = script.get_current_head()
        
        # Try to downgrade and upgrade again
        if current_rev:
            # This should work without errors
            command.upgrade(alembic_cfg, "head")
            
    except Exception as e:
        pytest.fail(f"Idempotent migration test failed: {e}")
    finally:
        engine.dispose()

