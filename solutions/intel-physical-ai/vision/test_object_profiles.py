import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import object_pipeline as pipeline
import prepare_objects as prepare

class PinnedProfiles(unittest.TestCase):
    def test_portable_spec_reconstructs_exact_input_bytes(self):
        path=Path(__file__).with_name('object_dataset.json')
        self.assertEqual(prepare.digest(path.read_bytes()),prepare.SPEC_SHA)
        spec=json.loads(path.read_bytes())
        for name,value in spec.items():self.assertEqual(prepare.digest(prepare.encoded(value)),pipeline.PINS[name])
    def test_both_profiles_refuse_unpinned_model_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'weights.safetensors';p.write_bytes(b'not pinned model weights')
            for profile in pipeline.BACKBONES:
                with self.subTest(profile=profile),self.assertRaisesRegex(ValueError,'Backbone hash'):
                    pipeline.create_model(d,profile,str(p))
    def test_unknown_profile_not_implicitly_downloaded(self):
        with self.assertRaises(KeyError):pipeline.create_model('/nonexistent','unapproved-provider')
if __name__=='__main__':unittest.main()
