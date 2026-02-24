"""
Lightweight logger for ScreenComply Lite.
Only logs system integrity data - no video, no audio.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any


class LiteLogger:
    """Minimal logger for system integrity monitoring only."""

    def __init__(self, user_email: str, log_dir: str = "logs"):
        self.user_email = user_email
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        # Create session folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Clean email for folder name
        clean_email = user_email.replace('@', '_at_').replace('.', '_')
        self.session_id = f"{clean_email}_{timestamp}"
        self.session_folder = os.path.join(log_dir, f"session_{self.session_id}")
        os.makedirs(self.session_folder, exist_ok=True)

        # File paths
        self.system_info_jsonl = os.path.join(self.session_folder, "system_integrity.jsonl")
        self.summary_json = os.path.join(self.session_folder, "session_summary.json")

        # Session start time
        self._session_start = time.time()
        self._snapshot_count = 0

        # Create metadata file
        self._create_metadata()

        print(f"✓ Logging initialized: {self.session_folder}")

    def _create_metadata(self):
        """Create session metadata file."""
        metadata_path = os.path.join(self.session_folder, "session_info.json")
        metadata = {
            'user_email': self.user_email,
            'session_id': self.session_id,
            'session_start': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'monitoring_type': 'system_integrity_only',
            'snapshot_interval_seconds': 5,
        }
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

    def _get_timestamp(self) -> tuple:
        """Get timestamp in milliseconds and human-readable format."""
        elapsed_ms = int((time.time() - self._session_start) * 1000)
        human_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        return elapsed_ms, human_time

    def log_system_integrity(self, integrity_data: Dict[str, str]):
        """Log system integrity data to JSONL.

        Args:
            integrity_data: Dict containing browser, network, and program info
        """
        try:
            elapsed_ms, human_time = self._get_timestamp()
            self._snapshot_count += 1

            # Create JSON object with timestamp
            log_entry = {
                'snapshot': self._snapshot_count,
                'timestamp_ms': elapsed_ms,
                'timestamp_human': human_time,
                'browser_info': integrity_data.get('browser_info', ''),
                'browser_stats': integrity_data.get('browser_stats', ''),
                'network_info': integrity_data.get('network_info', ''),
                'programs_info': integrity_data.get('programs_info', ''),
            }

            # Append to JSONL file
            with open(self.system_info_jsonl, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
                f.flush()
        except Exception as e:
            print(f"Error logging system integrity: {e}")

    def close(self) -> Dict[str, Any]:
        """Close the logger and create session summary.

        Returns:
            Session summary dict
        """
        duration = time.time() - self._session_start

        summary = {
            'user_email': self.user_email,
            'session_id': self.session_id,
            'session_start': datetime.fromtimestamp(self._session_start).strftime('%Y-%m-%d %H:%M:%S'),
            'session_end': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'duration_seconds': duration,
            'total_snapshots': self._snapshot_count,
            'snapshot_interval': 5,
        }

        # Write summary
        try:
            with open(self.summary_json, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2)
        except Exception as e:
            print(f"Error writing summary: {e}")

        print(f"✓ Session logged: {self._snapshot_count} snapshots over {duration:.1f}s")
        return summary
