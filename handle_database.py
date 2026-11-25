"""Typed access to MechBot's normalized SQLite database.

Every function takes an already-open cursor. Async helpers are for aiosqlite
cursors, ``*_sync`` helpers for sqlite3 cursors.
"""

# name -> columns, used for dumps of whole tables (e.g. the $debug command)
TABLES = {
    'permitted': ('user_id',),
    'lvl_roles': ('level', 'role_id'),
    'invites': ('member_id', 'invite_code', 'inviter_name', 'inviter_id'),
    'money': ('user_id', 'amount'),
    'xp': ('user_id', 'amount'),
    'temp_xp': ('user_id', 'amount'),
    'shop': ('name', 'price', 'role_id', 'description', 'returnable'),
    'xp_blacklist': ('channel_id',),
    'xp_channel_settings': ('channel_id', 'multiplier'),
    'xp_category_settings': ('category_id', 'multiplier'),
    'locales': ('user_id', 'locale'),
    'alert_channel': ('id', 'channel_id'),
}

UPSERT = "INSERT INTO {table} ({columns}) VALUES ({placeholders}) " \
         "ON CONFLICT({key}) DO UPDATE SET {updates}"


def _upsert_sql(table, columns, key):
    return UPSERT.format(
        table=table,
        columns=', '.join(columns),
        placeholders=', '.join('?' for _ in columns),
        key=key,
        updates=', '.join(f'{column} = excluded.{column}' for column in columns if column != key),
    )


def _shop_rows(rows):
    return {
        name: {
            'price': price,
            'role_id': role_id,
            'description': description,
            'returnable': bool(returnable),
        }
        for name, price, role_id, description, returnable in rows
    }


# ========== permitted ========== #

async def get_permitted(cursor):
    await cursor.execute("SELECT user_id FROM permitted ORDER BY user_id")
    return [row[0] for row in await cursor.fetchall()]


def get_permitted_sync(cursor):
    cursor.execute("SELECT user_id FROM permitted ORDER BY user_id")
    return [row[0] for row in cursor.fetchall()]


async def add_permitted(cursor, user_id):
    await cursor.execute("INSERT OR IGNORE INTO permitted (user_id) VALUES (?)", (int(user_id),))


def add_permitted_sync(cursor, user_id):
    cursor.execute("INSERT OR IGNORE INTO permitted (user_id) VALUES (?)", (int(user_id),))


# ========== lvl_roles ========== #

async def get_lvl_roles(cursor):
    await cursor.execute("SELECT level, role_id FROM lvl_roles")
    return {str(level): role_id for level, role_id in await cursor.fetchall()}


async def get_lvl_role(cursor, level):
    await cursor.execute("SELECT role_id FROM lvl_roles WHERE level = ?", (int(level),))
    row = await cursor.fetchone()
    return row[0] if row else None


async def set_lvl_role(cursor, level, role_id):
    await cursor.execute(
        _upsert_sql('lvl_roles', ('level', 'role_id'), 'level'),
        (int(level), int(role_id)),
    )


async def clear_lvl_roles(cursor):
    await cursor.execute("DELETE FROM lvl_roles")


# ========== invites ========== #

async def get_invite(cursor, member_id):
    """Returns [invite_code, inviter_name, inviter_id] or None."""
    await cursor.execute(
        "SELECT invite_code, inviter_name, inviter_id FROM invites WHERE member_id = ?",
        (int(member_id),),
    )
    row = await cursor.fetchone()
    return list(row) if row else None


async def get_invites(cursor):
    await cursor.execute("SELECT member_id, invite_code, inviter_name, inviter_id FROM invites")
    return {
        str(member_id): [code, inviter_name, inviter_id]
        for member_id, code, inviter_name, inviter_id in await cursor.fetchall()
    }


async def set_invite(cursor, member_id, invite_code, inviter_name, inviter_id):
    await cursor.execute(
        _upsert_sql('invites', ('member_id', 'invite_code', 'inviter_name', 'inviter_id'), 'member_id'),
        (int(member_id), str(invite_code), str(inviter_name), int(inviter_id)),
    )


async def delete_invite(cursor, member_id):
    await cursor.execute("DELETE FROM invites WHERE member_id = ?", (int(member_id),))


# ========== money ========== #

async def get_balance(cursor, user_id):
    await cursor.execute("SELECT amount FROM money WHERE user_id = ?", (int(user_id),))
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_balances(cursor):
    await cursor.execute("SELECT user_id, amount FROM money")
    return {str(user_id): amount for user_id, amount in await cursor.fetchall()}


async def set_money(cursor, user_id, amount):
    await cursor.execute(
        _upsert_sql('money', ('user_id', 'amount'), 'user_id'),
        (int(user_id), int(amount)),
    )


async def add_money(cursor, user_id, amount):
    """Apply a delta atomically and return the resulting balance."""
    await cursor.execute(
        "INSERT INTO money (user_id, amount) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET amount = money.amount + excluded.amount",
        (int(user_id), int(amount)),
    )
    return await get_balance(cursor, user_id)


async def delete_money(cursor, user_id):
    await cursor.execute("DELETE FROM money WHERE user_id = ?", (int(user_id),))


# ========== xp / temp_xp ========== #

async def get_xp(cursor, user_id):
    await cursor.execute("SELECT amount FROM xp WHERE user_id = ?", (int(user_id),))
    row = await cursor.fetchone()
    return row[0] if row else 0.0


async def get_all_xp(cursor):
    await cursor.execute("SELECT user_id, amount FROM xp")
    return {str(user_id): amount for user_id, amount in await cursor.fetchall()}


async def set_xp(cursor, user_id, amount):
    await cursor.execute(
        _upsert_sql('xp', ('user_id', 'amount'), 'user_id'),
        (int(user_id), float(amount)),
    )


async def add_xp(cursor, user_id, amount):
    """Apply a delta atomically and return the resulting xp."""
    await cursor.execute(
        "INSERT INTO xp (user_id, amount) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET amount = xp.amount + excluded.amount",
        (int(user_id), float(amount)),
    )
    return await get_xp(cursor, user_id)


async def clear_xp(cursor):
    await cursor.execute("DELETE FROM xp")


async def get_temp_xp(cursor, user_id):
    await cursor.execute("SELECT amount FROM temp_xp WHERE user_id = ?", (int(user_id),))
    row = await cursor.fetchone()
    return row[0] if row else 0.0


async def set_temp_xp(cursor, user_id, amount):
    await cursor.execute(
        _upsert_sql('temp_xp', ('user_id', 'amount'), 'user_id'),
        (int(user_id), float(amount)),
    )


async def clear_temp_xp(cursor):
    await cursor.execute("DELETE FROM temp_xp")


# ========== alert_channel ========== #

async def get_alert_channel(cursor):
    await cursor.execute("SELECT channel_id FROM alert_channel WHERE id = 1")
    row = await cursor.fetchone()
    return row[0] if row else None


async def set_alert_channel(cursor, channel_id):
    await cursor.execute(
        "INSERT INTO alert_channel (id, channel_id) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET channel_id = excluded.channel_id",
        (int(channel_id),),
    )


# ========== shop ========== #

SHOP_SELECT = "SELECT name, price, role_id, description, returnable FROM shop"

async def get_shop(cursor):
    await cursor.execute(SHOP_SELECT)
    return _shop_rows(await cursor.fetchall())


def get_shop_sync(cursor):
    cursor.execute(SHOP_SELECT)
    return _shop_rows(cursor.fetchall())


async def get_shop_item(cursor, name):
    await cursor.execute(SHOP_SELECT + " WHERE name = ?", (str(name).lower(),))
    rows = await cursor.fetchall()
    shop = _shop_rows(rows)
    return shop.get(str(name).lower())


async def set_shop_item(cursor, name, price, role_id, description, returnable):
    await cursor.execute(
        _upsert_sql(
            'shop',
            ('name', 'price', 'role_id', 'description', 'returnable'),
            'name',
        ),
        (
            str(name).lower(),
            int(price),
            int(role_id) if role_id is not None else None,
            str(description),
            int(bool(returnable)),
        ),
    )


async def remove_shop_item(cursor, name):
    await cursor.execute("DELETE FROM shop WHERE name = ?", (str(name).lower(),))


# ========== xp settings ========== #

async def get_xp_channel_settings(cursor):
    await cursor.execute("SELECT channel_id, multiplier FROM xp_channel_settings")
    return {str(channel_id): multiplier for channel_id, multiplier in await cursor.fetchall()}


async def get_xp_channel_multiplier(cursor, channel_id):
    await cursor.execute(
        "SELECT multiplier FROM xp_channel_settings WHERE channel_id = ?",
        (int(channel_id),),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def set_xp_channel_multiplier(cursor, channel_id, multiplier):
    if multiplier is None:
        await cursor.execute(
            "DELETE FROM xp_channel_settings WHERE channel_id = ?",
            (int(channel_id),),
        )
    else:
        await cursor.execute(
            _upsert_sql('xp_channel_settings', ('channel_id', 'multiplier'), 'channel_id'),
            (int(channel_id), float(multiplier)),
        )


async def get_xp_category_settings(cursor):
    await cursor.execute("SELECT category_id, multiplier FROM xp_category_settings")
    return {str(category_id): multiplier for category_id, multiplier in await cursor.fetchall()}


async def get_xp_category_multiplier(cursor, category_id):
    await cursor.execute(
        "SELECT multiplier FROM xp_category_settings WHERE category_id = ?",
        (int(category_id),),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def set_xp_category_multiplier(cursor, category_id, multiplier):
    if multiplier is None:
        await cursor.execute(
            "DELETE FROM xp_category_settings WHERE category_id = ?",
            (int(category_id),),
        )
    else:
        await cursor.execute(
            _upsert_sql('xp_category_settings', ('category_id', 'multiplier'), 'category_id'),
            (int(category_id), float(multiplier)),
        )


# ========== xp_blacklist ========== #

async def get_xp_blacklist(cursor):
    await cursor.execute("SELECT channel_id FROM xp_blacklist")
    return [row[0] for row in await cursor.fetchall()]


async def is_xp_blacklisted(cursor, channel_id):
    await cursor.execute(
        "SELECT 1 FROM xp_blacklist WHERE channel_id = ?",
        (int(channel_id),),
    )
    return await cursor.fetchone() is not None


async def set_xp_blacklisted(cursor, channel_id, blacklisted):
    if blacklisted:
        await cursor.execute(
            "INSERT OR IGNORE INTO xp_blacklist (channel_id) VALUES (?)",
            (int(channel_id),),
        )
    else:
        await cursor.execute(
            "DELETE FROM xp_blacklist WHERE channel_id = ?",
            (int(channel_id),),
        )


# ========== locales ========== #

async def get_locale(cursor, user_id):
    await cursor.execute("SELECT locale FROM locales WHERE user_id = ?", (int(user_id),))
    row = await cursor.fetchone()
    return row[0] if row else 'pl'


async def set_locale(cursor, user_id, locale):
    await cursor.execute(
        _upsert_sql('locales', ('user_id', 'locale'), 'user_id'),
        (int(user_id), str(locale)),
    )


# ========== generic table dumps ========== #

async def get_tables(cursor):
    await cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in await cursor.fetchall()]


async def get_table_snapshot(cursor, table):
    """Return the contents of a known table in a printable shape."""
    if table not in TABLES:
        return None

    columns = TABLES[table]
    await cursor.execute(f"SELECT {', '.join(columns)} FROM {table}")
    rows = await cursor.fetchall()

    if len(columns) == 1:
        return [row[0] for row in rows]
    if len(columns) == 2:
        return {str(row[0]): row[1] for row in rows}
    return {str(row[0]): list(row[1:]) for row in rows}
