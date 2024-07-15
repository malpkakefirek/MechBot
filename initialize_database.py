import os
# import sqlite3
import json


def initialize_database(conn):
    database_structure = {
        'permitted': list,
        'lvl_roles': dict,
        'invites': dict,
        'money': dict,
        'temp_xp': dict,
        'alert_channel': None,
        'shop': dict,
        'xp_blacklist': list,
        'xp_channel_settings': dict,
        'xp_category_settings': dict,
        'xp': dict,
        'locales': dict
    }
    type_translation = {
        list: "[]",
        dict: "{}",
        None: "NULL"
    }

    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mechy (
            key string,
            value string
        )
    ''')

    try:
        # Read JSON data from file
        with open('db.json', 'r') as json_file:
            data = json.load(json_file)

        # Insert data into SQLite table
        for key, value in data.items():
            json_string = json.dumps(value)
            cursor.execute("INSERT INTO mechy (key, value) VALUES (?, ?)", (key, json_string))

        # Commit the changes
        conn.commit()

        os.remove('db.json')
    except Exception as e:
        print(str(e))

    for key, value in database_structure.items():
        cursor.execute("SELECT * FROM mechy WHERE key = ?", (key, ))
        if cursor.fetchone() is None:
            query = "INSERT INTO mechy (key, value) VALUES (?, ?)"
            cursor.execute(query, (key, type_translation[value]))
            conn.commit()

        cursor.execute("SELECT value FROM mechy WHERE key = ?", (key, ))
        value = cursor.fetchone()[0]
        print(f"{key} — {value}\n")

    print("\n==============================\nCREATED ALL MISSING DATABASES!\n==============================\n")
