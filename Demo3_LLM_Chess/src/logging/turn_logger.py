import json
import os
from datetime import datetime

class TurnLogger:
    def __init__(self, log_file_path):
        self.log_file_path = log_file_path
        # Ensure the directory exists
        log_dir = os.path.dirname(log_file_path)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def log_turn(self, turn_data: dict):
        record = dict(turn_data)
        record["timestamp"] = datetime.utcnow().replace(microsecond=0).isoformat()

        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
        except Exception as e:
            # Logging is intentionally non-fatal.
            print(f"Error writing to log file: {e}")
