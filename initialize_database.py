from replit import db

def initialize_database():
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
    current_keys = db.keys()

    for key, value in database_structure.items():
        if key not in current_keys and value is not None:
            db[key] = value()
            print(f"{key} — {db[key]}\n")

    print("\n==============================\nCREATED ALL MISSING DATABASES!\n==============================\n")
