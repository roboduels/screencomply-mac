"""
API client for ScreenComply Lite.
Handles session heartbeat (start/heartbeat/end) via Supabase edge function
and S3 upload of session data.
"""

import time
import requests
from typing import Dict, Any

HEARTBEAT_URL = "https://ocyyhutrtuyiahqieygd.supabase.co/functions/v1/session-heartbeat"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9jeXlodXRydHV5aWFocWlleWdkIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzAwNjE5MzUsImV4cCI6MjA4NTYzNzkzNX0."
    "MmGJ-I2yF9fmhX0u0FrDAVseOwdr_kga_DecX3_Ym5c"
)


class APIClient:
    """Client for communicating with ScreenComply backend."""

    def __init__(self, user_email: str, session_id: str):
        self.user_email = user_email
        self.session_id = session_id
        self.session_start = time.time()

    def _post_heartbeat(self, action: str) -> dict:
        """Send a request to the session-heartbeat edge function.

        Args:
            action: One of "start", "heartbeat", or "end"

        Returns:
            Response JSON dict, or empty dict on failure
        """
        payload = {
            "participantEmail": self.user_email,
            "action": action,
        }

        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(HEARTBEAT_URL, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data
        except requests.RequestException as e:
            print(f"✗ Heartbeat {action} failed: {e}")
            return {}

    def register_session(self):
        """Send action: 'start' to mark the session as live."""
        try:
            data = self._post_heartbeat("start")
            status = data.get("status", "unknown")
            print(f"✓ Session registered (status: {status})")
            print(f"  User: {self.user_email}")
            print(f"  Session ID: {self.session_id}")
            return True
        except Exception as e:
            print(f"✗ Failed to register session: {e}")
            return False

    def send_heartbeat(self, snapshot_count: int = 0):
        """Send action: 'heartbeat' as a keep-alive ping."""
        try:
            duration = int(time.time() - self.session_start)
            self._post_heartbeat("heartbeat")
            print(f"♥ Heartbeat sent — Duration: {duration}s, Snapshots: {snapshot_count}")
            return True
        except Exception as e:
            print(f"✗ Heartbeat failed: {e}")
            return False

    def end_session(self):
        """Send action: 'end' to complete the session and trigger report generation."""
        try:
            data = self._post_heartbeat("end")
            status = data.get("status", "unknown")
            print(f"✓ Session ended (status: {status})")
            return True
        except Exception as e:
            print(f"✗ Failed to end session: {e}")
            return False

    def upload_session(self, summary: Dict[str, Any], session_folder: str):
        """Upload session data files to S3."""
        try:
            print(f"  Duration: {summary.get('duration_seconds', 0):.1f}s")
            print(f"  Snapshots: {summary.get('total_snapshots', 0)}")

            # Lazy import to avoid slow boto3 load at startup
            from s3_uploader import upload_session_to_s3

            s3_uri = upload_session_to_s3(session_folder, self.session_id)
            print(f"✓ Uploaded to S3: {s3_uri}")

            return True
        except Exception as e:
            print(f"✗ Failed to upload session: {e}")
            return False
