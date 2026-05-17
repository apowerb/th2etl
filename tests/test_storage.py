import pytest
from th2etl.storage.database import DatabaseStorage, BlocRecord

# For this example, we'll use an in-memory SQLite database for testing.
# In a real-world scenario, you might use a test-specific PostgreSQL database.
DSN = "postgresql://user:password@localhost:5432/testdb"

@pytest.fixture
def db():
    """Fixture to set up and tear down the database for each test."""
    storage = DatabaseStorage(dsn=DSN)
    # In a real test setup, you'd want to clear the tables before each test.
    # For this example, we'll rely on a clean test database.
    yield storage
    storage.close()

def test_create_and_get_bloc(db: DatabaseStorage):
    """Test creating a bloc and then retrieving it."""
    bloc_name = "test_bloc"
    db.create_bloc(
        name=bloc_name,
        bloc_type="test_type",
        dependencies=[],
        config={},
        description="A test bloc",
    )

    retrieved_bloc = db.get_bloc(bloc_name)
    assert retrieved_bloc is not None
    assert retrieved_bloc.name == bloc_name
    assert retrieved_bloc.bloc_type == "test_type"

def test_get_nonexistent_bloc(db: DatabaseStorage):
    """Test that getting a nonexistent bloc returns None."""
    retrieved_bloc = db.get_bloc("nonexistent_bloc")
    assert retrieved_bloc is None
