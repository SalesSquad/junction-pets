"""Focused R3 invariants; synthetic arrays never represent model quality."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

from visual_adapter import (epoch_batches, load_ablation, load_selected, make_batch,
                            make_torch_adapter, mine_visual_hard_negatives,
                            normalize_rows, project_features,
                            select_with_identity, symmetric_visual_loss)


class VisualAdapterTests(unittest.TestCase):
    def test_each_anchor_once_and_preserved_even_at_batch_two(self):
        rng=np.random.default_rng(43)
        q=normalize_rows(rng.normal(size=(33,8)))
        g=normalize_rows(q+0.05*rng.normal(size=q.shape))
        families=[f"family-{i//2}" for i in range(len(q))]
        hard=mine_visual_hard_negatives(q,g,families)
        for size in (2,3,8,15,16,31,128):
            for epoch in (0,1):
                counts=np.zeros(len(q),dtype=int)
                for batch in epoch_batches(families,hard,size,17,epoch):
                    counts[batch.anchors]+=1
                    self.assertLessEqual(len(batch.candidates),size)
                    self.assertEqual(len(set(batch.candidates.tolist())),len(batch.candidates))
                    np.testing.assert_array_equal(batch.candidates[batch.positive_columns],batch.anchors)
                    self.assertFalse(batch.exclude[np.arange(len(batch.anchors)),batch.positive_columns].any())
                np.testing.assert_array_equal(counts,np.ones(len(q),dtype=int))

    def test_family_variants_are_masked_not_promoted_to_positives(self):
        batch=make_batch([0,1],[0,1,2],["a","a","b"])
        np.testing.assert_array_equal(batch.positive_columns,[0,1])
        np.testing.assert_array_equal(batch.exclude,[[False,True,False],[True,False,False]])
        with self.assertRaisesRegex(ValueError,"anchor_was_dropped"):
            make_batch([2],[0,1],["a","a","b"])
        with self.assertRaisesRegex(ValueError,"no_valid_negative"):
            make_batch([0],[0,1],["a","a","b"])

    def test_mining_is_local_visual_and_excludes_same_family(self):
        q=np.array([[1,0],[1,0],[0.9,0.1],[0,1]],dtype=np.float32)
        families=["a","a","b","c"]
        hard=mine_visual_hard_negatives(q,q,families,4)
        self.assertEqual(int(hard[0,0]),2)
        for i,row in enumerate(hard):
            for j in row[row>=0]:
                self.assertLess(int(j),4)
                self.assertNotEqual(families[i],families[int(j)])
        # A global/dev index cannot be smuggled into a train-local batch table.
        bad=hard.copy();bad[0,0]=4
        with self.assertRaisesRegex(ValueError,"other_train_family"):
            list(epoch_batches(families,bad,2,17,0))

    def test_epoch_zero_matches_frozen_features_and_scores_exactly(self):
        rng=np.random.default_rng(71)
        q=normalize_rows(rng.normal(size=(7,768)))
        g=normalize_rows(rng.normal(size=(7,768)))
        weights={"a":rng.normal(size=(768,64)).astype(np.float32)*0.01,"b":np.zeros((64,768),dtype=np.float32)}
        np.testing.assert_array_equal(project_features(q,None),project_features(q,weights))
        np.testing.assert_array_equal(project_features(g,None),project_features(g,weights))
        np.testing.assert_array_equal(project_features(q,None)@project_features(g,None).T,project_features(q,weights)@project_features(g,weights).T)

    def test_no_dev_gain_and_exact_ties_keep_identity(self):
        baseline={"kind":"identity","epoch":0,"dev":{"recall_at_1":0.5,"mrr":0.6}}
        equal={"kind":"adapter","epoch":1,"dev":{"recall_at_1":0.5,"mrr":0.6}}
        worse={"kind":"adapter","epoch":2,"dev":{"recall_at_1":0.49,"mrr":0.9}}
        self.assertIs(select_with_identity(baseline,[worse,equal]),baseline)
        better={"kind":"adapter","epoch":3,"dev":{"recall_at_1":0.5,"mrr":0.600001}}
        self.assertIs(select_with_identity(baseline,[better]),better)
        with self.assertRaisesRegex(ValueError,"explicit_epoch_zero"):
            select_with_identity(equal,[worse])

    def test_identity_loading_and_primary_ablation_boundary(self):
        node={"kind":"identity","epoch":0,"checkpoint":None,"checkpoint_sha256":None,"recipe":"primary","preservation":0.0}
        ablation={**node,"recipe":"cosine_preservation_ablation","preservation":0.05}
        selection={"schema_version":1,"kind":"meta.visual_adapter.r3.selection","fresh_cal_test_evaluated":False,"primary":node,"confirmation_candidate":dict(node),"ablation":ablation}
        original=copy.deepcopy(selection)
        self.assertIsNone(load_selected(selection,"/path-not-read-for-identity"))
        self.assertIsNone(load_ablation(selection,"/path-not-read-for-identity"))
        self.assertEqual(selection,original)
        bad=copy.deepcopy(selection)
        bad["confirmation_candidate"]=dict(ablation)
        for loader in (load_selected,load_ablation):
            with self.assertRaisesRegex(ValueError,"must_match_frozen_primary"):
                loader(bad,"/path-not-read")
        bad=copy.deepcopy(selection)
        bad["ablation"]=dict(node)
        with self.assertRaisesRegex(ValueError,"unexpected_ablation_recipe"):
            load_ablation(bad,"/path-not-read")

    @unittest.skipUnless(importlib.util.find_spec("safetensors") is not None,"safetensors unavailable locally; checkpoint loading must run on executor")
    def test_primary_and_ablation_checkpoint_hash_shape_and_values(self):
        from safetensors.numpy import save_file
        rng=np.random.default_rng(91)
        primary={"a":rng.normal(size=(768,64)).astype(np.float32)*0.01,"b":rng.normal(size=(64,768)).astype(np.float32)*0.01}
        ablation={"a":rng.normal(size=(768,64)).astype(np.float32)*0.01,"b":rng.normal(size=(64,768)).astype(np.float32)*0.02}
        with tempfile.TemporaryDirectory(prefix="r3-checkpoint-test-") as root:
            root=Path(root)
            nodes={}
            for name,weights,preservation in (("primary",primary,0.0),("cosine_preservation_ablation",ablation,0.05)):
                path=root/(name+".safetensors")
                save_file(weights,str(path))
                nodes[name]={"kind":"adapter","epoch":1,"recipe":name,"preservation":preservation,"checkpoint":path.name,"checkpoint_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            selection={"schema_version":1,"kind":"meta.visual_adapter.r3.selection","fresh_cal_test_evaluated":False,"primary":nodes["primary"],"confirmation_candidate":dict(nodes["primary"]),"ablation":nodes["cosine_preservation_ablation"]}
            for loader,expected in ((load_selected,primary),(load_ablation,ablation)):
                loaded=loader(selection,root)
                for key in ("a","b"):
                    np.testing.assert_array_equal(loaded[key],expected[key])
            for key,loader in (("primary",load_selected),("ablation",load_ablation)):
                bad=copy.deepcopy(selection)
                bad[key]["checkpoint_sha256"]="0"*64
                if key=="primary":
                    bad["confirmation_candidate"]=dict(bad[key])
                with self.assertRaisesRegex(ValueError,"checkpoint_hash_mismatch"):
                    loader(bad,root)
                path=root/(key+"-bad-shape.safetensors")
                save_file({"a":np.ones((768,63),dtype=np.float32),"b":np.zeros((63,768),dtype=np.float32)},str(path))
                bad[key]["checkpoint"]=path.name
                bad[key]["checkpoint_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
                if key=="primary":
                    bad["confirmation_candidate"]=dict(bad[key])
                with self.assertRaisesRegex(ValueError,"unexpected_selected_adapter_shape"):
                    loader(bad,root)

    def test_nonfinite_and_wrong_checkpoint_dtype_rejected(self):
        x=np.array([[1,0]],dtype=np.float32)
        with self.assertRaisesRegex(ValueError,"dtype"):
            project_features(x,{"a":np.ones((2,1),dtype=np.float64),"b":np.zeros((1,2),dtype=np.float32)})
        with self.assertRaisesRegex(ValueError,"nonfinite_adapter"):
            project_features(x,{"a":np.ones((2,1),dtype=np.float32),"b":np.array([[np.nan,0]],dtype=np.float32)})
        with self.assertRaisesRegex(ValueError,"zero_embedding"):
            project_features(np.zeros((1,2),dtype=np.float32))

    @unittest.skipUnless(importlib.util.find_spec("torch") is not None,"Torch unavailable locally; actual step belongs to verified executor")
    def test_shared_adapter_cpu_step_has_finite_nonzero_update(self):
        import torch
        q=np.zeros((3,768),dtype=np.float32)
        q[0,0]=1;q[1,1]=1;q[2,2]=1
        g=q[[1,2,0]].copy()
        model=make_torch_adapter(768,64,17,"cpu")
        self.assertEqual(sum(p.numel() for p in model.parameters()),98304)
        batch=make_batch([0],[0,1,2],["a","b","c"])
        initial=model.b.detach().clone()
        loss,parts=symmetric_visual_loss(model,torch.tensor(q),torch.tensor(g),batch,0.07,0.0)
        self.assertEqual(parts["loss_anchor_rows"],1)
        self.assertEqual(parts["candidate_rows"],3)
        loss.backward()
        self.assertTrue(torch.isfinite(model.b.grad).all())
        self.assertGreater(float(model.b.grad.norm()),0)
        optimizer=torch.optim.AdamW(model.parameters(),lr=0.001,weight_decay=0.0001)
        optimizer.step()
        self.assertGreater(float((model.b.detach()-initial).norm()),0)
        self.assertTrue(torch.isfinite(model.b).all())


if __name__=="__main__":
    unittest.main()
