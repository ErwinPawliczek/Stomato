"""Polite, resumable fetcher for the chemical-database source documents.

Downloads raw source pages into a cache directory *outside* the repository; the
parsed, cited tables are what gets committed (see ``scripts/chemdb/build.py``).
Nothing fetched is ever executed: pages are parsed as text by ``parse_nist.py``.

    python -I scripts/chemdb/fetch.py nist    <seed.txt> <cache-dir>
    python -I scripts/chemdb/fetch.py pubchem <seed.txt> <cache-dir>
    python -I scripts/chemdb/fetch.py janaf   <cache-dir>

Rate limits honoured: NIST WebBook robots.txt ``Crawl-delay: 5``; PubChem PUG
REST "no more than 5 requests per second" (one batched request every 0.4 s here).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "stomato-chemdb/1.0 (open process simulator; reference-data build; low rate)"
NIST_DELAY_S = 5.2
PUBCHEM_DELAY_S = 0.4
JANAF_DELAY_S = 1.5
#: Elements of the common process species, fetched first so a partial run is useful.
_JANAF_FIRST = ("C", "H", "N", "O", "S", "Cl", "F", "Br", "I", "P", "Si", "He", "Ne", "Ar", "Kr", "Xe")
PUBCHEM_BATCH = 100
PUBCHEM_PROPS = "MolecularFormula,MolecularWeight,InChIKey,CanonicalSMILES,IUPACName,Charge"


def _get(url: str, timeout: float = 45.0) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), bytes(response.read())
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def _seed(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def fetch_nist(seed: Path, cache: Path) -> int:
    """One WebBook page per CAS (Mask=7: gas, condensed, phase-change data)."""
    out = cache / "nist"
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for i, cas in enumerate(_seed(seed)):
        target = out / f"{cas}.html"
        marker = out / f"{cas}.missing"
        if target.exists() or marker.exists():
            continue
        digits = cas.replace("-", "")
        url = f"https://webbook.nist.gov/cgi/cbook.cgi?ID=C{digits}&Units=SI&Mask=7"
        try:
            status, body = _get(url)
        except (TimeoutError, OSError) as exc:
            print(f"{i} {cas}: network error {exc}", flush=True)
            failures += 1
            if failures > 20:
                return 1
            time.sleep(60.0)
            continue
        if status == 200 and b'id="Top"' in body:
            target.write_bytes(body)
        elif status == 200 or status == 404:
            marker.write_text(str(status))
        elif status in (403, 429, 503):
            print(f"{i} {cas}: HTTP {status}; backing off and stopping", flush=True)
            return 1
        else:
            print(f"{i} {cas}: HTTP {status}", flush=True)
        if i % 25 == 0:
            print(f"{i} {cas}", flush=True)
        time.sleep(NIST_DELAY_S)
    return 0


def fetch_pubchem(seed: Path, cache: Path) -> int:
    """Identity records: one batched POST-free GET per ``PUBCHEM_BATCH`` CIDs.

    The seed file holds ``cas<TAB>cid`` rows (CIDs from the identifier bank).
    """
    out = cache / "pubchem"
    out.mkdir(parents=True, exist_ok=True)
    rows = [line.split("\t") for line in _seed(seed)]
    cids = sorted({int(r[1]) for r in rows if len(r) > 1 and r[1].isdigit()})
    for start in range(0, len(cids), PUBCHEM_BATCH):
        target = out / f"batch_{start:06d}.json"
        if target.exists():
            continue
        chunk = ",".join(str(c) for c in cids[start : start + PUBCHEM_BATCH])
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{chunk}/property/{PUBCHEM_PROPS}/JSON"
        status, body = _get(url)
        if status != 200:
            print(f"batch {start}: HTTP {status}", flush=True)
            return 1
        json.loads(body)
        target.write_bytes(body)
        time.sleep(PUBCHEM_DELAY_S)
    return 0


def fetch_janaf(cache: Path) -> int:
    """Every NIST-JANAF table: element index pages first, then one text table each."""
    out = cache / "janaf"
    out.mkdir(parents=True, exist_ok=True)
    root = out / "periodic_table.html"
    if not root.exists():
        status, body = _get("https://janaf.nist.gov/periodic_table.html")
        if status != 200:
            return 1
        root.write_bytes(body)
    elements = sorted(set(re.findall(r"tables/([A-Za-z]+)-index\.html", root.read_text(errors="replace"))))
    tables: set[str] = set()
    for element in elements:
        index = out / f"{element}-index.html"
        if not index.exists():
            status, body = _get(f"https://janaf.nist.gov/tables/{element}-index.html")
            if status != 200:
                print(element, status, flush=True)
                continue
            index.write_bytes(body)
            time.sleep(JANAF_DELAY_S)
        tables |= set(re.findall(r'href="([A-Za-z]+-\d{3})\.html"', index.read_text(errors="replace")))
    print(len(elements), "elements", len(tables), "tables", flush=True)
    for name in sorted(tables, key=lambda t: (t.split("-")[0] not in _JANAF_FIRST, t)):
        target = out / f"{name}.txt"
        if target.exists():
            continue
        status, body = _get(f"https://janaf.nist.gov/tables/{name}.txt")
        if status == 200:
            target.write_bytes(body)
        else:
            print(name, status, flush=True)
        time.sleep(JANAF_DELAY_S)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("nist", "pubchem", "janaf"))
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    if args.source == "janaf":
        return fetch_janaf(args.paths[0])
    if args.source == "nist":
        return fetch_nist(args.paths[0], args.paths[1])
    return fetch_pubchem(args.paths[0], args.paths[1])


if __name__ == "__main__":
    sys.exit(main())
