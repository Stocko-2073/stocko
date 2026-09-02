#!/usr/bin/env bash
# Create and configure the S3 bucket the robot pulls firmware from.
# Reentrant: safe to run again; it only fixes what is missing.
#
# Layout in the bucket, matching what the firmware expects (net/ota.c):
#   firmware.bin   the image, uploaded by push_firmware.sh
#   version.txt    its version, one line, e.g. 0.1.3
#
# Only those two objects are public-read; everything else stays private.
# Versioning is on so an earlier image can be restored from the console.
#
# Writes .ota_config (gitignored) with the bucket name and URL, which
# push_firmware.sh reads. Adapted from corvid/firmware/ota_provisioning.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/.ota_config"
REGION="${AWS_REGION:-us-east-1}"

info() { echo "[info] $*"; }
fail() { echo "[error] $*" >&2; exit 1; }

command -v aws >/dev/null || fail "AWS CLI not found"
aws sts get-caller-identity >/dev/null 2>&1 || fail "AWS credentials not configured -- 'aws configure'"

BUCKET_NAME=""
if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
    info "existing config: BUCKET_NAME=$BUCKET_NAME"
fi
if [[ -z "$BUCKET_NAME" ]]; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    BUCKET_NAME="ubot-ota-${ACCOUNT_ID}"
    info "bucket name: $BUCKET_NAME"
fi

if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    info "bucket '$BUCKET_NAME' exists"
else
    info "creating bucket '$BUCKET_NAME' in $REGION"
    if [[ "$REGION" == "us-east-1" ]]; then
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$REGION" >/dev/null
    else
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
    fi
fi

# Block public ACLs but allow a bucket policy, which is how the two firmware
# objects are exposed.
aws s3api put-public-access-block --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false"

POLICY=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadFirmware",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": [
      "arn:aws:s3:::${BUCKET_NAME}/firmware.bin",
      "arn:aws:s3:::${BUCKET_NAME}/version.txt"
    ]
  }]
}
JSON
)
aws s3api put-bucket-policy --bucket "$BUCKET_NAME" --policy "$POLICY"
aws s3api put-bucket-versioning --bucket "$BUCKET_NAME" --versioning-configuration Status=Enabled
info "policy and versioning set"

# The firmware only accepts https:// -- the certificate bundle it ships has
# Amazon's roots, so this URL verifies as-is.
BUCKET_URL="https://${BUCKET_NAME}.s3.${REGION}.amazonaws.com"

cat > "$CONFIG_FILE" <<CFG
# Written by ota_provisioning.sh; read by push_firmware.sh
BUCKET_NAME="$BUCKET_NAME"
BUCKET_URL="$BUCKET_URL"
REGION="$REGION"
CFG
info "saved $CONFIG_FILE"

if ! aws s3api head-object --bucket "$BUCKET_NAME" --key version.txt >/dev/null 2>&1; then
    echo "0.0.0" | aws s3 cp - "s3://${BUCKET_NAME}/version.txt" --content-type text/plain >/dev/null
    info "created version.txt (0.0.0)"
fi

cat <<DONE

OTA bucket ready.
  bucket   $BUCKET_NAME
  url      $BUCKET_URL

Point the robot at it once, on its console:
  set ota_url $BUCKET_URL

Then, after each ./push_firmware.sh:
  ota check          update if version.txt is newer than what is running
  ota start          update regardless
Or 'set ota_auto 1' to check every time WiFi comes up.
DONE
