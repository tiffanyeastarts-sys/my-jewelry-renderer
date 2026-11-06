"""管线自测：不联网、不依赖真实 API Key。

    python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jrenderer.providers.base import BaseProvider, ProviderError, ProviderResult  # noqa: E402
from jrenderer.providers.ark import _image_payload  # noqa: E402
from jrenderer.runner import run  # noqa: E402
from jrenderer.spec import SpecError, load_spec  # noqa: E402

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


class FlakyProvider(BaseProvider):
    """前两次抛可重试错误，第三次成功——用来验证退避重试真的生效。"""

    name = "flaky"
    model = "test"

    def __init__(self, fail_times=2):
        self.fail_times = fail_times
        self.calls = 0

    def generate(self, job, reference_image=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError("模拟 429", retryable=True, status=429)
        return ProviderResult(data=PNG_1x1 * 40, provider=self.name, model=self.model)


class DeadProvider(BaseProvider):
    """不可恢复错误：不应浪费重试次数。"""

    name = "dead"
    model = "test"

    def generate(self, job, reference_image=None):
        raise ProviderError("模拟 400", retryable=False, status=400)


class SpecTests(unittest.TestCase):
    def test_matrix_size_and_naming(self):
        spec = load_spec("configs/quickstart.yaml", out_dir=tempfile.mkdtemp())
        self.assertEqual(len(spec.jobs), 2)
        names = [j.out_path.name for j in spec.jobs]
        self.assertEqual(len(names), len(set(names)), "矩阵内不能出现重名任务")
        self.assertIn("__yellow_gold__round_brilliant__front__v1.png", names[0])

    def test_unknown_gem_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "bad.yaml"
            cfg.write_text(
                "piece:\n  name: t\nmetals: [yellow_gold]\ngems: [diamond_but_wrong]\nangles: [front]\n",
                encoding="utf-8",
            )
            with self.assertRaises(SpecError):
                # 注意：词表里没有 diamond_but_wrong，必须在展开前就报错
                load_spec(cfg)

    def test_missing_required_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "bad.yaml"
            cfg.write_text("piece:\n  name: t\nangles: [front]\n", encoding="utf-8")
            with self.assertRaises(SpecError):
                load_spec(cfg)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.spec = load_spec("configs/quickstart.yaml", out_dir=self.out, variants=1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_retry_until_success(self):
        provider = FlakyProvider(fail_times=2)
        stats = run(self.spec, provider, workers=1, retries=3, backoff=0.01, quiet=True)
        self.assertEqual(stats["ok"], 2)
        for job in self.spec.jobs:
            self.assertTrue(job.out_path.exists())
            self.assertGreater(job.out_path.stat().st_size, 1024)
        rows = (self.spec.out_dir / "manifest.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 3)  # 表头 + 2 条任务

    def test_unrecoverable_error_does_not_burn_retries(self):
        provider = DeadProvider()
        stats = run(self.spec, provider, workers=1, retries=5, backoff=0.01, quiet=True)
        self.assertEqual(stats["failed"], 2)
        self.assertFalse(self.spec.jobs[0].out_path.exists())

    def test_resume_skips_existing_and_keeps_ok_status(self):
        provider = FlakyProvider(fail_times=0)
        run(self.spec, provider, workers=2, quiet=True)
        stats = run(self.spec, provider, workers=2, quiet=True)
        self.assertEqual(stats["skipped"], 2)
        manifest = (self.spec.out_dir / "manifest.csv").read_text(encoding="utf-8")
        self.assertNotIn(",failed,", manifest)
        self.assertEqual(manifest.count(",ok,"), 2, "续跑不能把已成功记录的 status 改成 skipped")


class PayloadTests(unittest.TestCase):
    def test_http_reference_passes_through(self):
        self.assertEqual(_image_payload("https://example.com/a.png"), "https://example.com/a.png")

    def test_local_reference_becomes_data_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ref.png"
            path.write_bytes(PNG_1x1)
            url = _image_payload(str(path))
            self.assertTrue(url.startswith("data:image/png;base64,"))

    def test_missing_reference_raises(self):
        with self.assertRaises(ProviderError):
            _image_payload("/no/such/file.png")


if __name__ == "__main__":
    unittest.main()
