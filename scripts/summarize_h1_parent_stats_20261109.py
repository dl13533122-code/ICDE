import hashlib
import json
import pathlib
import statistics


ROOT = pathlib.Path(__file__).resolve().parents[1]
RECON = ROOT / "evidence" / "h1_harmonic_reconstruction_20261109"
VERIFY = ROOT / "evidence" / "h1_harmonic_reconstruction_verification_20261109.json"
OUT = ROOT / "evidence" / "h1_parent_level_statistics_20261109.json"


def mean(values):
    return sum(values) / len(values)


def stats(rows):
    ratios = [row["harmonic_ratio_to_independence"] for row in rows]
    improvements = [1.0 - x for x in ratios]
    return {
        "parents": len(rows),
        "seeds": [row["seed"] for row in rows],
        "harmonic_wins": sum(x < 1.0 for x in ratios),
        "harmonic_nonwins": sum(x >= 1.0 for x in ratios),
        "ratio_mean": mean(ratios),
        "ratio_median": statistics.median(ratios),
        "ratio_min": min(ratios),
        "ratio_max": max(ratios),
        "improvement_mean": mean(improvements),
        "improvement_median": statistics.median(improvements),
        "improvement_min": min(improvements),
        "improvement_max": max(improvements),
        "rows": rows,
    }


def main():
    rows = []
    for path in sorted(RECON.glob("parent_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        methods = {row["method"]: row for row in data["methods"]}
        rows.append({
            "seed": data["seed"],
            "stratum": data["stratum"],
            "independence_objective": methods["independence"]["objective"],
            "uniform_objective": methods["uniform"]["objective"],
            "harmonic_objective": methods["harmonic"]["objective"],
            "harmonic_ratio_to_independence": methods["harmonic"]["ratio_to_independence"],
            "uniform_ratio_to_independence": methods["uniform"]["ratio_to_independence"],
            "harmonic_q_min": methods["harmonic"]["harmonic_q_min"],
            "privacy_passed": methods["harmonic"]["privacy"]["passed"],
        })
    groups = {}
    for row in rows:
        groups.setdefault(row["stratum"], []).append(row)
    result = {
        "status": "LOCALLY_VERIFIED",
        "reconstruction_dir": str(RECON.relative_to(ROOT)),
        "reconstruction_summary_sha256": hashlib.sha256((RECON / "summary.json").read_bytes()).hexdigest(),
        "verification_record": str(VERIFY.relative_to(ROOT)),
        "parent_count": len(rows),
        "overall": stats(rows),
        "by_stratum": {name: stats(value) for name, value in sorted(groups.items())},
        "scope": "parent-level summary for the eight frozen deterministic H1 parents; not a 32-parent population estimate and not a deployment claim",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "parents": len(rows), "strata": sorted(groups)}))


if __name__ == "__main__":
    main()
