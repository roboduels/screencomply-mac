"""
S3 uploader for ScreenComply Lite.
Uploads raw session files to the screencomply-prod S3 bucket,
preserving the folder structure.
"""

import os
import boto3

AWS_REGION = "us-east-2"
AWS_ACCESS_KEY = "AKIAW4BLXMAIM4GHE6ZJ"
AWS_SECRET_KEY = "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"


def upload_session_to_s3(session_folder: str, session_id: str) -> str:
    """Upload all files in a session folder to S3, preserving structure.

    Uploads each file individually so the S3 bucket mirrors the local
    folder layout:  sessions/{session_id}/session_info.json
                    sessions/{session_id}/system_integrity.jsonl
                    sessions/{session_id}/session_summary.json

    Args:
        session_folder: Path to the local session folder
        session_id: Session identifier used as the S3 prefix

    Returns:
        The S3 prefix URI where files were uploaded

    Raises:
        Exception: If upload fails
    """
    bucket = "screencomply-prod"
    s3_prefix = f"sessions/{session_id}"

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
    )

    uploaded = 0
    for root, dirs, files in os.walk(session_folder):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative = os.path.relpath(local_path, session_folder)
            s3_key = f"{s3_prefix}/{relative}".replace("\\", "/")

            with open(local_path, "rb") as f:
                s3.upload_fileobj(f, bucket, s3_key)
            uploaded += 1
            print(f"  ↑ {s3_key}")

    s3_uri = f"s3://{bucket}/{s3_prefix}/"
    print(f"✓ Uploaded {uploaded} file(s) to {s3_uri}")
    return s3_uri
