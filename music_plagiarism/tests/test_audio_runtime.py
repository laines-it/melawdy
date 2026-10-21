"""Check the actual model checkpoints, not just presence of their files."""
import sys
import unittest

from core import VENDOR, choose_device, diagnostics


class AudioRuntimeTests(unittest.TestCase):
    def test_full_runtime_and_checkpoint_architectures(self):
        self.assertTrue(diagnostics()["ready"])
        sys.path.insert(0, str(VENDOR))
        import torch
        from ml_models.DilatedTransformer import Demixed_DilatedTransformerModel
        from ml_models.AST.net import EffNetb0
        from madmom.features.beats import DBNBeatTrackingProcessor
        from madmom.features.downbeats import DBNDownBeatTrackingProcessor

        torch.set_num_threads(1)
        beat = Demixed_DilatedTransformerModel(attn_len=5, instr=5, ntoken=2,
                                              dmodel=256, nhead=8, d_hid=1024, nlayers=9, norm_first=True)
        state = torch.load(VENDOR / "ml_models/Beat-Transformer/checkpoint/fold_4_trf_param.pt",
                           map_location="cpu", weights_only=True)
        beat.load_state_dict(state["state_dict"], strict=True)
        del state, beat
        singing = EffNetb0().eval()
        state = torch.load(VENDOR / "ml_models/AST/models/1005_e_4", map_location="cpu", weights_only=True)
        loaded = singing.load_state_dict(state, strict=False)
        self.assertEqual(loaded.missing_keys, [])
        # The published checkpoint retains unused heads from a legacy architecture.
        legacy = {f"{layer}.{parameter}" for layer in ("conv1", "conv2", "conv3", "fc1", "fc2", "fc3")
                  for parameter in ("weight", "bias")}
        self.assertEqual(set(loaded.unexpected_keys), legacy)
        with torch.inference_mode():
            predictions = singing(torch.zeros(1, 1, 11, 168))
        self.assertEqual(len(predictions), 4)
        self.assertTrue(all(torch.isfinite(p).all() for p in predictions))
        self.assertIsNotNone(DBNBeatTrackingProcessor(fps=44100/1024))
        self.assertIsNotNone(DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=44100/1024))
        self.assertEqual(choose_device("cpu"), "cpu")


if __name__ == "__main__":
    unittest.main()
