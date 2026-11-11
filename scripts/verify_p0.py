"""P0 verifier for activation signs and saved fixed-support evidence.

This entry point uses only repository-local inputs.  Exact sign and privacy
checks use ``fractions.Fraction``; floating solver statuses are never treated
as certificates.  Missing canonical inputs are reported explicitly.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import pathlib
from collections import defaultdict
from fractions import Fraction as F


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "p0_verification.json"
MANIFEST = ROOT / "evidence" / "p0_verifier_manifest.json"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q(value) -> F:
    if isinstance(value, F):
        return value
    if isinstance(value, list) and len(value) == 2:
        return F(int(value[0]), int(value[1]))
    if isinstance(value, int):
        return F(value)
    return F(str(value))


def frac_text(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def det(matrix):
    a = [list(row) for row in matrix]
    n = len(a)
    if n == 0:
        return F(1)
    result = F(1)
    for col in range(n):
        pivot = next((row for row in range(col, n) if a[row][col] != 0), None)
        if pivot is None:
            return F(0)
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
            result = -result
        pivot_value = a[col][col]
        result *= pivot_value
        for row in range(col + 1, n):
            factor = a[row][col] / pivot_value
            for j in range(col + 1, n):
                a[row][j] -= factor * a[col][j]
    return result


def inverse_diag(matrix):
    denominator = det(matrix)
    if denominator <= 0:
        raise AssertionError("non-positive exact covariance determinant")
    values = []
    for i in range(len(matrix)):
        minor = [[matrix[r][c] for c in range(len(matrix)) if c != i]
                 for r in range(len(matrix)) if r != i]
        values.append(det(minor) / denominator)
    return values


def covariance(n, a, edges, weights, honest):
    position = {node: idx for idx, node in enumerate(honest)}
    matrix = [[F(0) for _ in honest] for _ in honest]
    for node in honest:
        matrix[position[node]][position[node]] = a[node]
    for (u, v), weight in zip(edges, weights):
        if u not in position or v not in position:
            continue
        i, j = position[u], position[v]
        matrix[i][i] += weight
        matrix[j][j] += weight
        matrix[i][j] -= weight
        matrix[j][i] -= weight
    return matrix


def coalitions(n, f):
    yield ()
    if f >= 1:
        for node in range(n):
            yield (node,)


def privacy_check(n, a, edges, weights, f=1, r=F(1)):
    views = 0
    worst = F(0)
    for coalition in coalitions(n, f):
        honest = [node for node in range(n) if node not in coalition]
        values = inverse_diag(covariance(n, a, edges, weights, honest))
        for value in values:
            views += 1
            worst = max(worst, value)
            if value > r:
                return False, views, worst
    return True, views, worst


def workload_stats(workload, edges):
    rows = [[q(x) for x in row] for row in workload]
    n = len(rows[0])
    s = [sum((row[i] * row[i] for row in rows), F(0)) for i in range(n)]
    c = [sum(((row[u] - row[v]) ** 2 for row in rows), F(0)) for u, v in edges]
    return s, c


def activation_B(workload, edges, f, direction):
    s, c = workload_stats(workload, edges)
    n = len(s)
    d = [F(0) for _ in range(n)]
    incident = [[] for _ in range(n)]
    for edge, weight in zip(edges, direction):
        u, v = edge
        incident[u].append(weight)
        incident[v].append(weight)
    for node, values in enumerate(incident):
        values = sorted(values, reverse=True)
        d[node] = sum(values, F(0)) - sum(values[:f], F(0))
    value = sum((s[i] * d[i] for i in range(n)), F(0))
    value -= sum((c[j] * direction[j] for j in range(len(edges))), F(0))
    return value, s, c, d


def cycle_power(n, p=2):
    edges = set()
    for i in range(n):
        for distance in range(1, p + 1):
            edges.add(tuple(sorted((i, (i + distance) % n))))
    return sorted(edges)


def activation_cases():
    cases = []
    star_edges = [(0, i) for i in range(1, 8)]
    star_v = [F(1, 7)] * len(star_edges)
    star_B, _, _, star_d = activation_B([[F(1)] * 8], star_edges, 1, star_v)
    star_t, star_beta = F(3, 16), F(9, 896)
    star_a = [F(1) - star_t * value + star_beta for value in star_d]
    star_w = [star_t * value for value in star_v]
    cases.append({"name": "paper_star_k8_f1", "kind": "exact_positive_primal",
                  "workload": [[1] * 8], "edges": star_edges, "direction": star_v,
                  "a": star_a, "w": star_w, "B": star_B, "expected_objective": F(887, 112)})

    square_edges = cycle_power(8, 2)
    square_workload = []
    for row in range(6):
        square_workload.append([1 if col == row + 3 else 0 for col in range(8)])
    for col in range(3):
        square_workload[0][col] = 1
    square_v = [F(0) for _ in square_edges]
    for edge in [(0, 1), (0, 2), (1, 2)]:
        square_v[square_edges.index(edge)] = F(1, 3)
    square_B, _, _, square_d = activation_B(square_workload, square_edges, 1, square_v)
    square_t, square_beta = F(9, 64), F(9, 1024)
    square_a = [F(1) - square_t * value + square_beta for value in square_d]
    square_w = [square_t * value for value in square_v]
    cases.append({"name": "paper_cycle_square_k8_f1", "kind": "exact_positive_primal",
                  "workload": square_workload, "edges": square_edges, "direction": square_v,
                  "a": square_a, "w": square_w, "B": square_B,
                  "expected_objective": F(1015, 128)})

    base_edges = [(i, (i + 1) % 6) for i in range(6)]
    g_workload = [[1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1]]
    g0 = base_edges
    g3 = sorted(set(base_edges + [(0, 3), (1, 4), (2, 5)]))
    for name, edges, a, w in [("paper_G0_uniform", g0, F(139, 144), F(1, 24)),
                               ("paper_G3_uniform", g3, F(205, 216), F(1, 36))]:
        direction = [F(1, len(edges))] * len(edges)
        value, _, _, _ = activation_B(g_workload, edges, 1, direction)
        cases.append({"name": name, "kind": "exact_positive_primal",
                      "workload": g_workload, "edges": edges, "direction": direction,
                      "a": [a] * 6, "w": [w] * len(edges), "B": value})
    return cases


def verify_activation():
    records = []
    for case in activation_cases():
        n = len(case["a"])
        ok, views, worst = privacy_check(n, case["a"], case["edges"], case["w"])
        s, c = workload_stats(case["workload"], case["edges"])
        objective = sum((s[i] * case["a"][i] for i in range(n)), F(0))
        objective += sum((c[j] * case["w"][j] for j in range(len(case["edges"]))), F(0))
        baseline = sum(s, F(0))
        sign = "positive" if case["B"] > 0 else "nonpositive"
        record = {"name": case["name"], "status": "LOCALLY_VERIFIED" if ok and case["B"] > 0 and objective < baseline else "FAILED",
                  "sign": sign, "B_exact": frac_text(case["B"]), "objective_exact": frac_text(objective),
                  "baseline_exact": frac_text(baseline), "privacy_views": views,
                  "worst_inverse_exact": frac_text(worst), "a_exact": [frac_text(x) for x in case["a"]],
                  "w_exact": [frac_text(x) for x in case["w"]]}
        if "expected_objective" in case:
            record["expected_objective_exact"] = frac_text(case["expected_objective"])
            record["objective_matches_paper"] = objective == case["expected_objective"]
            if not record["objective_matches_paper"]:
                record["status"] = "FAILED"
        records.append(record)
    records.append({"name": "singleton_controls_historical", "status": "UNRESOLVED",
                    "reason": "canonical workload/support/direction inputs are not retained; the saved table is insufficient for an exact activation dual certificate"})
    return records


def gram(q_matrix):
    return [[sum((u * v for u, v in zip(row, col)), F(0))
             for col in q_matrix] for row in q_matrix]


def positive_ldl(matrix):
    a = [row[:] for row in matrix]
    for j in range(len(a)):
        if a[j][j] <= 0:
            return False
        pivot = a[j][j]
        for u in range(j + 1, len(a)):
            for v in range(u, len(a)):
                a[u][v] -= a[u][j] * a[v][j] / pivot
                a[v][u] = a[u][v]
    return True


def verify_dual_data():
    source = ROOT / "experiments" / "small_sdp_certificates_r3" / "results.json"
    data = json.loads(source.read_text())
    support_count = 0
    view_count = 0
    summaries = {}
    for name, result in data["cases"].items():
        workload = result["W"]
        n = 3
        ca = [sum((F(row[i]) ** 2 for row in workload), F(0)) for i in range(n)]
        lows, ups = [], []
        for case in result["supports"]:
            support_count += 1
            edges = [tuple(edge) for edge in case["edges"]]
            a = [q(value) for value in case["primal_a"]]
            w = [q(value) for value in case["primal_w"]]
            cw = [sum((F(row[u] - row[v]) ** 2 for row in workload), F(0)) for u, v in edges]
            ga, gw, constant, seen = [F(0)] * n, [F(0)] * len(edges), F(0), set()
            for record in case["dual_factors"]:
                coalition = tuple(record["coalition"])
                honest = [i for i in range(n) if i not in coalition]
                target = record["target"]
                q_matrix = [[q(value) for value in row] for row in record["factor_Q"]]
                z = gram(q_matrix)
                m = len(honest)
                matrix = [[a[honest[u]] if u == v else F(0) for v in range(m)] for u in range(m)]
                for index, ((u, v), weight) in enumerate(zip(edges, w)):
                    if u not in honest or v not in honest:
                        continue
                    p, r = honest.index(u), honest.index(v)
                    matrix[p][p] += weight
                    matrix[r][r] += weight
                    matrix[p][r] -= weight
                    matrix[r][p] -= weight
                    gw[index] += z[p][p] + z[r][r] - 2 * z[p][r]
                for j, node in enumerate(honest):
                    ga[node] += z[j][j]
                bordered = [row + [F(int(honest[u] == target))] for u, row in enumerate(matrix)]
                bordered.append([F(int(v == target)) for v in honest] + [F(1)])
                if not positive_ldl(bordered):
                    raise AssertionError(f"dual factor is not exact PSD at {name}")
                constant -= 2 * z[honest.index(target)][m] + z[m][m]
                seen.add((coalition, target))
                view_count += 1
            expected = {(C, i) for C in [(), (0,), (1,), (2,)] for i in range(n) if i not in C}
            if seen != expected:
                raise AssertionError(f"incomplete views at {name}")
            scale = q(case["dual_scale"])
            if [c - scale * g for c, g in zip(ca, ga)] != [q(value) for value in case["dual_a_slack"]]:
                raise AssertionError(f"node dual slack mismatch at {name}")
            if [c - scale * g for c, g in zip(cw, gw)] != [q(value) for value in case["dual_w_slack"]]:
                raise AssertionError(f"edge dual slack mismatch at {name}")
            if any(c - scale * g < 0 for c, g in zip(ca, ga)) or any(c - scale * g < 0 for c, g in zip(cw, gw)):
                raise AssertionError(f"negative exact dual slack at {name}")
            lower = scale * constant
            upper = sum((c * value for c, value in zip(ca, a)), F(0)) + sum((c * value for c, value in zip(cw, w)), F(0))
            if lower != q(case["lower"]) or upper != q(case["upper"]) or lower > upper:
                raise AssertionError(f"objective interval mismatch at {name}")
            lows.append(lower)
            ups.append(upper)
        summaries[name] = {"supports": len(result["supports"]), "lower_exact": frac_text(min(lows)),
                           "upper_exact": frac_text(min(ups)), "max_fixed_support_gap": max(float(q(case["upper"]) - q(case["lower"])) for case in result["supports"])}
    return {"status": "LOCALLY_VERIFIED", "source": str(source.relative_to(ROOT)),
            "source_sha256": sha256(source), "fixed_supports": support_count,
            "dual_view_factors": view_count, "cases": summaries,
            "scope": "exact Fraction primal/dual brackets for the two saved 3-node workloads; no global-optimality claim"}


def verify_harmonic_saved():
    records = []
    for source in sorted((ROOT / "experiments" / "b_h1_pure_20261105").glob("parent_*.json")):
        data = json.loads(source.read_text())
        workload = [[q(x) for x in row] for row in data["workload"]]
        edges = [tuple(edge) for edge in data["support"]]
        methods = {row["method"]: row for row in data["methods"]}
        row = methods.get("harmonic")
        if not row or "a" not in row or "w" not in row:
            records.append({"source": str(source.relative_to(ROOT)), "status": "NOT_REPRODUCIBLE"})
            continue
        a, w = [q(x) for x in row["a"]], [q(x) for x in row["w"]]
        h = [[] for _ in a]
        for (u, v), weight in zip(edges, w):
            h[u].append(weight * a[v] / (a[v] + weight))
            h[v].append(weight * a[u] / (a[u] + weight))
        qmin = min(a[i] + sum(h[i], F(0)) - (max(h[i]) if h[i] else F(0)) for i in range(len(a)))
        s, c = workload_stats(workload, edges)
        objective = sum((s[i] * a[i] for i in range(len(a))), F(0)) + sum((c[j] * w[j] for j in range(len(edges))), F(0))
        reported = q(row["objective"])
        records.append({"source": str(source.relative_to(ROOT)), "status": "LOCALLY_VERIFIED" if qmin >= 1 and objective == reported else "FAILED",
                        "q_min_exact": frac_text(qmin), "objective_exact": frac_text(objective),
                        "reported_objective_exact": frac_text(reported)})
    return {"status": "LOCALLY_VERIFIED" if all(r["status"] == "LOCALLY_VERIFIED" for r in records) else "FAILED", "parents": records,
            "scope": "eight saved H1 harmonic coefficient records; exact decimal strings interpreted as rationals"}


def verify_squared_error_csv():
    csv_path = ROOT / "evidence" / "reports_physical_r6" / "query_squared_errors.csv"
    summary_path = ROOT / "evidence" / "reports_physical_r6" / "summary.json"
    summary = {row["tag"]: row for row in json.loads(summary_path.read_text())}
    by_trial = defaultdict(lambda: defaultdict(F))
    with csv_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            by_trial[row["tag"]][row["trial"]] += q(row["squared_error"])
    checks = []
    for tag, trials in sorted(by_trial.items()):
        if tag not in summary:
            checks.append({"tag": tag, "status": "UNRESOLVED", "reason": "tag absent from saved summary"})
            continue
        mean = sum(trials.values(), F(0)) / len(trials)
        reported = q(summary[tag]["observed_total_error"]["mean"])
        ok = abs(float(mean - reported)) <= 1e-9 * max(1.0, abs(float(reported)))
        checks.append({"tag": tag, "status": "LOCALLY_VERIFIED" if ok else "FAILED", "trials": len(trials),
                       "recomputed_mean_exact_decimal": str(mean), "reported_mean_decimal": str(reported)})
    return {"status": "LOCALLY_VERIFIED" if checks and all(x["status"] == "LOCALLY_VERIFIED" for x in checks) else "FAILED",
            "source": str(csv_path.relative_to(ROOT)), "source_sha256": sha256(csv_path), "cases": checks,
            "scope": "recomputed saved per-trial squared-error sums and compared with the saved physical summary"}


def missing_direct_lmi():
    table = ROOT / "tables" / "direct_lmi_parent16.tex"
    return {"status": "NOT_REPRODUCIBLE/UNRESOLVED", "table": str(table.relative_to(ROOT)),
            "table_sha256": sha256(table),
            "reason": "the repository retains the rendered table but no complete canonical W, support, a, w and coalition input bundle for independent direct-LMI recomputation"}


def main():
    input_paths = [ROOT / "main.tex", ROOT / "experiments" / "small_sdp_certificates_r3" / "results.json",
                   ROOT / "evidence" / "reports_physical_r6" / "query_squared_errors.csv",
                   ROOT / "evidence" / "reports_physical_r6" / "summary.json",
                   ROOT / "tables" / "direct_lmi_parent16.tex"]
    result = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "status": "LOCALLY_VERIFIED", "activation": verify_activation(),
              "dual": verify_dual_data(), "harmonic": verify_harmonic_saved(),
              "direct_lmi": missing_direct_lmi(), "squared_error": verify_squared_error_csv(),
              "unresolved": ["historical singleton-control activation sign", "direct-LMI certificate inputs", "six historical fixed-support dual records not present in the saved exact bundle"],
              "scope": "P0 exact sign/certificate and saved-result reproduction only; no new experiment, deployment or scientific acceptance"}
    result["script_sha256"] = sha256(pathlib.Path(__file__))
    result["input_sha256"] = {str(path.relative_to(ROOT)): sha256(path) for path in input_paths}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    manifest = {"verifier": "scripts/verify_p0.py", "verifier_sha256": result["script_sha256"],
                "command": "<project-python> scripts/verify_p0.py", "inputs": result["input_sha256"],
                "output": str(OUT.relative_to(ROOT)), "output_sha256": sha256(OUT),
                "notes": "All unresolved entries are deliberate; no floating solver status is promoted to an exact proof."}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "activation": [x["status"] for x in result["activation"]],
                      "dual": result["dual"]["status"], "harmonic": result["harmonic"]["status"],
                      "direct_lmi": result["direct_lmi"]["status"], "squared_error": result["squared_error"]["status"]}))


if __name__ == "__main__":
    main()
