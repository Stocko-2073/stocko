#!/usr/bin/env python3
"""Conditional S3 writes; works even when the installed AWS CLI is older.
Requires boto3 >= 1.35 in UBOT_PUBLISH_PYTHON's environment.
"""
import argparse
import hashlib
import json
from pathlib import Path


def put(client, bucket, key, data, content_type):
    import botocore.exceptions
    digest = hashlib.sha256(data).hexdigest()
    try:
        client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type,
                          IfNoneMatch='*', Metadata={'sha256': digest})
    except botocore.exceptions.ClientError as error:
        if error.response['ResponseMetadata']['HTTPStatusCode'] != 412:
            raise
        # A retry is safe only when the immutable bytes already match exactly.
        existing = client.get_object(Bucket=bucket, Key=key)['Body']
        try:
            actual = hashlib.sha256(existing.read()).hexdigest()
        finally:
            existing.close()
        if actual != digest:
            raise RuntimeError(f'immutable release already exists with different content: {key}')


def main():
    import boto3
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bucket', required=True)
    p.add_argument('--region', default='us-east-1')
    p.add_argument('--image', required=True, type=Path)
    p.add_argument('--manifest', required=True, type=Path)
    a = p.parse_args()
    manifest = a.manifest.read_bytes()
    m = json.loads(manifest)
    client = boto3.client('s3', region_name=a.region)
    put(client, a.bucket, f"releases/{m['version']}/{m['sha256']}.bin",
        a.image.read_bytes(), 'application/octet-stream')
    put(client, a.bucket, f"releases/{m['version']}/manifest.json", manifest, 'application/json')


if __name__ == '__main__':
    main()
