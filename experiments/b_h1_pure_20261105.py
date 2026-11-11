import argparse
import hashlib
import json
import math
import os
import platform
import random
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "b_h1_pure_20261105"
N = 32
RHO = 0.5
CAP = 8.0
SEEDS = list(range(6101, 6109))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def cycle_power(n, p=2):
    edges = set()
    for i in range(n):
        for d in range(1, p + 1):
            edges.add(tuple(sorted((i, (i + d) % n))))
    return sorted(edges)


def workload(seed, kind):
    rng = random.Random(seed)
    order = list(range(N))
    rng.shuffle(order)
    cat = [i // 4 for i in range(N)]
    rows = []
    if kind == "category":
        for c in range(8):
            rows.append([1.0 if cat[i] == c else 0.0 for i in order])
        rows += [[1.0 if cat[i] in {c, (c + 1) % 8} else 0.0 for i in order] for c in range(2)]
    elif kind == "range":
        for _ in range(10):
            lo = rng.randrange(0, 6)
            hi = rng.randrange(lo + 1, 9)
            rows.append([1.0 if lo <= cat[i] < hi else 0.0 for i in order])
        rows.append([1.0 if cat[i] < 4 else 0.0 for i in order])
    elif kind == "mixed":
        for c in range(4):
            rows.append([1.0 if cat[i] == c else 0.0 for i in order])
        for _ in range(6):
            chosen = {rng.randrange(8) for _ in range(3)}
            rows.append([1.0 if cat[i] in chosen else 0.0 for i in order])
        for _ in range(4):
            rows.append([1.0 if rng.random() < 0.45 else 0.0 for _ in order])
    elif kind == "iid":
        for _ in range(16):
            rows.append([1.0 if rng.random() < 0.5 else 0.0 for _ in order])
    else:
        raise ValueError(kind)
    rows.append([1.0] * N)
    return rows, order


def solve_diag(A):
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            x = A[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if x <= 1e-12:
                    raise ValueError("non-positive covariance")
                L[i][j] = math.sqrt(x)
            else:
                L[i][j] = x / L[j][j]
    diag = []
    for target in range(n):
        y = [0.0] * n
        for i in range(n):
            y[i] = ((1.0 if i == target else 0.0) - sum(L[i][k] * y[k] for k in range(i))) / L[i][i]
        x = [0.0] * n
        for i in range(n - 1, -1, -1):
            x[i] = (y[i] - sum(L[k][i] * x[k] for k in range(i + 1, n))) / L[i][i]
        diag.append(x[target])
    return diag


def privacy(a, edges, weights):
    worst = 0.0
    worst_case = None
    checks = 0
    for coalition in [()] + [(i,) for i in range(N)]:
        hidden = [i for i in range(N) if i not in coalition]
        pos = {v: j for j, v in enumerate(hidden)}
        A = [[0.0] * len(hidden) for _ in hidden]
        for i, v in enumerate(hidden):
            A[i][i] = float(a[v])
        for (u, v), w in zip(edges, weights):
            if u in pos and v in pos:
                i, j = pos[u], pos[v]
                A[i][i] += w
                A[j][j] += w
                A[i][j] -= w
                A[j][i] -= w
        inv_diag = solve_diag(A)
        checks += len(hidden)
        local = max(inv_diag) * 0.5 if inv_diag else 0.0
        if local > worst:
            worst = local
            worst_case = coalition
    return {"passed": worst <= RHO * (1.0 + 1e-8), "worst_rho": worst, "worst_coalition": list(worst_case or ()), "checks": checks}


def objective(W, a, edges, weights):
    s = [sum(row[i] * row[i] for row in W) for i in range(N)]
    c = [sum((row[u] - row[v]) ** 2 for row in W) for u, v in edges]
    return sum(x * y for x, y in zip(s, a)) + sum(x * y for x, y in zip(c, weights)), s, c


def harmonic_q(a, edges, weights):
    h = [[] for _ in range(N)]
    for (u, v), w in zip(edges, weights):
        h[u].append(w * a[v] / (a[v] + w))
        h[v].append(w * a[u] / (a[u] + w))
    return [a[i] + sum(h[i]) - (max(h[i]) if h[i] else 0.0) for i in range(N)]


def scale_to_harmonic(a0, w0, edges):
    def candidate(scale):
        a = [scale * x for x in a0]
        w = [scale * x for x in w0]
        return a, w, min(harmonic_q(a, edges, w))
    lo, hi = 0.0, CAP / max(max(a0), max(w0, default=0.0), 1e-12)
    if candidate(hi)[2] < 1.0:
        return None
    for _ in range(70):
        mid = (lo + hi) / 2.0
        if candidate(mid)[2] >= 1.0:
            hi = mid
        else:
            lo = mid
    a, w, _ = candidate(hi * (1.0 + 1e-8))
    if max(a + w) > CAP * (1.0 + 1e-7):
        return None
    return a, w


def harmonic_candidate(W, edges):
    _, s, c = objective(W, [1.0] * N, edges, [0.0] * len(edges))
    ms = sum(s) / N
    mc = sum(c) / max(1, len(c))
    best = None
    for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
        for beta in (0.0, 0.5, 1.0):
            for kappa in (0.25, 0.5, 1.0, 2.0):
                a0 = [max(1e-4, (s[i] / ms) ** alpha) for i in range(N)]
                w0 = [max(1e-4, kappa * (max(c[j], 1e-12) / mc) ** beta) for j in range(len(edges))]
                scaled = scale_to_harmonic(a0, w0, edges)
                if scaled is None:
                    continue
                a, w = scaled
                val, _, _ = objective(W, a, edges, w)
                if best is None or val < best[0]:
                    best = (val, a, w, alpha, beta, kappa)
    if best is None:
        return None
    _, a, w, alpha, beta, kappa = best
    return {"a": a, "w": w, "alpha": alpha, "beta": beta, "kappa": kappa, "q_min": min(harmonic_q(a, edges, w))}


def uniform_candidate(W, edges):
    best = None
    # Closed-form harmonic bound family; keep only cap-feasible candidates and
    # recertify every empty/singleton induced view with the direct inverse.
    h = N - 1
    gap = min(2.0, 4.0 * math.sin(math.pi / N) ** 2)
    for gamma in [0.05 + i * (h - 1.0 - 0.05) / 240.0 for i in range(241)]:
        a = (1.0 + gamma) / h
        w = a * ((h - 1.0) / gamma - 1.0) / gap
        if max(a, w) > CAP:
            continue
        aa, ww = [a] * N, [w] * len(edges)
        cert = privacy(aa, edges, ww)
        if not cert["passed"]:
            scale = cert["worst_rho"] / RHO * (1.0 + 1e-8)
            aa, ww = [x * scale for x in aa], [x * scale for x in ww]
            if max(aa + ww) > CAP * (1.0 + 1e-7):
                continue
            cert = privacy(aa, edges, ww)
        val, _, _ = objective(W, aa, edges, ww)
        if cert["passed"] and (best is None or val < best[0]):
            best = (val, aa, ww, gamma, cert)
    if best is None:
        return None
    _, aa, ww, gamma, cert = best
    return {"a": aa, "w": ww, "gamma": gamma, "certificate": cert}


def evaluate_parent(seed, kind):
    W, order = workload(seed, kind)
    edges = cycle_power(N, 2)
    methods = {}
    indep_a, indep_w = [1.0] * N, [0.0] * len(edges)
    methods["independence"] = {"a": indep_a, "w": indep_w, "certificate": privacy(indep_a, edges, indep_w)}
    uniform = uniform_candidate(W, edges)
    if uniform is not None:
        methods["uniform"] = uniform
    harmonic = harmonic_candidate(W, edges)
    if harmonic is not None:
        harmonic["certificate"] = privacy(harmonic["a"], edges, harmonic["w"])
        methods["harmonic"] = harmonic
    rows = []
    for name, d in methods.items():
        val, s, c = objective(W, d["a"], edges, d["w"])
        rows.append({"method": name, "objective": val, "ratio_to_independence": val / methods["independence"].get("_objective", sum(s)),
                     "edge_count": sum(x > 1e-10 for x in d["w"]), "max_variance": max(d["a"] + d["w"]),
                     "privacy": d["certificate"], "harmonic_q_min": min(harmonic_q(d["a"], edges, d["w"]))})
    indep_obj = next(x["objective"] for x in rows if x["method"] == "independence")
    for row in rows:
        row["ratio_to_independence"] = row["objective"] / indep_obj
    portfolio = min(rows, key=lambda x: x["objective"])
    return {"seed": seed, "stratum": kind, "owner_count": N, "f": 1, "report_dimension": 1,
            "variance_cap": CAP, "workload": W, "owner_order": order, "workload_sha256": digest(W),
            "support": edges, "support_sha256": digest(edges), "methods": rows,
            "portfolio_method": portfolio["method"], "portfolio_objective": portfolio["objective"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    kinds = ["category", "category", "range", "range", "mixed", "mixed", "iid", "iid"]
    results = []
    for seed, kind in zip(SEEDS, kinds):
        path = OUT / f"parent_{seed}.json"
        if path.exists():
            results.append(json.loads(path.read_text()))
            continue
        result = evaluate_parent(seed, kind)
        result["runtime"] = {"python": platform.python_version(), "host": platform.node(), "pid": os.getpid()}
        path.write_text(json.dumps(result, indent=2) + "\n")
        results.append(result)
        print(json.dumps({"seed": seed, "stratum": kind, "portfolio": result["portfolio_method"],
                          "methods": [(x["method"], round(x["ratio_to_independence"], 6)) for x in result["methods"]]}), flush=True)
    summary = {"experiment": "B-H1 prospective matched-cap parent panel", "seeds": SEEDS,
               "strata": kinds, "owner_count": N, "f": 1, "report_dimension": 1, "variance_cap": CAP,
               "results": results, "wall_seconds": time.perf_counter() - t0,
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "status": "OBSERVED", "claim_scope": "independent synthetic workload parents; ideal Gaussian covariance only; no deployment claim"}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": "OBSERVED", "parents": len(results), "wall_seconds": summary["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
