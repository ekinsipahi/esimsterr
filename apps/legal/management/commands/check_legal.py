"""Guard the version numbers against silent edits.

The acceptance ledger stores "version 2026.1, hash 9f2c...". That record is only
worth something if the pair is stable: edit a clause without bumping the version
and every earlier record now claims the customer agreed to text they never saw.

So the hashes are checked in, and this command compares them. It runs in CI and
before a deploy; `--write` accepts the new text and is the deliberate act of
saying "yes, this is a new version".
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.legal.documents import BY_SLUG, DOCUMENTS, version_hash
from apps.legal.history import HISTORY
from apps.legal.registry import ALL_SURFACES

LOCK = Path(__file__).resolve().parents[2] / "versions.lock.json"


class Command(BaseCommand):
    help = "Verify that every legal document's text still matches its recorded version."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true",
                            help="Accept the current text as the content of the current versions.")

    def handle(self, *args, **opts):
        current = {
            doc.slug: {
                "version": doc.version,
                "effective": doc.effective.isoformat(),
                "hashes": {s: version_hash(doc.slug, s) for s in ALL_SURFACES if doc.applies_to(s)},
            }
            for doc in DOCUMENTS
        }

        if opts["write"]:
            LOCK.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {LOCK.name} for {len(current)} documents."))
            return

        if not LOCK.exists():
            raise CommandError(f"{LOCK} is missing. Run with --write to create it.")

        locked = json.loads(LOCK.read_text(encoding="utf-8"))
        problems = []

        for slug, now in current.items():
            was = locked.get(slug)
            if was is None:
                problems.append(f"{slug}: new document, not in the lock file")
                continue
            if was["hashes"] != now["hashes"] and was["version"] == now["version"]:
                changed = [s for s in now["hashes"] if was["hashes"].get(s) != now["hashes"][s]]
                problems.append(
                    f"{slug}: text changed on {', '.join(changed)} but the version is still "
                    f"{now['version']}. Bump Document.version, add an entry to history.py, "
                    f"then run check_legal --write."
                )
            if was["version"] != now["version"] and was["effective"] == now["effective"]:
                problems.append(
                    f"{slug}: version moved {was['version']} to {now['version']} without a new "
                    f"effective date."
                )
            elif was["hashes"] != now["hashes"]:
                # A legitimate version bump still has to be recorded. Without
                # this the lock quietly goes stale, and the next edit that
                # forgets to bump slips through because the versions no longer
                # match either -- which defeats the whole mechanism.
                problems.append(
                    f"{slug}: text changed and the lock file was not updated. Run "
                    f"check_legal --write and commit apps/legal/versions.lock.json."
                )

        for slug in locked.keys() - current.keys():
            problems.append(f"{slug}: was published and has been removed; keep it reachable or "
                            f"redirect it, old orders link to it")

        # Every version in the registry must be explained on the change-history
        # page, or the page silently stops being a history.
        documented = {(e["version"], d) for e in HISTORY for d in e["documents"]}
        for doc in DOCUMENTS:
            if (doc.version, doc.slug) not in documented:
                problems.append(f"{doc.slug}: version {doc.version} has no entry in history.py")

        if problems:
            for p in problems:
                self.stderr.write(self.style.ERROR(f"  {p}"))
            raise CommandError(f"{len(problems)} legal version problem(s).")

        self.stdout.write(self.style.SUCCESS(
            f"All {len(current)} legal documents match their recorded versions."
        ))
