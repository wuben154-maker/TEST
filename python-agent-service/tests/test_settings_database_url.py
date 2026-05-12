from app.config.settings import Settings


def test_database_url_is_none_in_supabase_mode():
    s = Settings(database_mode="supabase", supabase_url="https://example.supabase.co")
    assert s.database_url is None


def test_database_url_is_none_in_memory_mode():
    s = Settings(database_mode="memory")
    assert s.database_url is None


def test_database_url_is_postgres_dsn_in_local_mode():
    s = Settings(
        database_mode="local",
        local_db_host="localhost",
        local_db_port=5432,
        local_db_name="secmanus",
        local_db_user="postgres",
        local_db_password="postgres",
    )
    assert s.database_url == "postgresql://postgres:postgres@localhost:5432/secmanus"

