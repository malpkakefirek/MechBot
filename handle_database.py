# import aiosqlite
# import sqlite3
import json


async def select_value(cursor, key):
    await cursor.execute("SELECT value FROM mechy WHERE key = ?", (key, ))
    row = await cursor.fetchone()
    return json.loads(str(row[0]))


async def update_value(cursor, key, value):
    value = json.dumps(value)
    await cursor.execute("UPDATE mechy SET value = ? WHERE key = ?", (value, key))
    return True


def select_value_sync(cursor, key):
    cursor.execute("SELECT value FROM mechy WHERE key = ?", (key, ))
    return json.loads(str(cursor.fetchone()[0]))


def update_value_sync(cursor, key, value):
    value = json.dumps(value)
    cursor.execute("UPDATE mechy SET value = ? WHERE key = ?", (value, key))
    return True
