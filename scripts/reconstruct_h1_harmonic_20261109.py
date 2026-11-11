import hashlib
import importlib.util
import json
import pathlib
import platform
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments" / "b_h1_pure_20261105.py"
OUT = ROOT / "evidence" / "h1_harmonic_reconstruction_20261109"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source():
    spec = importlib.util.spec_from_file_location("b_h1_pure_20261105", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def evaluate(module, seed, kind):
    workload, order = module.workload(seed, kind)
    edges = module.cycle_power(module.N, 2)
    methods = {}
    indep_a, indep_w = [1.0] * module.N, [0.0] * len(edges)
    methods["independence"] = {
        "a": indep_a,
        "w": indep_w,
        "certificate": module.privacy(indep_a, edges, indep_w),
    }
    uniform = module.uniform_candidate(workload, edges)
    if uniform is not None:
        methods["uniform"] = uniform
    harmonic = module.harmonic_candidate(workload, edges)
    if harmonic is not None:
        harmonic["certificate"] = module.privacy(harmonic["a"], edges, harmonic["w"])
        methods["harmonic"] = harmonic
    rows = []
    for name, data in methods.items():
        value, s, c = module.objective(workload, data["a"], edges, data["w"])
        rows.append({
            "method": name,
            "a": data["a"],
            "w": data["w"],
            "objective": value,
            "ratio_to_independence": value / sum(s),
            "edge_count": sum(x > 1e-10 for x in data["w"]),
            "max_variance": max(data["a"] + data["w"]),
            "privacy": data["certificate"],
            "harmonic_q_min": min(module.harmonic_q(data["a"], edges, data["w"])),
        })
    independent = next(row["objective"] for row in rows if row["method"] == "independence")
    for row in rows:
        row["ratio_to_independence"] = row["objective"] / independent
    portfolio = min(rows, key=lambda row: row["objective"])
    return {
        "seed": seed,
        "stratum": kind,
        "owner_count": module.N,
        "f": 1,
        "report_dimension": 1,
        "variance_cap": module.CAP,
        "workload": workload,
        "owner_order": order,
        "workload_sha256": module.digest(workload),
        "support": edges,
        "support_sha256": module.digest(edges),
        "methods": rows,
        "portfolio_method": portfolio["method"],
        "portfolio_objective": portfolio["objective"],
    }


def main():
    module = load_source()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    kinds = ["category", "category", "range", "range", "mixed", "mixed", "iid", "iid"]
    results = []
    for seed, kind in zip(module.SEEDS, kinds):
        result = evaluate(module, seed, kind)
        result["runtime"] = {
            "python": platform.python_version(),
            "host": platform.node(),
            "pid": __import__("os").getpid(),
        }
        (OUT / f"parent_{seed}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        results.append(result)
    summary = {
        "experiment": "B-H1 harmonic coefficient reconstruction from frozen source",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha256(SOURCE),
        "seeds": module.SEEDS,
        "strata": kinds,
        "results": results,
        "wall_seconds": time.perf_counter() - t0,
        "status": "LOCALLY_RECONSTRUCTED",
        "claim_scope": "reconstruction of saved deterministic H1 parents; ideal Gaussian covariance only; no new scientific claim",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "parents": len(results), "wall_seconds": summary["wall_seconds"]}))


if __name__ == "__main__":
    main()
