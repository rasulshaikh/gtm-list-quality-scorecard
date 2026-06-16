#!/usr/bin/env python3
"""
GTM List Quality Scorecard
Grades a lead list across 8 dimensions before sending.
Outputs letter grade + markdown report.

Usage:
    python scorecard.py --list leads.csv --out scorecard.md
    python scorecard.py --list leads.csv --icp-file client-profile.yaml --out scorecard.md
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

BAD_TITLE_PATTERNS = [
    re.compile(r"\bintern(ship)?\b", re.I),
    re.compile(r"\bassistant\b", re.I),
    re.compile(r"\bcoordinator\b", re.I),
    re.compile(r"\bstudent\b", re.I),
    re.compile(r"\bpart.time\b", re.I),
    re.compile(r"\bretired\b", re.I),
    re.compile(r"\btrainee\b", re.I),
]

CATCH_ALL_LOCAL = {
    "info", "contact", "hello", "hi", "sales", "team", "support",
    "admin", "noreply", "no-reply", "office", "marketing",
}


def get_field(row: Dict, keys: List[str]) -> str:
    for k in keys:
        if row.get(k):
            return row[k]
    return ""


def letter_grade(score: int) -> str:
    if score >= 93:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def load_icp(path: Path) -> Dict:
    text = path.read_text()
    icp = {"titles": [], "industries": [], "headcount_min": 0, "headcount_max": float("inf")}
    title_m = re.search(r"job_titles:\s*\n((?:\s+-\s+.+\n?)+)", text)
    if title_m:
        icp["titles"] = [
            l.replace("-", "").strip()
            for l in title_m.group(1).split("\n")
            if l.strip().startswith("-")
        ]
    ind_m = re.search(r"industries_in:\s*\n((?:\s+-\s+.+\n?)+)", text)
    if ind_m:
        icp["industries"] = [
            l.replace("-", "").strip()
            for l in ind_m.group(1).split("\n")
            if l.strip().startswith("-")
        ]
    min_m = re.search(r"headcount_min:\s*(\d+)", text)
    if min_m:
        icp["headcount_min"] = int(min_m.group(1))
    max_m = re.search(r"headcount_max:\s*(\d+)", text)
    if max_m:
        icp["headcount_max"] = int(max_m.group(1))
    return icp


def is_catch_all(email: str) -> bool:
    local = (email.split("@")[0] if "@" in email else "").lower()
    return local in CATCH_ALL_LOCAL


def is_fake_name(first: str, last: str) -> bool:
    if not first or not last:
        return True
    if first.upper() == first and len(first) > 2:
        return True
    if any(c.isdigit() for c in first + last):
        return True
    fakes = {"admin", "info", "contact", "test", "user", "n/a", "na"}
    return first.lower() in fakes or last.lower() in fakes


def title_matches(title: str, icp_titles: List[str]) -> bool:
    t = title.lower()
    for i in icp_titles:
        il = i.lower()
        if il in t or t.split(" ")[0] in il:
            return True
    return False


def score_list(rows: List[Dict], icp: Optional[Dict] = None) -> Dict:
    total = len(rows)
    icp = icp or {"titles": [], "industries": [], "headcount_min": 0, "headcount_max": float("inf")}

    has_ver_col = any(
        r.get("email_status") or r.get("verification_status") or r.get("mv_status")
        for r in rows
    )
    verified = sum(
        1 for r in rows
        if (r.get("email_status") or r.get("verification_status") or r.get("mv_status") or "").lower()
        in ("ok", "verified", "valid")
    )
    verification_score = round((verified / total) * 100) if has_ver_col else 0

    seen, dupes = set(), 0
    for r in rows:
        e = (r.get("email") or "").lower()
        if not e:
            continue
        if e in seen:
            dupes += 1
        seen.add(e)
    dupe_pct = (dupes / total) * 100
    dupe_score = max(0, round(100 - dupe_pct * 20))

    domain_counts: Dict[str, int] = {}
    for r in rows:
        d = (r.get("company_domain") or (r.get("email") or "").split("@")[-1]).lower()
        if d:
            domain_counts[d] = domain_counts.get(d, 0) + 1
    avg_per_domain = total / len(domain_counts) if domain_counts else 0
    over_5 = sum(1 for n in domain_counts.values() if n > 5)
    domain_score = 100 if avg_per_domain < 2 else (60 if avg_per_domain < 5 else 30)

    title_relevant = 0
    if icp["titles"]:
        for r in rows:
            t = get_field(r, ["job_title", "title"])
            if t and title_matches(t, icp["titles"]):
                title_relevant += 1
    title_score = round((title_relevant / total) * 100) if icp["titles"] else -1

    bad_titles = sum(
        1 for r in rows
        if any(p.search(get_field(r, ["job_title", "title"])) for p in BAD_TITLE_PATTERNS)
    )
    bad_pct = (bad_titles / total) * 100
    bad_score = max(0, round(100 - bad_pct * 10))

    catch_alls = sum(1 for r in rows if is_catch_all(r.get("email", "")))
    catch_pct = (catch_alls / total) * 100
    catch_score = 100 if catch_pct < 5 else (max(0, round(100 - (catch_pct - 5) * 5)) if catch_pct < 15 else 0)

    icp_fit = 0
    if icp["industries"] or icp["headcount_min"] > 0:
        for r in rows:
            ind = (r.get("company_industry") or "").lower()
            hc = int(r.get("company_headcount") or 0)
            ind_ok = not icp["industries"] or any(i.lower() in ind for i in icp["industries"])
            hc_ok = hc == 0 or (icp["headcount_min"] <= hc <= icp["headcount_max"])
            if ind_ok and hc_ok:
                icp_fit += 1
    icp_score = round((icp_fit / total) * 100) if (icp["industries"] or icp["headcount_min"] > 0) else -1

    fake_names = sum(1 for r in rows if is_fake_name(r.get("first_name", ""), r.get("last_name", "")))
    name_score = round(((total - fake_names) / total) * 100)

    dims = [
        ("Email verification", verification_score, 2),
        ("Duplicate emails", dupe_score, 1),
        ("Duplicate domains", domain_score, 1),
        ("Title relevance", title_score, 1.5),
        ("Bad-title detection", bad_score, 1),
        ("Catch-all density", catch_score, 1),
        ("ICP fit", icp_score, 2),
        ("Name quality", name_score, 1),
    ]
    applicable = [(n, s, w) for n, s, w in dims if s >= 0]
    overall = round(sum(s * w for _, s, w in applicable) / sum(w for _, _, w in applicable))

    issues = []
    if not has_ver_col:
        issues.append("No email verification column — verify all emails before sending")
    elif verification_score < 100:
        issues.append(f"{total - verified} emails unverified — run MillionVerifier/Findymail")
    if dupes:
        issues.append(f"{dupes} duplicate emails ({dupe_pct:.1f}%) — deduplicate")
    if catch_alls:
        issues.append(f"{catch_alls} catch-all addresses ({catch_pct:.1f}%) — drop or deprioritize")
    if bad_titles:
        issues.append(f"{bad_titles} bad titles ({bad_pct:.1f}%) — tighten Prospeo filters")
    if over_5:
        issues.append(f"{over_5} domains with >5 leads — cap at 2-3 per domain")
    if icp_score >= 0 and icp_score < 80:
        issues.append(f"{total - icp_fit} leads outside ICP ({100 - icp_score:.1f}%)")
    if fake_names > total * 0.05:
        issues.append(f"{fake_names} rows with likely-fake names")

    return {
        "total": total,
        "grade": letter_grade(overall),
        "overall": overall,
        "dimensions": dims,
        "issues": issues[:5],
    }


def render_report(result: Dict, list_path: str) -> str:
    lines = [
        "# List Quality Scorecard",
        "",
        f"**File:** {list_path}",
        f"**Rows:** {result['total']}",
        f"**Grade:** {result['grade']} ({result['overall']}/100)",
        "",
        "## Dimensions",
        "",
    ]
    for i, (name, score, _) in enumerate(result["dimensions"], 1):
        s = f"{score}/100" if score >= 0 else "n/a (data missing)"
        lines.append(f"{i}. {name:<22} {s}")

    lines += ["", f"## Top {len(result['issues'])} issues to fix", ""]
    for i, issue in enumerate(result["issues"], 1):
        lines.append(f"{i}. {issue}")

    lines += [
        "",
        "## Pre-send checklist",
        "",
        "- [ ] Deduplicate by email",
        "- [ ] Verify all emails (MillionVerifier / Findymail / ZeroBounce)",
        "- [ ] Drop catch-all addresses if density >5%",
        "- [ ] Filter bad titles (intern, assistant, coordinator, student)",
        "- [ ] Cap per-domain concentration at 2-3 leads",
        "- [ ] Re-run scorecard after filtering",
        "- [ ] If grade <C, rebuild list instead of sending",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="GTM List Quality Scorecard")
    parser.add_argument("--list", required=True, help="Input CSV path")
    parser.add_argument("--icp-file", help="client-profile.yaml from ICP onboarding")
    parser.add_argument("--out", help="Output markdown path")
    parser.add_argument("--json", help="Output JSON path")
    args = parser.parse_args()

    list_path = Path(args.list)
    with list_path.open() as f:
        rows = list(csv.DictReader(f))
        rows = [{k.lower().strip(): v for k, v in r.items()} for r in rows]

    if not rows:
        print("Empty list.", file=sys.stderr)
        sys.exit(1)

    icp = load_icp(Path(args.icp_file)) if args.icp_file else None
    result = score_list(rows, icp)
    report = render_report(result, str(list_path))

    if args.out:
        Path(args.out).write_text(report)
    if args.json:
        import json
        Path(args.json).write_text(json.dumps(result, indent=2))
    print(report)


if __name__ == "__main__":
    main()