#!/usr/bin/env bash
# Copy data/ to a second physical disk.
#
# The repo holds the app; this machine holds everything you have done with it.
# Since data/ left version control there is no remote copy of your event log,
# your Records or your photographs — so this script
# is the only thing standing between a dead disk and losing all of it.
#
#   ./backup.sh                    # to the configured destination
#   ./backup.sh /run/media/me/ssd  # ...or somewhere else, e.g. a plugged-in SSD
#
# Run by pgs-backup.timer once a day. Safe to run by hand at any time, and safe
# to run twice.
set -euo pipefail
cd "$(dirname "$0")"

DATA="${PGS_DATA_DIR:-$PWD/data}"
DEST="${1:-${PGS_BACKUP_DIR:-/mnt/data/pgs-backup}}"

die() { printf '\033[31mbackup failed:\033[0m %s\n' "$*" >&2; exit 1; }

[ -d "$DATA" ] || die "no data directory at $DATA"

# The one check that matters: the destination must be on a different device
# than the source. A second copy on one disk is not a backup; it is two files
# that die together.
#
# This is also, and not obviously, the check that catches an unmounted backup
# disk. When /mnt/data is not mounted it is an ordinary empty directory on the
# root filesystem — so rsync would cheerfully "succeed", write the backup onto
# the very disk it exists to protect against, and report nothing wrong for
# months. Comparing devices catches that without needing to know how the disk
# was supposed to be mounted, which a `mountpoint` test on a hardcoded path
# does not: an external SSD lands at /run/media/you/ssd, where the parent
# directory is not a mount point and refusing would be simply wrong.
#
# The destination usually does not exist yet on a first run, so the comparison
# is made against its nearest existing ancestor — which is the filesystem the
# write would actually land on.
anchor() {
	local path="$1"
	while [ ! -e "$path" ] && [ "$path" != "/" ]; do path="$(dirname "$path")"; done
	printf '%s' "$path"
}

SRC_DEV="$(df --output=source "$DATA" | tail -1)"
DST_DEV="$(df --output=source "$(anchor "$DEST")" | tail -1)"
[ "$SRC_DEV" != "$DST_DEV" ] || die "$DEST would land on the same device as your data ($SRC_DEV).
  Almost always this means the backup disk is not mounted, so the destination
  is just an empty directory on the system disk. Copying there protects
  nothing, so this is a refusal rather than a warning.
  Check with:  findmnt $(anchor "$DEST")"

mkdir -p "$DEST"

# No --delete, deliberately.
#
# Everything here is append-only or hand-written, so the local copy shrinking is
# never something to propagate: a truncated log, a folder deleted by a misclick or
# a notes folder lost to a bad command would all be faithfully mirrored, and the
# backup would destroy the very thing you wanted it for. Without --delete the
# destination only ever grows, which for a few hundred kilobytes a year is a
# trade worth making.
#
# index.sqlite is excluded: it rebuilds from the log, and copying a database
# while the app may be writing it produces a file that is worse than absent.
rsync -a --exclude 'index.sqlite' "$DATA/" "$DEST/"

# A timestamp the app's Settings page — and you — can read to answer "when did
# this last actually work", which is the only question that matters about a
# backup and the one a silent cron job never answers.
date -Iseconds > "$DEST/.last-backup"

printf '\033[32m✓\033[0m %s → %s (%s)\n' \
	"$DATA" "$DEST" "$(du -sh "$DEST" 2>/dev/null | cut -f1)"
