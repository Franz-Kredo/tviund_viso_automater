#!/usr/bin/env bash
set -euo pipefail

#
# ─── USER CONFIGURATION ────────────────────────────────────────────────────────
#

# Which file extensions to snapshot? (no leading dot; leave empty for “all”)
INCLUDE_EXTENSIONS=(py md)

# Directories to skip entirely
IGNORE_DIRS=(snapshots .venv .git)

# Filename-patterns to skip (globs)
IGNORE_PATTERNS=('*.pyc' '.env*')

# This script’s filename (so we don’t snapshot ourselves)
SELF_SCRIPT="$(basename "$0")"

#
# ─── PLATFORM DETECTION ────────────────────────────────────────────────────────
#
OS="$(uname -s)"
if [[ "$OS" == "Darwin" ]]; then
CLIP_MODE="pbcopy-only"
elif [[ "$OS" == "Linux" ]] && grep -qE '^ID=debian' /etc/os-release && grep -qE 'VERSION_ID="12"' /etc/os-release; then
CLIP_MODE="auto"    # Debian 12 “remote”
else
CLIP_MODE="auto"
echo "⚠️  Unrecognized OS or distro—using generic clipboard‐auto mode." >&2
fi

#
# ─── PREPARE SNAPSHOT & INDEX ─────────────────────────────────────────────────
#
mkdir -p snapshots

# Always use nullglob so “no snapshots yet” doesn’t break
shopt -s nullglob
last=0
for f in snapshots/data-*.md; do
num="${f##*data-}"
num="${num%.md}"
# only update if it’s a number
if [[ "$num" =~ ^[0-9]+$ ]] && (( num > last )); then
    last=$num
fi
done
shopt -u nullglob

next=$(( last + 1 ))
outfile="snapshots/data-$next.md"

#
# ─── BUILD find ARGUMENTS ─────────────────────────────────────────────────────
#

# 1) prune list
prune_args=()
for d in "${IGNORE_DIRS[@]}"; do
prune_args+=( -path "./$d" -prune -o )
done
# drop trailing -o
unset 'prune_args[${#prune_args[@]}-1]'

# 2) extensions filter
ext_args=()
if (( ${#INCLUDE_EXTENSIONS[@]} )); then
for ext in "${INCLUDE_EXTENSIONS[@]}"; do
    ext_args+=( -iname "*.${ext}" -o )
done
unset 'ext_args[${#ext_args[@]}-1]'
else
ext_args=( -true )
fi

# 3) extra patterns + this script
pattern_args=()
for pat in "${IGNORE_PATTERNS[@]}"; do
pattern_args+=( ! -name "$pat" )
done
pattern_args+=( ! -name "$SELF_SCRIPT" )

#
# ─── DUMP SNAPSHOT ─────────────────────────────────────────────────────────────
#
{
echo '```'
if command -v tree &>/dev/null; then
    tree -I "$(IFS='|'; echo "${IGNORE_DIRS[*]}" "${IGNORE_PATTERNS[*]}" "$SELF_SCRIPT")"
else
    find . "${prune_args[@]}" -prune -o -type f -print | sed 's|^\./||'
fi
echo '```'
echo

find . \
    "${prune_args[@]}" -prune -o \
    -type f \
    \( "${ext_args[@]}" \) \
    "${pattern_args[@]}" \
    -print0 \
| sort -z \
| while IFS= read -r -d '' file; do
    echo "## ${file#./}"
    cat "$file"
    echo
    done
} > "$outfile"

echo "✅ Saved snapshot to $outfile"

#
# ─── COPY TO CLIPBOARD ───────────────────────────────────────────────────────────
#
copy_osc52() {
local b64
b64=$(base64 < "$1" | tr -d '\n')
printf "\e]52;c;%s\a" "$b64"
}

if [[ "$CLIP_MODE" == "pbcopy-only" ]]; then
if command -v pbcopy &>/dev/null; then
    pbcopy < "$outfile" && echo "Copied via pbcopy."
else
    echo "⚠️ pbcopy not found; copy $outfile manually."
fi
else
if command -v pbcopy &>/dev/null; then
    pbcopy < "$outfile" && echo "Copied via pbcopy."
elif command -v xclip &>/dev/null; then
    if xclip -selection clipboard < "$outfile"; then
    echo "Copied via xclip."
    else
    echo "🔄 xclip failed; using OSC52."
    copy_osc52 "$outfile" && echo "Copied via OSC52."
    fi
elif command -v xsel &>/dev/null; then
    if xsel --clipboard --input < "$outfile"; then
    echo "Copied via xsel."
    else
    echo "🔄 xsel failed; using OSC52."
    copy_osc52 "$outfile" && echo "Copied via OSC52."
    fi
elif [[ -n "${SSH_CONNECTION:-}" && -t 1 ]]; then
    copy_osc52 "$outfile" && echo "Copied via OSC52 over SSH."
else
    echo "⚠️  No clipboard tool found—install pbcopy, xclip, or xsel."
fi
fi
