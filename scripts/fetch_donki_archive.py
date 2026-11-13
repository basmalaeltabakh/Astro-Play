"""Create or refresh the bundled DONKI snapshot (data/donki_archive.json) from live NASA data.

Usage:  python scripts/fetch_donki_archive.py [--force]

Needs network access to the official DONKI API (https://ccmc.gsfc.nasa.gov/DONKI/api/). No API key is needed.
The snapshot keeps the real event values (a verbatim subset of fields), the dates covered, the retrieval time and the
provenance. If NASA cannot be reached nothing is written: an archive is only ever made from real fetched data.

An existing archive is never overwritten silently: its contents are shown first and --force is required to replace it.
After writing, the file is verified (counts re-derived from the stored events) and loaded through the same fallback
code the game uses, to confirm it is labeled "archived", never "live".
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astro import config, nasa_data  # noqa: E402


def describe_existing(path: Path) -> None:
    print(f"An archive already exists at {path}:")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        print(f"  fetched {d.get('fetched_at')}   window {d.get('window')}")
        print(f"  counts  {d.get('counts')}")
        print(f"  has provenance: {'provenance' in d}   has events: {'events' in d}")
    except Exception as e:
        print(f"  (unreadable: {type(e).__name__})")
    problems = nasa_data.verify_archive(path)
    print("  integrity: " + ("OK" if not problems else "PROBLEMS: " + "; ".join(problems)))


def main(argv=None, session=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh data/donki_archive.json from the official DONKI API.")
    ap.add_argument("--force", action="store_true", help="replace an existing archive")
    args = ap.parse_args(argv)
    target = Path(config.DONKI_ARCHIVE_PATH)
    if target.exists():
        describe_existing(target)
        if not args.force:
            print("Not overwriting. Re-run with --force to replace it.")
            return 2
    try:
        live = nasa_data.refresh_archive(target, session=session)
    except nasa_data.DonkiError as e:
        print(f"FAILED: could not fetch live DONKI data ({e}). The archive was not changed.")
        return 1
    print(f"OK   archive written to {target}")
    print(f"     window {live.window[0]} .. {live.window[1]}   fetched {live.as_of}")
    print(f"     counts {live.counts}   game solar activity {live.level:.2f}")
    problems = nasa_data.verify_archive(target)
    if problems:
        print("FAILED verification: " + "; ".join(problems))
        return 1
    with tempfile.TemporaryDirectory() as tmp:                  # load it the way the game does when NASA is unreachable
        loaded = nasa_data.get_solar_activity(cache_path=Path(tmp) / "none.json", archive_path=target,
                                              allow_network=False)
    print(f"     verified: counts match the stored events; fallback loads it as source={loaded.source!r}, "
          f"live={loaded.is_live}, as_of={loaded.as_of}")
    return 0 if (loaded.source == nasa_data.ARCHIVED and not loaded.is_live) else 1


if __name__ == "__main__":
    sys.exit(main())
