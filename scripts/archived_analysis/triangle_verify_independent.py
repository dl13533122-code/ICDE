"""Independent stdlib-only rational recheck of the five triangle certificates.

No optimizer, project import, numerical library, or claimed solver status is used.
The full covariance inverse is formed by 3x3 cofactors and checked by multiplication.
Run only on the authorized compute host within the shared scientific deadline.
"""
import argparse, hashlib, json, pathlib, socket, sys, time
from fractions import Fraction as F

EDGES = ((0, 1), (0, 2), (1, 2))
S = (F(1), F(1), F(3))
C = (F(0), F(2), F(2))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def rat(token):
    a, b = token.split('/')
    def integer(x):
        return int(x, 16 if x.lstrip('+-').lower().startswith('0x') else 10)
    return F(integer(a), integer(b))


def vector(tokens):
    return [rat(x) for x in tokens]


def loss(a, w):
    return sum(S[i]*a[i] for i in range(3)) + sum(C[e]*w[e] for e in range(3))


def domain(a, w, tau):
    check(len(a) == len(w) == 3, 'Wrong dimensions')
    check(all(x > 0 for x in a) and all(x >= 0 for x in w), 'Invalid signs')
    check(sum(w) <= tau, 'Edge budget exceeded')


def inverse3(matrix):
    cof = []
    for i in range(3):
        row = []
        for j in range(3):
            rows = [k for k in range(3) if k != i]
            cols = [k for k in range(3) if k != j]
            determinant2 = matrix[rows[0]][cols[0]]*matrix[rows[1]][cols[1]] - matrix[rows[0]][cols[1]]*matrix[rows[1]][cols[0]]
            row.append((-1)**(i+j)*determinant2)
        cof.append(row)
    determinant = sum(matrix[0][j]*cof[0][j] for j in range(3))
    check(determinant > 0, 'Nonpositive covariance determinant')
    inv = [[cof[j][i]/determinant for j in range(3)] for i in range(3)]
    check(all(sum(matrix[i][k]*inv[k][j] for k in range(3)) == int(i == j)
              for i in range(3) for j in range(3)), 'Cofactor inverse residual')
    return inv


def constraints_and_gradients(method, a, w):
    # All constraints use g_i <= 0; gradients have their actual signed values.
    da = [[F(0)]*3 for _ in range(3)]
    dw = [[F(0)]*3 for _ in range(3)]
    if method == 'full_pairwise':
        matrix = [[a[i] if i == j else F(0) for j in range(3)] for i in range(3)]
        for (u, v), weight in zip(EDGES, w):
            matrix[u][u] += weight; matrix[v][v] += weight
            matrix[u][v] -= weight; matrix[v][u] -= weight
        inv = inverse3(matrix)
        g = [inv[i][i]-1 for i in range(3)]
        for i in range(3):
            for k in range(3): da[i][k] = -inv[i][k]**2
            for e, (u, v) in enumerate(EDGES): dw[i][e] = -(inv[i][u]-inv[i][v])**2
        return g, da, dw
    check(method == 'harmonic', 'Unknown family')
    q = list(a)
    for i in range(3): da[i][i] = -1
    for e, ((u, v), weight) in enumerate(zip(EDGES, w)):
        for i, j in ((u, v), (v, u)):
            q[i] += a[j]*weight/(a[j]+weight)
            da[i][j] -= weight**2/(a[j]+weight)**2
            dw[i][e] -= a[j]**2/(a[j]+weight)**2
    return [1-x for x in q], da, dw


def verify_method(name, record, tau):
    check(record['method'] == name, 'Method label mismatch')
    ref = record['reference']; a = vector(ref['anchors']); w = vector(ref['edge_variances'])
    domain(a, w, tau)
    check(rat(ref['objective']) == loss(a, w), 'Reference objective mismatch')
    check(rat(ref['total_edge_variance']) == sum(w), 'Reference sum mismatch')
    dual = record['lower_certificate']; lam = vector(dual['multipliers'])
    check(len(lam) == 3 and min(lam) >= 0, 'Invalid dual multipliers')
    g, da, dw = constraints_and_gradients(name, a, w)
    anchor_gradient = [S[k]+sum(lam[i]*da[i][k] for i in range(3)) for k in range(3)]
    check(anchor_gradient == [0, 0, 0], 'Unbounded anchor term in tangent lower bound')
    edge_gradient = [C[e]+sum(lam[i]*dw[i][e] for i in range(3)) for e in range(3)]
    constant = loss(a, w)+sum(lam[i]*g[i] for i in range(3))-sum(edge_gradient[e]*w[e] for e in range(3))
    lower = constant+tau*min([F(0)]+edge_gradient)
    check(vector(dual['constraint_values']) == g, 'Dual constraints mismatch')
    check(vector(dual['anchor_stationarity_residual']) == [0, 0, 0], 'Stored stationarity mismatch')
    check(vector(dual['edge_lagrangian_gradient']) == edge_gradient, 'Edge gradient mismatch')
    check(rat(dual['simplex_minimum_coefficient']) == min([F(0)]+edge_gradient), 'Simplex minimum mismatch')
    check(rat(dual['lower_bound']) == lower, 'Lower bound mismatch')
    primal = record['primal_certificate']; ap = vector(primal['anchors']); wp = vector(primal['edge_variances'])
    domain(ap, wp, tau)
    delta = rat(primal['anchor_increment'])
    check(delta >= 0 and ap == [x+delta for x in a] and wp == w, 'Invalid anchor repair')
    gp, _, _ = constraints_and_gradients(name, ap, wp)
    check(max(gp) <= 0 and vector(primal['constraint_values']) == gp, 'Primal privacy failed')
    upper = loss(ap, wp)
    check(rat(primal['objective']) == upper and rat(primal['total_edge_variance']) == sum(wp), 'Primal fields mismatch')
    interval = record['interval']; width = upper-lower; target = tau**3/3200
    for key, value in {'lower':lower, 'upper':upper, 'width':width, 'target_width':target}.items():
        check(rat(interval[key]) == value, 'Interval mismatch: '+key)
    check(0 <= width <= target, 'Requested exact bracket width not met')
    check(interval['width_target_met'] is True and record['status'] == 'CERTIFIED', 'Certificate status mismatch')
    return lower, upper


def run(args):
    raw = args.input.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    check(digest == args.expected_sha256, 'Input transport hash mismatch')
    obj = json.loads(raw); experiment = obj['experiment']
    check(obj['schema'] == 'triangle_exact_v1' and obj['complete'] is True, 'Incomplete or wrong schema')
    check(experiment['Q'] == [[1,1,1],[0,0,1]] and vector(experiment['frequencies']) == [1,2], 'Wrong workload')
    check(experiment['edge_order'] == [list(e) for e in EDGES] and experiment['collusion_budget'] == 0, 'Wrong graph/view')
    check(rat(experiment['r']) == 1 and vector(experiment['owner_mass']) == list(S) and vector(experiment['edge_cost']) == list(C), 'Wrong coefficients')
    check(rat(experiment['independent_loss']) == 5, 'Wrong independent reference')
    taus = [F(1,2**k) for k in range(3,8)]
    check(vector(obj['requested_taus']) == taus and [rat(c['tau']) for c in obj['cases']] == taus, 'Missing/reordered budgets')
    result = []
    for tau, case in zip(taus, obj['cases']):
        check(time.time() < args.deadline_epoch, 'Scientific deadline reached')
        check(not case['errors'] and set(case['methods']) == {'full_pairwise','harmonic'}, 'Missing/failed methods')
        pl, pu = verify_method('full_pairwise', case['methods']['full_pairwise'], tau)
        hl, hu = verify_method('harmonic', case['methods']['harmonic'], tau)
        lower, upper = hl-pu, hu-pl; bound = F(20,27)*tau**3/(1-tau)**2
        check(0 < lower <= upper <= bound, 'Positive/cubic gap claim not established')
        expected = {'lower':lower,'upper':upper,'width':upper-lower,'normalized_lower':lower/tau**3,
                    'normalized_upper':upper/tau**3,'theoretical_cubic_upper_bound':bound,'asymptotic_normalized_limit':F(1,32)}
        check(all(rat(case['gap'][k]) == v for k,v in expected.items()), 'Gap field mismatch')
        check(case['gap']['strictly_positive'] is True and case['gap']['upper_within_cubic_bound'] is True
              and case['status'] == 'CERTIFIED_POSITIVE_GAP', 'Gap status mismatch')
        result.append({'tau':str(tau),'both_full_dimensional_bounds_checked':True,'positive_gap':True,
                       'normalized_lower_decimal':float(lower/tau**3),'normalized_upper_decimal':float(upper/tau**3)})
    check(time.time() <= args.deadline_epoch, 'Scientific deadline exceeded')
    return {'passed':True,'input_sha256':digest,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
            'hostname':socket.gethostname(),'python_version':sys.version,'methods_verified':10,'cases':result,
            'algorithm':'independent exact cofactor inverse and signed convex Lagrangian tangent checks',
            'deadline_epoch':args.deadline_epoch,'finished_epoch':time.time()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=pathlib.Path,required=True);parser.add_argument('--output',type=pathlib.Path,required=True)
    parser.add_argument('--expected-sha256',required=True);parser.add_argument('--deadline-epoch',type=float,required=True)
    args = parser.parse_args(); start = time.time()
    try: result = run(args); status = 0
    except Exception as error: result = {'passed':False,'error':type(error).__name__+': '+str(error),'hostname':socket.gethostname()};status = 2
    result['elapsed_seconds'] = time.time()-start
    args.output.parent.mkdir(parents=True,exist_ok=True)
    check(not args.output.exists(), 'Refusing to overwrite an earlier verification result')
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(result,sort_keys=True),flush=True)
    return status


if __name__ == '__main__': sys.exit(main())
