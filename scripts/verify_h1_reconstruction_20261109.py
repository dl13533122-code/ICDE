import hashlib
import importlib.util
import json
import math
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments" / "b_h1_pure_20261105.py"
RECON = ROOT / "evidence" / "h1_harmonic_reconstruction_20261109"
OUT = ROOT / "evidence" / "h1_harmonic_reconstruction_verification_20261109.json"


def load_source():
    spec = importlib.util.spec_from_file_location("b_h1_pure_20261105", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    module = load_source()
    checks = []
    for path in sorted(RECON.glob("parent_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        harmonic = next(row for row in data["methods"] if row["method"] == "harmonic")
        workload = data["workload"]
        edges = [tuple(edge) for edge in data["support"]]
        a = harmonic["a"]
        w = harmonic["w"]
        value, _, _ = module.objective(workload, a, edges, w)
        q_min = min(module.harmonic_q(a, edges, w))
        privacy = module.privacy(a, edges, w)
        ok = (
            len(a) == data["owner_count"]
            and len(w) == len(edges)
            and q_min >= 1.0
            and privacy["passed"]
            and math.isclose(value, harmonic["objective"], rel_tol=1e-12, abs_tol=1e-10)
            and math.isclose(value, data["portfolio_objective"], rel_tol=1e-12, abs_tol=1e-10)
        )
        checks.append({
            "source": str(path.relative_to(ROOT)),
            "seed": data["seed"],
            "status": "LOCALLY_VERIFIED" if ok else "FAILED",
            "q_min_recomputed": q_min,
            "objective_recomputed": value,
            "objective_recorded": harmonic["objective"],
            "privacy": privacy,
        })
    result = {
        "source_script": str(SOURCE.relative_to(ROOT)),
        "source_script_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "reconstruction_dir": str(RECON.relative_to(ROOT)),
        "status": "LOCALLY_VERIFIED" if checks and all(x["status"] == "LOCALLY_VERIFIED" for x in checks) else "FAILED",
        "parents": checks,
        "scope": "independent recomputation of retained deterministic H1 harmonic records; no global optimality or deployment claim",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "parents": len(checks)}))


if __name__ == "__main__":
    main()
