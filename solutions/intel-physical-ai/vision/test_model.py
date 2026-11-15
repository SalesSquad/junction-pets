"""CPU random-weight/synthetic-pixel plumbing ONLY. Never quality evaluation."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import torch
from safetensors.torch import save_file
from anomalib.models.image.padim.torch_model import PadimModel
import pipeline as p


class ModelPlumbing(unittest.TestCase):
    def test_fit_safe_reload_infer_and_openvino(self):
        torch.set_num_threads(2);torch.manual_seed(330)
        model=PadimModel(n_features=50,backbone='resnet18',pre_trained=False).cpu()
        model.train()
        for _ in range(3):
            with torch.no_grad():model(torch.randn(1,3,128,128))
        model.fit();model.eval()
        x=torch.randn(1,3,128,128)
        score,amap=p.infer(model,x)
        self.assertTrue(np.isfinite(score));self.assertEqual(amap.shape,(1,1,128,128))
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            state={k:v.contiguous() for k,v in model.state_dict().items()}
            save_file(state,str(out/'model.safetensors'))
            p.write_json(out/'model-tensors.json',p.tensor_hashes(state))
            p.write_json(out/'config.json',dict(config=p.CONFIG,preprocess=p.PREPROCESS))
            p.write_json(out/'thresholds.json',dict(values=dict(good=1.,binary=2.,defect=3.)))
            p.write_json(out/'frozen.json',dict(model=p.digest((out/'model.safetensors').read_bytes()),
                          thresholds=p.digest((out/'thresholds.json').read_bytes())))
            p.seal(out)
            restored,_=p.load_fitted(out)
            score2,amap2=p.infer(restored,x)
            # CPU kernels can change rounding with reloaded tensor strides.
            # Use the experiment's predeclared numerical tolerances.
            np.testing.assert_allclose(score,score2,atol=.001,rtol=.001)
            np.testing.assert_allclose(amap,amap2,atol=.001,rtol=.001)
    def test_openvino_cpu_qualification(self):
        # Separate environment gate: CPU compile refusal must remain a failure.
        torch.set_num_threads(2);torch.manual_seed(330)
        restored=PadimModel(n_features=50,backbone='resnet18',pre_trained=False).cpu()
        restored.train()
        for _ in range(3):
            with torch.no_grad():restored(torch.randn(1,3,128,128))
        restored.fit();restored.eval()
        x=torch.randn(1,3,128,128);score,amap=p.infer(restored,x)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            # Real conversion/readback path; synthetic tensors, no quality claim.
            from unittest.mock import patch
            row=dict(image='SYNTHETIC_PLUMBING_ONLY',partition='heldout')
            with patch.object(p,'image_tensor',return_value=x):
                parity=p.export_parity(restored,dict(samples=[row]),out,out,
                        {row['image']:(score,amap)},dict(good=1.,binary=2.,defect=3.))
            self.assertEqual(parity['status'],'pass',parity)
            self.assertEqual(parity['count'],1)


if __name__=='__main__':unittest.main()
