#!/usr/bin/env bash
# Bump the version, build, and upload the image to the OTA bucket.
#
#   ./push_firmware.sh                 patch bump (0.1.0 -> 0.1.1), build, upload
#   ./push_firmware.sh --bump-minor    0.1.x -> 0.2.0
#   ./push_firmware.sh --bump-major    x.y.z -> (x+1).0.0
#   ./push_firmware.sh --no-bump       upload whatever version.txt already says
#   ./push_firmware.sh --clean         idf.py fullclean first
#
# The version lives in version.txt, which ESP-IDF bakes into the image as
# PROJECT_VER (what `version` prints and the BLE firmware-revision reports).
# The same string goes to the bucket as version.txt so `ota check` can compare.
# Adapted from corvid/firmware/push_firmware.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/.ota_config"
VERSION_FILE="$SCRIPT_DIR/version.txt"
BIN="$SCRIPT_DIR/build/ubot_base.bin"
IDF="${IDF_PATH:-$HOME/esp/esp-idf}"

info() { echo "[info] $*"; }
step() { echo "[step] $*"; }
fail() { echo "[error] $*" >&2; exit 1; }

BUMP="patch"
CLEAN=false
for arg in "$@"; do
    case "$arg" in
        --bump-major) BUMP="major" ;;
        --bump-minor) BUMP="minor" ;;
        --bump-patch) BUMP="patch" ;;
        --no-bump)    BUMP="none" ;;
        --clean)      CLEAN=true ;;
        -h|--help)    sed -n '2,13p' "$0"; exit 0 ;;
        *) fail "unknown option: $arg (try --help)" ;;
    esac
done

command -v aws >/dev/null || fail "AWS CLI not found"
[[ -f "$CONFIG_FILE" ]] || fail "no $CONFIG_FILE -- run ./ota_provisioning.sh first"
# shellcheck disable=SC1090
source "$CONFIG_FILE"
[[ -f "$VERSION_FILE" ]] || fail "no $VERSION_FILE"

CURRENT=$(tr -d '[:space:]' < "$VERSION_FILE")
[[ "$CURRENT" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "version.txt is not MAJOR.MINOR.PATCH: '$CURRENT'"
IFS=. read -r MAJOR MINOR PATCH <<< "$CURRENT"
case "$BUMP" in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    patch) PATCH=$((PATCH + 1)) ;;
    none)  ;;
esac
NEW="${MAJOR}.${MINOR}.${PATCH}"
info "version $CURRENT -> $NEW"
echo "$NEW" > "$VERSION_FILE"

cd "$SCRIPT_DIR"
# shellcheck disable=SC1091
. "$IDF/export.sh" >/dev/null
if [[ "$CLEAN" == true ]]; then
    step "fullclean"
    idf.py fullclean
fi
step "build"
idf.py build
[[ -f "$BIN" ]] || fail "no image at $BIN"
SIZE=$(stat -f%z "$BIN" 2>/dev/null || stat -c%s "$BIN")
info "image $SIZE bytes"

MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
python3 "$SCRIPT_DIR/tools/release_manifest.py" "$BIN" --base "$BUCKET_URL" --version "$NEW" > "$MANIFEST"
SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$MANIFEST")"
KEY="releases/$NEW/$SHA.bin"

step "upload immutable release"
# Conditional writes prevent accidental replacement, including concurrent publishers.
"${UBOT_PUBLISH_PYTHON:-python3}" "$SCRIPT_DIR/tools/publish_immutable.py" \
    --bucket "$BUCKET_NAME" --region "${REGION:-us-east-1}" --image "$BIN" --manifest "$MANIFEST"
# Keep legacy readers working during the bootstrap transition.
aws s3 cp "$BIN" "s3://${BUCKET_NAME}/firmware.bin" --content-type application/octet-stream
echo "$NEW" | aws s3 cp - "s3://${BUCKET_NAME}/version.txt" --content-type text/plain
# Publish the discovery pointer last, after every referenced object exists.
aws s3 cp "$MANIFEST" "s3://${BUCKET_NAME}/manifest.json" --content-type application/json --cache-control no-cache

cat <<DONE

Published $NEW
  $BUCKET_URL/firmware.bin   ($SIZE bytes)
  $BUCKET_URL/version.txt

Use ubotctl ota check, then ubotctl ota install. Automatic installation is disabled.
DONE
