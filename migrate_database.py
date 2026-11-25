"""One-time migration from the legacy single-table (JSON) database.

Run with:  python migrate_database.py

A backup of the database is created before any data is touched. The old
``mechy`` table is dropped only after every row has been copied and verified.
"""

import json
import os
import shutil
import sqlite3
from datetime import datetime

from initialize_database import create_tables

DB_PATH = 'mechbot.db'
BACKUP_PATH = 'mechbot.db.bak'


def backup_database(db_path=DB_PATH, backup_path=BACKUP_PATH):
    """Copy the database before migrating it. Never overwrites an old backup."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    if os.path.exists(backup_path):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        root, ext = os.path.splitext(backup_path)
        backup_path = f"{root}_{stamp}{ext}"

    shutil.copy2(db_path, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def _decode(raw):
    """Old values were usually JSON strings; alert_channel was stored raw."""
    return json.loads(raw) if isinstance(raw, str) else raw


def migrate_database(conn):
    """Move each key/value from ``mechy`` into its own typed table."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'mechy'")
    if not cursor.fetchone():
        print("No legacy 'mechy' table found — nothing to migrate.")
        return False

    legacy = {key: _decode(value) for key, value in cursor.execute("SELECT key, value FROM mechy")}
    create_tables(conn)

    expected = {}

    # INSERT OR IGNORE keeps one row per id, so legacy lists with repeated ids
    # must be verified by DISTINCT ids rather than raw list lengths.
    ignored_id_columns = {
        'permitted': 'user_id',
        'xp_blacklist': 'channel_id',
    }

    def count(table, amount):
        expected[table] = amount

    # permitted — list of user ids
    permitted_ids = {int(user_id) for user_id in (legacy.get('permitted') or [])}
    for user_id in permitted_ids:
        cursor.execute("INSERT OR IGNORE INTO permitted (user_id) VALUES (?)", (user_id,))
    count('permitted', len(permitted_ids))

    # lvl_roles — level -> role id
    lvl_roles = legacy.get('lvl_roles') or {}
    for level, role_id in lvl_roles.items():
        cursor.execute(
            "INSERT OR REPLACE INTO lvl_roles (level, role_id) VALUES (?, ?)",
            (int(level), int(role_id)),
        )
    count('lvl_roles', len(lvl_roles))

    # invites — member id -> [code, inviter name, inviter id].
    # A few old entries were just empty guild placeholders ({}); they hold no data.
    invites = legacy.get('invites') or {}
    migrated_invites = 0
    for member_id, invite in invites.items():
        if not isinstance(invite, list) or len(invite) < 3:
            continue
        cursor.execute(
            "INSERT OR REPLACE INTO invites (member_id, invite_code, inviter_name, inviter_id) "
            "VALUES (?, ?, ?, ?)",
            (int(member_id), str(invite[0]), str(invite[1]), int(invite[2])),
        )
        migrated_invites += 1
    count('invites', migrated_invites)

    # money — user id -> amount (int)
    money = legacy.get('money') or {}
    for user_id, amount in money.items():
        cursor.execute(
            "INSERT OR REPLACE INTO money (user_id, amount) VALUES (?, ?)",
            (int(user_id), int(float(amount))),
        )
    count('money', len(money))

    # xp / temp_xp — user id -> amount (float)
    for table in ('xp', 'temp_xp'):
        values = legacy.get(table) or {}
        for user_id, amount in values.items():
            cursor.execute(
                f"INSERT OR REPLACE INTO {table} (user_id, amount) VALUES (?, ?)",
                (int(user_id), float(amount)),
            )
        count(table, len(values))

    # shop — item name -> {price, role_id, description, returnable}
    shop = legacy.get('shop') or {}
    for name, details in shop.items():
        role_id = details.get('role_id')
        cursor.execute(
            "INSERT OR REPLACE INTO shop (name, price, role_id, description, returnable) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(name).lower(),
                int(details['price']),
                int(role_id) if role_id is not None else None,
                str(details.get('description', '')),
                int(bool(details.get('returnable', True))),
            ),
        )
    count('shop', len(shop))

    # xp_blacklist — list of channel ids
    blacklist_ids = {int(channel_id) for channel_id in (legacy.get('xp_blacklist') or [])}
    for channel_id in blacklist_ids:
        cursor.execute(
            "INSERT OR IGNORE INTO xp_blacklist (channel_id) VALUES (?)",
            (channel_id,),
        )
    count('xp_blacklist', len(blacklist_ids))

    # xp multipliers — id -> float
    for table, key_column in (
        ('xp_channel_settings', 'channel_id'),
        ('xp_category_settings', 'category_id'),
    ):
        values = legacy.get(table) or {}
        for identifier, multiplier in values.items():
            cursor.execute(
                f"INSERT OR REPLACE INTO {table} ({key_column}, multiplier) VALUES (?, ?)",
                (int(identifier), float(multiplier)),
            )
        count(table, len(values))

    # locales — user id -> language code
    locales = legacy.get('locales') or {}
    for user_id, locale in locales.items():
        cursor.execute(
            "INSERT OR REPLACE INTO locales (user_id, locale) VALUES (?, ?)",
            (int(user_id), str(locale)),
        )
    count('locales', len(locales))

    # alert_channel — single scalar value
    alert_channel = legacy.get('alert_channel')
    if alert_channel is not None and str(alert_channel).upper() != 'NULL':
        cursor.execute(
            "INSERT OR REPLACE INTO alert_channel (id, channel_id) VALUES (1, ?)",
            (int(alert_channel),),
        )
        count('alert_channel', 1)
    else:
        count('alert_channel', 0)

    # Keep inserts and verification in one transaction: a failed check rolls
    # everything back, leaving mechy as the untouched source of truth.

    # Verify before removing the source of truth. Tables populated with
    # INSERT OR IGNORE are checked with DISTINCT ids so duplicates in the
    # legacy data cannot abort an otherwise successful migration.
    for table, amount in expected.items():
        id_column = ignored_id_columns.get(table)
        counting = f"COUNT(DISTINCT {id_column})" if id_column else "COUNT(*)"
        actual = cursor.execute(f"SELECT {counting} FROM {table}").fetchone()[0]
        if actual != amount:
            raise RuntimeError(
                f"Migration check failed for {table}: expected {amount} rows, got {actual}. "
                "The old table was kept; restore the backup if needed."
            )
        print(f"{table}: {actual} rows")

    cursor.execute("DROP TABLE mechy")
    conn.commit()
    print("\nMigration complete — legacy 'mechy' table removed.")
    return True


if __name__ == '__main__':
    backup_database()
    with sqlite3.connect(DB_PATH) as connection:
        migrate_database(connection)
