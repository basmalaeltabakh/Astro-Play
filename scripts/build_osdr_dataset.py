"""Build the curated offline OSDR dataset (data/osdr_studies.json) from live NASA OSDR metadata.

Usage:  python scripts/build_osdr_dataset.py [--force]

The studies below were hand-selected by the project team. For each one this script retrieves the REAL study metadata from
the official OSDR Biological Data API (https://visualization.osdr.nasa.gov/biodata/api/ , no API key needed) and stores:
  * "verified": the normalized metadata exactly as NASA returned it (title and description verbatim, in English);
  * "app":      our own notes (topic and why we picked it), kept separate from NASA's facts.
Only study-level metadata is stored: no data files, samples or restricted data are downloaded or redistributed.

If any study cannot be retrieved, nothing is written (records are never made up). An existing dataset is never
overwritten silently: its contents are shown first and --force is required. After writing, the file is verified and
loaded with the network disabled to prove it works offline.
"""
import argparse
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astro import config, osdr_data  # noqa: E402
from astro.fileio import atomic_write_text  # noqa: E402

# (accession, topic, why we selected it). The reasons describe relevance only: they make no claims about findings.
SELECTION = [
    ("OSD-655", "plants", "Flight testing of growing leafy greens for crew food on the International Space Station: relevant to food production for Life Support."),
    ("OSD-745", "plants", "Lettuce grown on the International Space Station and analyzed for nutrition and microbes: relevant to growing food in space."),
    ("OSD-670", "plants", "A ground-based study, not done in space, of growing crops in asteroid regolith: relevant to growing food away from Earth."),
    ("OSD-46", "radiation", "A ground-based study, not done in space, of plant seedlings treated with gamma rays and heavy ions: relevant to how radiation affects living things."),
    ("OSD-431", "radiation", "A spaceflight study of human cells that looks at microgravity and space radiation together: relevant to protecting a crew."),
    ("OSD-202", "radiation", "A ground-based model of spaceflight, not done in space, combining low-dose radiation with simulated weightlessness in mice: relevant to radiation on long missions."),
    ("OSD-48", "microgravity", "The first NASA Rodent Research validation flight to the International Space Station: relevant to how a body responds to spaceflight."),
    ("OSD-310", "microgravity", "Rats flown on Space Shuttle mission STS-62, looking at vertebral bone: relevant to how the body changes during spaceflight."),
    ("OSD-174", "health", "Hair follicle samples from astronauts living on the International Space Station: relevant to human adaptation to a closed space environment."),
    ("OSD-569", "health", "Blood measurements from the private crew of the SpaceX Inspiration4 mission, sampled before, during and after flight: relevant to human health in spaceflight."),
    ("OSD-65", "microbes", "A survey of microbes on International Space Station surfaces: relevant to keeping a closed habitat clean."),
    ("OSD-26", "microbes", "A study of microbes in dust from the International Space Station and spacecraft assembly facilities: relevant to habitat hygiene."),
    ("OSD-267", "microbes", "Microbes on lettuce grown on the International Space Station: relevant to food and habitat hygiene."),
]


def describe_existing(path: Path) -> None:
    print(f"A dataset already exists at {path}:")
    d = osdr_data._read_json(path) or {}
    studies = d.get("studies") if isinstance(d.get("studies"), list) else []
    print(f"  retrieved {d.get('retrieved')}   studies {len(studies)}")
    for s in studies:
        v, a = (s.get("verified") or {}), (s.get("app") or {})
        print(f"   {v.get('accession')} [{a.get('topic')}] {str(v.get('title'))[:70]}")
    problems = osdr_data.verify_offline(path)
    print("  integrity: " + ("OK" if not problems else "PROBLEMS: " + "; ".join(problems)))


def build(session=None, now=None, selection=None) -> dict:
    """Retrieve every selected study and return the dataset dict. Raises osdr_data.OsdrError if any is unavailable."""
    now = now or dt.datetime.now()
    selection = SELECTION if selection is None else selection
    accessions = [a for a, _, _ in selection]
    records, errors = osdr_data.fetch_studies(accessions, session, now.date())
    if errors or len(records) != len(set(accessions)):
        raise osdr_data.OsdrError("could not retrieve: " + ", ".join(f"{a} ({e})" for a, e in sorted(errors.items())))
    by_acc = {r["accession"]: r for r in records}
    return {
        "dataset": "Outpost Command curated NASA OSDR study metadata",
        "retrieved": now.date().isoformat(),
        "provenance": {
            "source": "NASA Open Science Data Repository (OSDR) Biological Data API, version 2.0.0",
            "base_url": config.OSDR_BASE_URL,
            "documentation": ["https://www.nasa.gov/osdr-api/", "https://visualization.osdr.nasa.gov/biodata/api/"],
            "authentication": "none",
            "endpoint": "GET /v2/dataset/{accession}/ (study-level metadata only)",
            "selection": "Hand-selected by the Astro Play team for relevance to Outpost Command topics.",
            "verified_vs_app_text": "Everything under 'verified' is copied from the API (title and description verbatim, "
                                    "in English). Everything under 'app' is written by the Astro Play team. No data files, "
                                    "samples or restricted data are included.",
        },
        "studies": [{"verified": by_acc[a], "app": {"topic": t, "why_selected": why}, "retrieved": now.date().isoformat()}
                    for a, t, why in selection],
    }


def main(argv=None, session=None) -> int:
    ap = argparse.ArgumentParser(description="Build data/osdr_studies.json from the official OSDR API.")
    ap.add_argument("--force", action="store_true", help="replace an existing dataset")
    args = ap.parse_args(argv)
    target = Path(config.OSDR_STUDIES_PATH)
    if target.exists():
        describe_existing(target)
        if not args.force:
            print("Not overwriting. Re-run with --force to replace it.")
            return 2
    try:
        data = build(session)
    except osdr_data.OsdrError as e:
        print(f"FAILED: {e}. The dataset was not changed.")
        return 1
    atomic_write_text(target, json.dumps(data, indent=1, ensure_ascii=False))
    print(f"OK   dataset written to {target}   ({len(data['studies'])} studies, retrieved {data['retrieved']})")
    problems = osdr_data.verify_offline(target)
    if problems:
        print("FAILED verification: " + "; ".join(problems))
        return 1
    with tempfile.TemporaryDirectory() as tmp:                  # load it the way the game does with no network
        loaded = osdr_data.get_studies(cache_path=Path(tmp) / "none.json", offline_path=target, allow_network=False)
    print(f"     verified; offline load -> source={loaded.source!r}, studies={len(loaded.entries)}, live={loaded.is_live}")
    return 0 if (loaded.source == osdr_data.OFFLINE and len(loaded.entries) == len(data["studies"])) else 1


if __name__ == "__main__":
    sys.exit(main())
