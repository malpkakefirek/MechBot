"""Schema for MechBot's SQLite database.

Every former key of the old ``mechy`` JSON blob now lives in its own table
with properly typed columns. See ``migrate_database.py`` for the one-time
migration from the legacy single-table database.
"""

TABLE_DEFINITIONS = (
    """
    CREATE TABLE IF NOT EXISTS permitted (
        user_id INTEGER PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lvl_roles (
        level INTEGER PRIMARY KEY,
        role_id INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invites (
        member_id INTEGER PRIMARY KEY,
        invite_code TEXT NOT NULL,
        inviter_name TEXT NOT NULL,
        inviter_id INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS money (
        user_id INTEGER PRIMARY KEY,
        amount INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xp (
        user_id INTEGER PRIMARY KEY,
        amount REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS temp_xp (
        user_id INTEGER PRIMARY KEY,
        amount REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shop (
        name TEXT PRIMARY KEY,
        price INTEGER NOT NULL,
        role_id INTEGER,
        description TEXT NOT NULL,
        returnable INTEGER NOT NULL CHECK (returnable IN (0, 1))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xp_blacklist (
        channel_id INTEGER PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xp_channel_settings (
        channel_id INTEGER PRIMARY KEY,
        multiplier REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xp_category_settings (
        category_id INTEGER PRIMARY KEY,
        multiplier REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS locales (
        user_id INTEGER PRIMARY KEY,
        locale TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_channel (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        channel_id INTEGER NOT NULL
    )
    """,
)


def create_tables(conn):
    """Create every table if it doesn't exist yet."""
    cursor = conn.cursor()
    for definition in TABLE_DEFINITIONS:
        cursor.execute(definition)
    conn.commit()
    cursor.close()


def initialize_database(conn):
    """Prepare the database for the bot and print a short row-count summary."""
    create_tables(conn)

    cursor = conn.cursor()
    print("\n==============================")
    print("DATABASE READY:")
    for definition in TABLE_DEFINITIONS:
        # The first identifier after CREATE TABLE IF NOT EXISTS is the name.
        table = definition.split("IF NOT EXISTS", 1)[1].strip().split(None, 1)[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"{table} — {cursor.fetchone()[0]} rows")
    cursor.close()
    print("==============================\n")
