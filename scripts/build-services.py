#!/usr/bin/env python3
"""Build service rule files from MetaCubeX meta-rules-dat BundleMRS.

Replaces the blackmatrix7 dependency for service rules (plan C step 2).

Inputs:
  --bundle-dir  extracted BundleMRS.7z (expects geo/geosite/*.mrs inside),
                OR --bundle-7z for the archive itself (extracted with py7zr)
  --supplements dir with *.txt supplement files (one domain per line,
                `+.domain` for suffix, `domain` for exact; `#` comments)
  --mihomo      path to the mihomo binary (for MRS <-> text conversion)
  --out         rules/ output directory

Mapping (geosite -> our file):
  Direct copies (MRS used as-is):
    apple, netflix, tiktok, youtube, spotify, amazon, google, openai,
    category-emby -> Apple_Domain, Netflix_Domain, TikTok_Domain,
    YouTube_Domain, Spotify_Domain, Amazon_Domain, Google_Domain,
    OpenAI_Domain, Emby
  Merges (MRS -> text -> merge + supplement -> dedup -> MRS):
    Microsoft.mrs = geosite/microsoft + geosite/linkedin + microsoft.txt
    iCloud.mrs    = geosite/icloud + icloud.txt
    Threads_Domain.mrs = geosite/threads + threads.txt

Frozen (NOT touched by this script; files stay in rules/ as-is):
  Apple.yaml (classical: keywords + IPs incl. 17.0.0.0/8, stable),
  Netflix_IP.mrs (BM7/QiuSimons 1,119 CIDRs; geoip netflix has only 122),
  Copilot_Domain.mrs + Copilot_IP.mrs (feed the Microsoft group; the
  Copilot web domains are covered by geosite microsoft's +.microsoft.com,
  and the OpenAI entries are shadowed by the GPT group's earlier rules).

Notes:
- geosite apple contains icloud domains, but the yaml evaluates the iCloud
  rule (line ~446) BEFORE the Apple rules (~447-448), so iCloud traffic
  still lands in the iCloud group. No filtering needed.
- Gemini/Claude domains are inline rules in the yaml (before Google_Domain),
  so google-gemini.mrs is not merged into Google_Domain.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DIRECT = {
    "apple": "Apple_Domain.mrs",
    "netflix": "Netflix_Domain.mrs",
    "tiktok": "TikTok_Domain.mrs",
    "youtube": "YouTube_Domain.mrs",
    "spotify": "Spotify_Domain.mrs",
    "amazon": "Amazon_Domain.mrs",
    "google": "Google_Domain.mrs",
    "openai": "OpenAI_Domain.mrs",
    "category-emby": "Emby.mrs",
}

MERGES = {
    # out file -> (geosite categories, supplement file or None)
    "Microsoft.mrs": (["microsoft", "linkedin"], "microsoft.txt"),
    "iCloud.mrs": (["icloud"], "icloud.txt"),
    "Threads_Domain.mrs": (["threads"], "threads.txt"),
}


def run_mihomo(mihomo: Path, args):
    r = subprocess.run([str(mihomo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"mihomo {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def mrs_to_entries(mihomo: Path, mrs_path: Path, tmpdir: Path) -> set[str]:
    txt = tmpdir / (mrs_path.stem + ".txt")
    run_mihomo(mihomo, ["convert-ruleset", "domain", "mrs", str(mrs_path), str(txt)])
    return {
        line.strip().lower()
        for line in txt.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def read_supplement(path: Path) -> set[str]:
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line.lower())
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-dir", type=Path, default=None)
    ap.add_argument("--bundle-7z", type=Path, default=None,
                    help="BundleMRS.7z archive; extracted with py7zr")
    ap.add_argument("--supplements", type=Path, required=True)
    ap.add_argument("--mihomo", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tmp", type=Path, default=Path(".tmp/services"))
    args = ap.parse_args()

    if bool(args.bundle_dir) == bool(args.bundle_7z):
        print("ERROR: pass exactly one of --bundle-dir / --bundle-7z", file=sys.stderr)
        sys.exit(1)

    # Resolve the mihomo path: subprocess needs a slash or a PATH lookup,
    # and Path("./mihomo") stringifies to "mihomo" (no slash).
    args.mihomo = args.mihomo.resolve()

    args.tmp.mkdir(parents=True, exist_ok=True)
    if args.bundle_7z:
        import py7zr

        bundle_dir = args.tmp / "bundle"
        targets = [f"geo/geosite/{c}.mrs" for c in DIRECT]
        for categories, _ in MERGES.values():
            targets += [f"geo/geosite/{c}.mrs" for c in categories]
        print(f"extracting {len(set(targets))} files from {args.bundle_7z} ...")
        with py7zr.SevenZipFile(args.bundle_7z) as a:
            a.extract(path=str(bundle_dir), targets=sorted(set(targets)))
        args.bundle_dir = bundle_dir

    geosite = args.bundle_dir / "geo" / "geosite"
    args.out.mkdir(parents=True, exist_ok=True)

    # Direct copies.
    for category, out_name in sorted(DIRECT.items()):
        src = geosite / f"{category}.mrs"
        if not src.exists():
            print(f"ERROR: missing {src}", file=sys.stderr)
            sys.exit(1)
        shutil.copyfile(src, args.out / out_name)
        print(f"{out_name}: copied from geosite/{category} ({src.stat().st_size} bytes)")

    # Merges.
    for out_name, (categories, supplement) in sorted(MERGES.items()):
        entries: set[str] = set()
        for category in categories:
            src = geosite / f"{category}.mrs"
            if not src.exists():
                print(f"ERROR: missing {src}", file=sys.stderr)
                sys.exit(1)
            got = mrs_to_entries(args.mihomo, src, args.tmp)
            print(f"  {out_name}: {category} -> {len(got)} entries")
            entries |= got
        if supplement:
            sup = read_supplement(args.supplements / supplement)
            print(f"  {out_name}: supplement {supplement} -> {len(sup)} entries")
            entries |= sup
        merged_txt = args.tmp / (Path(out_name).stem + ".txt")
        merged_txt.write_text("\n".join(sorted(entries)) + "\n", encoding="utf-8")
        run_mihomo(
            args.mihomo,
            ["convert-ruleset", "domain", "text", str(merged_txt), str(args.out / out_name)],
        )
        print(f"{out_name}: merged {len(entries)} entries -> {args.out / out_name}")

    print("done.")


if __name__ == "__main__":
    main()
