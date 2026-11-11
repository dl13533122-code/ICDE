import unittest,itertools,math
from fractions import Fraction as F
from src.finite_reports import *

class FiniteTests(unittest.TestCase):
    def test_all_tiny_bins(self):
        p=dict(DEFAULT,b=6,u=3,K=3,eta_bits=24,coefficient_bits=40)
        for coin in range(64):
            z=primitive(coin,p)
            self.assertEqual(z is None,not central(coin,p))
            if z:
                self.assertLessEqual(z[0],z[1])
                self.assertLessEqual(z[1]-z[0],constants(3)[0]/64+F(2,1<<24))
    def test_exact_fallback_every_tiny_endpoint(self):
        p=dict(DEFAULT,b=4,u=2,K=2,eta_bits=12,coefficient_bits=30)
        for j in range(4,13):
            fast=quantile(F(j,16),p);ref=fallback_quantile(F(j,16),p)
            self.assertLessEqual(fast[0],ref[1]);self.assertLessEqual(ref[0],fast[1])
            self.assertLessEqual(ref[1]-ref[0],F(1,1<<12))
    def test_default_tail_median_fallback(self):
        p=DEFAULT
        for prob in [F(1,1<<64),F(1,2),1-F(1,1<<64)]:
            fast=quantile(prob,p);ref=fallback_quantile(prob,p)
            self.assertLessEqual(fast[0],ref[1]);self.assertLessEqual(ref[0],fast[1])
            self.assertLessEqual(ref[1]-ref[0],F(1,1<<180))
    def test_rational_cdf_certificate(self):
        plan=fallback_plan(10,180)
        self.assertLess(plan['remainder']+plan['constant_error_upper']+plan['roundoff_upper'],plan['tolerance'])
        for x in [F(-10),F(-1),F(0),F(1),F(10)]:
            a=certified_cdf(x,plan)
            with ctx.workprec(1024): b=bounds((1+(arb(str(x))/arb(2).sqrt()).erf())/2)
            self.assertLessEqual(a[0],b[1]);self.assertLessEqual(b[0],a[1])
    def test_shared_opposite_masks_high_cancellation(self):
        p=DEFAULT;coin=(1<<255)+12345
        a=encode_report(F(1,4),(coin,F(1)),[(coin,F(10**30),1),(coin,F(10**30),-1)],p)
        self.assertIsNotNone(a);self.assertLessEqual(abs(F(a,1<<20)-F(1,4)),F(1,1<<20))
    def test_output_not_edge_rounding(self):
        p=dict(DEFAULT,b=8,u=3,K=3,grid_bits=0)
        # Interval close to an exact half-grid boundary must abort.
        self.assertIsNone(encode_report(F(1,2),(128,F(1,1<<200)),[],p))
    def test_tail_and_unequal_no_edge(self):
        self.assertIsNone(encode_report(0,(0,1),[],DEFAULT))
        for v in [F(1,10),F(7),F(10**20)]:
            self.assertIsNotNone(encode_report(0,(1<<255,v),[],DEFAULT))
    def test_uniform_bound_and_all_coordinates(self):
        peers=[dict(id=i,a=1.,neighbors={str(1-i):2.},report_dimension=2) for i in range(2)]
        b=public_bound(peers,attempts=22)
        self.assertTrue(b['passed']);self.assertEqual(b['M'],6)
        self.assertEqual(b['coordinates'],4)
        bad=dict(DEFAULT,b=8,u=3,K=3)
        self.assertFalse(public_bound(peers,bad,attempts=22)['passed'])
    def test_sqrt_uniform_exact(self):
        for x in [F(0),F(2),F(1,10),F(10**40),F(1,10**40)]:
            a,b=sqrt_interval(x);self.assertLessEqual(a*a,x);self.assertGreaterEqual(b*b,x)
            self.assertLessEqual(b-a,F(1,1<<220))
    def test_incident_coin_is_ideal_postprocessing(self):
        # Corrupt edge coins are public functions floor(2^b Phi(Z)).
        p=dict(DEFAULT,b=6,u=3,K=3)
        for coin in range(8,56):
            z=primitive(coin,p)
            with ctx.workprec(512):
                mid=arb(str((z[0]+z[1])/2));u=(1+(mid/arb(2).sqrt()).erf())/2
                self.assertEqual(int((u*64).floor().unique_fmpz()),coin)

    def test_public_wire_and_uniform_fallback_preflight(self):
        peers=[dict(id=i,a=1.,neighbors={},W=[[1.,1.],[-2.,.25]]) for i in range(2)]
        x=public_preflight(peers)
        self.assertTrue(x['passed'])
        self.assertLessEqual(x['maximum_numerator_bits'],511)
        self.assertLessEqual(x['maximum_denominator_bits'],512)
        plan=fallback_plan(10,180)
        self.assertLessEqual(2*plan['remainder']+plan['constant_error_upper']+plan['roundoff_upper'],plan['tolerance'])
        for peer in peers:peer['W'][0][0]=F(1,1<<600)
        with self.assertRaises(OverflowError):public_preflight(peers)

    def test_public_wire_refuses_huge_noise_before_sampling(self):
        with self.assertRaises(OverflowError):
            public_preflight([dict(id=0,a=10**320,neighbors={},W=[[1.]])])

if __name__=='__main__':unittest.main()
