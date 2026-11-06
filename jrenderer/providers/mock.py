"""Mock 后端：不调任何 API，用 Pillow 画程序化占位图。

用途：在没有 API Key / 离线时验证整条管线（任务矩阵、并发、断点续跑、manifest 报告），
产物是"示意图"而非真实渲染，文件名里带 __mock 便于区分。
"""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from ..vocab import ANGLES, GEMS, METALS
from .base import BaseProvider, ProviderResult

SS = 2  # 超采样倍数，画完再缩回目标尺寸，边缘更平滑


def _parse_size(size: str) -> tuple[int, int]:
    if "x" in size:
        w, h = size.lower().split("x")[:2]
        return int(w), int(h)
    return 2048, 2048


class MockProvider(BaseProvider):
    name = "mock"
    model = "pillow-procedural"

    def generate(self, job, reference_image: str | None = None) -> ProviderResult:
        w, h = _parse_size(job.size)
        img = self._draw(job, w * SS, h * SS).convert("RGB").resize((w, h), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return ProviderResult(data=buf.getvalue(), provider=self.name, model=self.model)

    # --- 绘制 -------------------------------------------------------------
    def _draw(self, job, w: int, h: int) -> Image.Image:
        metal = METALS[job.metal_key]["rgb"]
        gem = GEMS[job.gem_key]["rgb"]
        img = self._background(w, h)
        d = ImageDraw.Draw(img, "RGBA")
        layout = ANGLES[job.angle_key]["layout"]
        cx, cy = w // 2, int(h * 0.55)
        band_w = int(min(w, h) * 0.09)

        if layout == "front":
            rx, ry = int(w * 0.28), int(h * 0.30)
            self._band(d, cx, cy, rx, ry, band_w, metal)
            self._gem(d, cx, cy - ry, int(h * 0.13), gem, "round", job.gem_key)
        elif layout == "top45":
            rx, ry = int(w * 0.30), int(h * 0.17)
            self._band(d, cx, cy, rx, ry, band_w, metal)
            self._gem(d, cx, cy - ry, int(h * 0.15), gem, "oval", job.gem_key)
        elif layout == "side":
            rx, ry = int(w * 0.09), int(h * 0.28)
            self._band(d, cx, cy, rx, ry, band_w, metal)
            self._gem(d, cx, cy - ry - band_w // 2, int(h * 0.10), gem, "pear", job.gem_key)
        else:  # macro
            self._band(d, cx, int(h * 1.18), int(w * 0.36), int(h * 0.30), band_w * 2, metal)
            self._gem(d, cx, int(h * 0.47), int(h * 0.21), gem, "round", job.gem_key)

        return img

    def _background(self, w: int, h: int) -> Image.Image:
        img = Image.new("RGB", (w, h), (246, 246, 247))
        d = ImageDraw.Draw(img)
        top, bottom = (250, 250, 251), (214, 215, 218)
        for y in range(h):
            t = y / max(h - 1, 1)
            d.line(
                [(0, y), (w, y)],
                fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)),
            )
        # 底部柔和接触阴影
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse(
            [int(w * 0.18), int(h * 0.84), int(w * 0.82), int(h * 0.94)],
            fill=(0, 0, 0, 60),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(int(h * 0.03)))
        img = Image.alpha_composite(img.convert("RGBA"), shadow)
        return img

    def _band(self, d, cx, cy, rx, ry, width, metal):
        outer = [cx - rx, cy - ry, cx + rx, cy + ry]
        inner = [cx - rx + width, cy - ry + width, cx + rx - width, cy + ry - width]
        d.ellipse(outer, fill=metal + (255,))
        d.ellipse(inner, fill=(238, 238, 238, 255))
        # 高光：左上偏亮、右下偏暗的两段弧
        light = tuple(min(255, c + 38) for c in metal)
        dark = tuple(max(0, c - 55) for c in metal)
        d.arc([cx - rx + 4, cy - ry + 4, cx + rx - 4, cy + ry - 4], 200, 320, fill=light + (220,), width=max(2, width // 3))
        d.arc([cx - rx + 4, cy - ry + 4, cx + rx - 4, cy + ry - 4], 20, 140, fill=dark + (200,), width=max(2, width // 4))

    def _gem(self, d, cx, cy, r, gem, shape, gem_key=""):
        if shape == "oval":
            box = [cx - r, cy - int(r * 0.7), cx + r, cy + int(r * 0.7)]
            d.ellipse(box, fill=gem + (255,))
        elif shape == "pear":
            d.polygon(
                [(cx, cy - r), (cx + int(r * 0.7), cy + int(r * 0.5)), (cx, cy + r), (cx - int(r * 0.7), cy + int(r * 0.5))],
                fill=gem + (255,),
            )
        else:
            box = [cx - r, cy - r, cx + r, cy + r]
            d.ellipse(box, fill=gem + (255,))
        # 刻面：内接多边形 + 台面
        core = tuple(min(255, c + 45) for c in gem)
        edge = tuple(max(0, c - 50) for c in gem)
        poly = [
            (cx, cy - r),
            (cx + int(r * 0.86), cy - int(r * 0.5)),
            (cx + int(r * 0.86), cy + int(r * 0.5)),
            (cx, cy + r),
            (cx - int(r * 0.86), cy + int(r * 0.5)),
            (cx - int(r * 0.86), cy - int(r * 0.5)),
        ]
        d.polygon(poly, outline=edge + (255,))
        if gem_key == "emerald_cut":
            d.rectangle([cx - int(r * 0.55), cy - int(r * 0.62), cx + int(r * 0.55), cy + int(r * 0.62)],
                        fill=core + (205,))
        elif gem_key in ("oval_sapphire", "ruby", "aquamarine"):
            d.ellipse([cx - int(r * 0.5), cy - int(r * 0.55), cx + int(r * 0.5), cy + int(r * 0.55)],
                      fill=core + (200,))
        else:
            d.polygon(
                [(cx, cy - int(r * 0.75)), (cx + int(r * 0.5), cy), (cx, cy + int(r * 0.75)), (cx - int(r * 0.5), cy)],
                fill=core + (200,),
            )
        d.ellipse([cx - int(r * 0.28), cy - int(r * 0.72), cx + int(r * 0.28), cy - int(r * 0.30)], fill=(255, 255, 255, 170))
