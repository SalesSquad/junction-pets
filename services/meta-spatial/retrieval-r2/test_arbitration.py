import unittest
import numpy as np

from arbitration import assemble, calibrate, rrf, summarize, typed_decision
from retrieval import absent_family_scores


class ArbitrationTests(unittest.TestCase):
    def test_rrf_uses_ranks_and_preserves_absent_candidate_mask(self):
        a=np.array([[3.,2.,1.],[1.,3.,2.],[2.,1.,3.]],dtype=np.float32)
        np.testing.assert_allclose(rrf([a,a,a]),rrf([a*100+80,a*0.01,a+17]))
        absent=absent_family_scores(a,["a","b","c"])
        fused=rrf([absent,absent,absent])
        self.assertTrue(np.isneginf(np.diag(fused)).all())
        self.assertTrue(np.isfinite(fused[~np.eye(3,dtype=bool)]).all())

    def test_disagreement_requests_view_without_authorizing_capture(self):
        a=np.eye(3,dtype=np.float32)
        b=np.roll(a,1,axis=1)
        methods=assemble(a,b,b,0.5)
        scores,allowed=methods["fixed_rrf_agreement"]
        self.assertFalse(allowed.any())
        decision=typed_decision(scores[0],bool(allowed[0]),["a","b","c"],{"threshold":0.0})
        self.assertEqual(decision["decision"],"ask_new_view")
        self.assertFalse(decision["actual_device_action"])
        self.assertFalse(decision["physical_identity_verified"])
        self.assertFalse(decision["action_authorized"])

    def test_family_ties_cannot_be_hidden_by_agreement(self):
        families=[str(i) for i in range(320) for _ in range(2)]
        f=np.asarray(families)
        a=(f[:,None]==f[None,:]).astype(np.float32)
        normal=assemble(a,a,a,0.5)["fixed_rrf_agreement"]
        absent_a=absent_family_scores(a,families)
        absent=assemble(absent_a,absent_a,absent_a,0.5)["fixed_rrf_agreement"]
        measured=summarize(*normal,*absent,families,{"threshold":0.0})
        self.assertEqual(measured["wrong_present_accepted"],320)
        self.assertEqual(measured["accepted_precision"],0.5)
        policy=calibrate(*normal,*absent,families,0.01)
        final=summarize(*normal,*absent,families,policy)
        self.assertEqual(final["accepted"],0)

    def test_mask_mismatch_and_nonfinite_policy_are_rejected(self):
        a=np.eye(3,dtype=np.float32)
        b=a.copy();b[0,0]=-np.inf
        with self.assertRaisesRegex(ValueError,"candidate_masks"):
            rrf([a,a,b])
        with self.assertRaisesRegex(ValueError,"invalid_policy"):
            typed_decision([1,0],True,["a","b"],{"threshold":float("nan")})


if __name__=="__main__":
    unittest.main()
