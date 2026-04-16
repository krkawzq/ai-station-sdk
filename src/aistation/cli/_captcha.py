"""Render a captcha PNG as ASCII/unicode art for in-terminal display.

Strategy (best to worst quality):
1. External ``chafa`` / ``jp2a`` if on PATH — best fidelity
2. Pillow → half-block unicode (▀) with basic grayscale — good
3. Pillow → plain ASCII ramp — decent
4. Nothing available → caller prints the file path instead
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path


# Character ramp from light to dark (for dark-on-light captchas the ramp is
# inverted at render time so the text prints as filled glyphs).
_ASCII_RAMP = " .:-=+*#%@"

# Upper bound on the vertical space we ask of the terminal, regardless of how
# wide it is. Captcha images are only ~40 px tall; more than this and the art
# gets cartoonishly large without helping readability.
_MAX_HEIGHT_ROWS = 20


def terminal_width(fallback: int = 100) -> int:
    """Return the current terminal's column count, or ``fallback`` if unknown."""
    try:
        return shutil.get_terminal_size(fallback=(fallback, 24)).columns
    except OSError:
        return fallback


def save_png(base64_png: str, *, name: str = "aistation-captcha") -> Path:
    """Decode a base64 PNG and save to a temp file. Returns the path."""
    data = base64.b64decode(base64_png)
    tmp = Path(tempfile.gettempdir()) / f"{name}.png"
    tmp.write_bytes(data)
    return tmp


def render(path: Path, *, max_width: int | None = None) -> str | None:
    """Render the PNG at ``path`` as an ANSI/ASCII string suitable for ``print()``.

    When ``max_width`` is ``None`` (default) the renderer uses the current
    terminal width so the captcha fills the available space — most terminals
    are ≥ 100 columns and captcha text stays comfortably legible.
    Returns ``None`` when no renderer is available; caller should fall back to
    showing the file path.
    """
    if max_width is None:
        max_width = max(60, terminal_width() - 2)
    # Try external tools first — they usually produce beautiful output.
    for cmd in (_try_chafa, _try_jp2a):
        out = cmd(path, max_width)
        if out:
            return out
    # Fall back to PIL-based renderers.
    out = _try_pil_halfblock(path, max_width)
    if out:
        return out
    return _try_pil_ascii(path, max_width)


# ---------- renderers ----------

def _try_chafa(path: Path, max_width: int) -> str | None:
    if not shutil.which("chafa"):
        return None
    try:
        r = subprocess.run(
            ["chafa", "--size", f"{max_width}x", "--colors=full", str(path)],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return None


def _try_jp2a(path: Path, max_width: int) -> str | None:
    if not shutil.which("jp2a"):
        return None
    try:
        # jp2a needs JPEG; convert via PIL if possible
        from PIL import Image
        with tempfile.NamedTemporaryFile("wb", suffix=".jpg", delete=False) as fh:
            jpg = Path(fh.name)
        try:
            Image.open(path).convert("RGB").save(jpg, format="JPEG")
            r = subprocess.run(
                ["jp2a", f"--width={max_width}", "--invert", str(jpg)],
                capture_output=True, text=True, timeout=5, check=True,
            )
            return r.stdout
        finally:
            jpg.unlink(missing_ok=True)
    except (ImportError, subprocess.SubprocessError, OSError):
        return None


def _fit_dimensions(src_w: int, src_h: int, max_width: int) -> tuple[int, int]:
    """Scale ``src`` to fit ``max_width``, then clamp height to ``_MAX_HEIGHT_ROWS * 2``.

    Output is always even-height so each half-block cell has a clean pair of
    pixels.
    """
    target_w = min(max_width, max(20, src_w * max_width // max(src_w, 1)))
    target_w = min(target_w, max_width)
    target_h = max(2, int(src_h * target_w / max(src_w, 1)))
    # Cap total rows (= target_h / 2) so big terminals don't draw a wall of art.
    max_pixels_tall = _MAX_HEIGHT_ROWS * 2
    if target_h > max_pixels_tall:
        # Shrink width proportionally so aspect stays correct.
        scale = max_pixels_tall / target_h
        target_w = max(20, int(target_w * scale))
        target_h = max_pixels_tall
    if target_h % 2:
        target_h += 1
    return target_w, target_h


def _try_pil_halfblock(path: Path, max_width: int) -> str | None:
    """Render using Unicode upper-half blocks (▀) for 2x vertical resolution.

    Uses 24-bit truecolor ANSI. Falls back to nothing if Pillow is missing.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None

    target_w, target_h = _fit_dimensions(img.width, img.height, max_width)
    img = img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

    ESC = "\x1b["
    lines: list[str] = []
    # getpixel is the reliable typed accessor (.load() returns PixelAccess which
    # Pyright doesn't narrow well); profiling shows this is fast enough for
    # captcha-sized images.
    for y in range(0, target_h, 2):
        row_parts: list[str] = []
        for x in range(target_w):
            top = img.getpixel((x, y))
            bot = img.getpixel((x, y + 1))
            fr, fg, fb = _rgb_triplet(top)
            br, bg, bb = _rgb_triplet(bot)
            row_parts.append(f"{ESC}38;2;{fr};{fg};{fb}m{ESC}48;2;{br};{bg};{bb}m▀")
        row_parts.append(f"{ESC}0m")
        lines.append("".join(row_parts))
    return "\n".join(lines)


def _rgb_triplet(pixel: object) -> tuple[int, int, int]:
    """Coerce a PIL pixel value to (r, g, b)."""
    if isinstance(pixel, tuple):
        r, g, b = (pixel + (0, 0, 0))[:3]
        return int(r), int(g), int(b)
    v = int(pixel) if isinstance(pixel, (int, float)) else 0
    return v, v, v


def _try_pil_ascii(path: Path, max_width: int) -> str | None:
    """Render as plain-ASCII ramp (last resort, no color)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(path).convert("L")
    except Exception:  # noqa: BLE001
        return None

    # Character cells are ~2x taller than wide, so use half the rows
    target_w, target_h_pixels = _fit_dimensions(img.width, img.height, max_width)
    target_h = max(4, target_h_pixels // 2)
    img = img.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

    ramp = _ASCII_RAMP
    lines = []
    for y in range(target_h):
        row = []
        for x in range(target_w):
            pixel = img.getpixel((x, y))
            brightness = int(pixel) if isinstance(pixel, (int, float)) else 0
            # captchas are usually dark glyph on light background — invert so
            # dark pixels map to dense characters at the end of the ramp.
            idx = min(len(ramp) - 1, int((255 - brightness) * len(ramp) / 256))
            row.append(ramp[idx])
        lines.append("".join(row))
    return "\n".join(lines)
