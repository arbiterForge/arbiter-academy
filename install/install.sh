#!/bin/sh
set -eu
umask 077

RELEASE='preview-0.12'
ARCHIVE_NAME='arbiter-academy-preview-0.12.zip'
BUNDLE_SHA256='20175566732f49143f1a569d5767e616ab6327e54e19bff44c981a8a36beeb41'
ASSET_URL='https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.12/arbiter-academy-preview-0.12.zip'
BUNDLE_PATH=''

die() {
    printf '%s\n' "Arbiter Academy installer: $*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --bundle)
            [ "$#" -ge 2 ] || die '--bundle requires a path'
            BUNDLE_PATH=$2
            shift 2
            ;;
        *) die "unsupported installer argument: $1" ;;
    esac
done

python_command=$(command -v python3) || die 'python3 is required'
if [ -n "${XDG_DATA_HOME:-}" ]; then
    case "$XDG_DATA_HOME" in /*) data_home=$XDG_DATA_HOME ;; *) die 'XDG_DATA_HOME must be absolute' ;; esac
else
    case "${HOME:-}" in /*) data_home=$HOME/.local/share ;; *) die 'HOME must be absolute' ;; esac
fi
academy_root=$data_home/arbiter-academy
install_root=$academy_root/$RELEASE
case "$install_root" in "$academy_root"/preview-0.12) ;; *) die 'installer path escapes the user-owned Academy directory' ;; esac
[ ! -e "$academy_root" ] || { [ -d "$academy_root" ] && [ ! -L "$academy_root" ]; } \
    || die 'Academy tools directory must be a plain directory, not a symbolic link'
[ ! -e "$install_root" ] || die "conflicting or unowned install path: $install_root"

root_created=0
if [ ! -e "$academy_root" ]; then
    mkdir -p -- "$data_home"
    mkdir -- "$academy_root"
    root_created=1
fi
academy_physical=$(CDPATH= cd -- "$academy_root" && pwd -P) \
    || die 'could not establish the Academy tools directory identity'
marker_name=.academy-install-owner
ownership_token=$(LC_ALL=C od -An -N32 -tx1 /dev/urandom | tr -d ' \n') \
    || die 'could not create an unpredictable installer ownership token'
[ "${#ownership_token}" -eq 64 ] || die 'could not create an unpredictable installer ownership token'
work_root=$academy_root/.preview-0.12-install-$$
case "$work_root" in "$academy_root"/.preview-0.12-install-*) ;; *) die 'invalid installer work path' ;; esac
[ ! -e "$work_root" ] || die "conflicting installer work path: $work_root"
mkdir -- "$work_root"
work_marker=$work_root/$marker_name
(set -C; printf '%s\n' "$ownership_token" >"$work_marker") \
    || die 'could not claim the installer work directory'
extract_root=$work_root/bundle
download_path=$work_root/$ARCHIVE_NAME
owns_install=0
complete=0

plain_academy_root_is_current() {
    [ -d "$academy_root" ] && [ ! -L "$academy_root" ] || return 1
    current_root=$(CDPATH= cd -- "$academy_root" 2>/dev/null && pwd -P) || return 1
    [ "$current_root" = "$academy_physical" ]
}

owned_directory_is_current() {
    directory=$1
    marker=$2
    plain_academy_root_is_current || return 1
    [ -d "$directory" ] && [ ! -L "$directory" ] || return 1
    current_directory=$(CDPATH= cd -- "$directory" 2>/dev/null && pwd -P) || return 1
    [ "$current_directory" = "$academy_physical/$(basename -- "$directory")" ] || return 1
    [ -f "$marker" ] && [ ! -L "$marker" ] || return 1
    [ "$(command sed -n '1p' "$marker")" = "$ownership_token" ] || return 1
    [ "$(command wc -l <"$marker" | tr -d ' ')" = 1 ]
}

remove_owned_directory() {
    directory=$1
    marker=$2
    label=$3
    if ! owned_directory_is_current "$directory" "$marker"; then
        printf '%s\n' "rollback ownership check failed for $label; preserving it" >&2
        return
    fi
    quarantine=$academy_root/.academy-delete-$ownership_token-$label
    case "$quarantine" in "$academy_root"/.academy-delete-*) ;; *) die 'invalid quarantine path' ;; esac
    [ ! -e "$quarantine" ] && [ ! -L "$quarantine" ] || die 'conflicting rollback quarantine path'
    mv -- "$directory" "$quarantine"
    quarantine_marker=$quarantine/$(basename -- "$marker")
    if ! owned_directory_is_current "$quarantine" "$quarantine_marker"; then
        printf '%s\n' "rollback ownership check failed after quarantining $label; preserving it" >&2
        return
    fi
    rm -rf -- "$quarantine"
}

cleanup() {
    status=$?
    if [ "$complete" -ne 1 ] && [ "$owns_install" -eq 1 ] && [ -e "$install_root" ]; then
        remove_owned_directory "$install_root" "$install_marker" install
    fi
    if [ -e "$work_root" ]; then
        remove_owned_directory "$work_root" "$work_marker" work
    fi
    if [ "$root_created" -eq 1 ] && plain_academy_root_is_current; then
        rmdir -- "$academy_root" 2>/dev/null || true
    fi
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

validate_redirect() {
    "$python_command" - "$1" "$2" <<'PY'
import sys
from urllib.parse import urljoin, urlsplit

current = urlsplit(sys.argv[1])
candidate_url = urljoin(sys.argv[1], sys.argv[2].strip())
candidate = urlsplit(candidate_url)
trusted_first = current.hostname == "github.com" and candidate.hostname == "release-assets.githubusercontent.com"
trusted_cdn = current.hostname == "release-assets.githubusercontent.com" and candidate.hostname == "release-assets.githubusercontent.com"
if (
    candidate.scheme != "https"
    or candidate.username is not None
    or candidate.password is not None
    or candidate.port not in (None, 443)
    or candidate.fragment
    or not (trusted_first or trusted_cdn)
):
    raise SystemExit("release asset redirected to an untrusted or mutable location")
print(candidate_url)
PY
}

download_release_asset() {
    command -v curl >/dev/null 2>&1 || die 'curl is required to download the immutable release asset'
    current=$ASSET_URL
    redirects=0
    while :; do
        headers=$work_root/headers
        body=$work_root/body
        rm -f -- "$headers" "$body"
        status=$(curl --proto '=https' --tlsv1.2 --silent --show-error \
            --dump-header "$headers" --output "$body" --write-out '%{http_code}' "$current") \
            || die 'immutable release asset download failed'
        case "$status" in
            200)
                case "$current" in
                    https://github.com/*|https://release-assets.githubusercontent.com/*) ;;
                    *) die 'release asset response came from an untrusted host' ;;
                esac
                mv -- "$body" "$download_path"
                return
                ;;
            30[12378])
                [ "$redirects" -lt 3 ] || die 'release asset redirect chain is too long'
                location=$("$python_command" - "$headers" <<'PY'
import sys
from pathlib import Path

locations = []
for line in Path(sys.argv[1]).read_text(encoding="iso-8859-1").splitlines():
    if line.lower().startswith("location:"):
        locations.append(line.split(":", 1)[1].strip())
if len(locations) != 1 or not locations[0]:
    raise SystemExit("release asset redirect response has no unique Location")
print(locations[0])
PY
                ) || die 'release asset redirect response is malformed'
                current=$(validate_redirect "$current" "$location") \
                    || die 'release asset redirected to an untrusted or mutable location'
                redirects=$((redirects + 1))
                ;;
            *) die "release asset download returned HTTP $status" ;;
        esac
    done
}

if [ -n "$BUNDLE_PATH" ]; then
    [ -f "$BUNDLE_PATH" ] && [ ! -L "$BUNDLE_PATH" ] || die 'local bundle must be a regular file, not a symbolic link'
    bundle=$BUNDLE_PATH
else
    download_release_asset
    bundle=$download_path
fi

actual_digest=$("$python_command" - "$bundle" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
) || die 'could not hash the release bundle'
[ "$actual_digest" = "$BUNDLE_SHA256" ] || die 'bundle SHA-256 mismatch; extraction was not attempted'

mkdir -- "$extract_root"
wheel_name=$("$python_command" - "$bundle" "$extract_root" "$RELEASE" <<'PY'
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

archive_path, destination, release = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
with zipfile.ZipFile(archive_path) as archive:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len({name.casefold() for name in names}) != len(names):
        raise SystemExit("bundle contains duplicate or case-colliding paths")
    for info in infos:
        name = info.filename
        parts = PurePosixPath(name).parts
        file_type = (info.external_attr >> 16) & 0o170000
        if (
            not name
            or "\\" in name
            or name.startswith("/")
            or ":" in name
            or "/./" in f"/{name}/"
            or "//" in name
            or any(part in ("", ".", "..") for part in parts)
            or file_type == stat.S_IFLNK
        ):
            raise SystemExit("bundle contains an unsafe archive path")
    if len(names) != 2 or "bundle-manifest.json" not in names:
        raise SystemExit("bundle inventory is not the reviewed two-file offline payload")
    manifest_bytes = archive.read("bundle-manifest.json")
    manifest = json.loads(manifest_bytes)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if canonical != manifest_bytes:
        raise SystemExit("bundle-manifest.json is not canonical")
    wheelhouse = manifest.get("wheelhouse")
    if manifest.get("format_version") != 1 or manifest.get("release") != release or not isinstance(wheelhouse, list) or len(wheelhouse) != 1:
        raise SystemExit("bundle manifest does not match the reviewed release contract")
    record = wheelhouse[0]
    wheel = record.get("filename")
    if not isinstance(wheel, str) or re.fullmatch(r"workshop_queue-[A-Za-z0-9_.]+-py3-none-any\.whl", wheel) is None:
        raise SystemExit("bundle manifest contains an unapproved Academy wheel name")
    wheel_path = f"wheelhouse/{wheel}"
    if set(names) != {"bundle-manifest.json", wheel_path}:
        raise SystemExit("bundle inventory differs from its canonical manifest")
    payload = archive.read(wheel_path)
    if record.get("size") != len(payload) or record.get("sha256") != hashlib.sha256(payload).hexdigest():
        raise SystemExit("bundle manifest Academy wheel digest or size mismatch")
    for name in sorted(names):
        target = destination.joinpath(*PurePosixPath(name).parts)
        if destination.resolve() not in target.parent.resolve().parents and target.parent.resolve() != destination.resolve():
            raise SystemExit("bundle contains an archive traversal path")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(name) as source, target.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
print(wheel)
PY
) || die 'release bundle validation or extraction failed'

mkdir -- "$install_root" || die "conflicting or unowned install path: $install_root"
install_marker=$install_root/$marker_name
(set -C; printf '%s\n' "$ownership_token" >"$install_marker") \
    || die 'could not claim the Academy install directory'
owns_install=1
"$python_command" -m venv --copies "$install_root" || die 'Python failed to create the Academy environment'
venv_python=$install_root/bin/python
academy=$install_root/bin/arbiter-academy
wheelhouse=$extract_root/wheelhouse
wheel=$wheelhouse/$wheel_name
PIP_NO_INDEX=1 PIP_NO_CACHE_DIR=1 "$venv_python" -m pip install \
    --disable-pip-version-check --no-index --no-deps --find-links "$wheelhouse" "$wheel" \
    || die 'offline Academy wheel installation failed'

"$python_command" - "$install_root" "$BUNDLE_SHA256" "$RELEASE" <<'PY'
import json
import os
import sys
from pathlib import Path

root, digest, release = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
root_physical = root.resolve(strict=True)
owned = []
for directory, directories, files in os.walk(root, followlinks=False):
    base = Path(directory)
    for name in sorted(directories + files):
        path = base / name
        if path.is_symlink():
            try:
                path.resolve(strict=True).relative_to(root_physical)
            except (OSError, RuntimeError, ValueError):
                raise SystemExit("Academy environment contains a symbolic link outside its owned root")
        owned.append(path.relative_to(root).as_posix())
owned.append("install-manifest.json")
manifest = {
    "bundle_sha256": digest,
    "executable": "bin/arbiter-academy",
    "format_version": 1,
    "owned_paths": sorted(owned),
    "release": release,
}
(root / "install-manifest.json").write_bytes(
    json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
)
PY

complete=1
printf '%s\n' "Installed Arbiter Academy $RELEASE at $academy"
if ! "$academy" --repository "$PWD" doctor; then
    printf '%s\n' 'Academy Doctor reported repository preconditions that need attention.' >&2
fi
