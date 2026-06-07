import sqlite3
import json

def main():
    db_path = "data/assest_dev.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, type, config FROM connectors;")
    rows = cursor.fetchall()
    
    print(f"Direct SQLite Inspection of {len(rows)} connectors:")
    for row in rows:
        c_id, c_type, config = row
        print(f"  ID: {c_id}, Type: {c_type}")
        print(f"  Raw Config: {repr(config)}")
        
        # Check if the config is valid JSON.
        is_valid_json = False
        try:
            parsed = json.loads(config)
            print(f"    -> Valid JSON parsed as {type(parsed)}")
            is_valid_json = True
        except Exception as e:
            print(f"    -> Invalid JSON: {e}")
            
        if not is_valid_json:
            # Wrap in double quotes to make it a valid JSON string.
            new_config = json.dumps(config)
            print(f"    -> Fixing invalid JSON. New value: {repr(new_config)}")
            cursor.execute("UPDATE connectors SET config = ? WHERE id = ?;", (new_config, c_id))
            conn.commit()
            print("    -> Updated.")
            
    conn.close()

if __name__ == "__main__":
    main()
