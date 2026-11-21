#!/usr/bin/env python3
"""Prepare hero/card/widget/icon crops from user-src photos. Raw files stay in user-src/user-out."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path("/workspace/calendar-lm")
SRC = ROOT / "user-src"
OUT = ROOT / "user-out"
ICONS = ROOT / "icons"
OUT.mkdir(parents=True, exist_ok=True)
ICONS.mkdir(parents=True, exist_ok=True)

# Photos the user said are sideways (lie down). We'll also auto-correct via faces.
SIDEWAYS = {"04", "05", "06", "14"}
# Visible watermarks to inpaint (heuristic regions + text-like contrast).
WATERMARK = {"08", "09", "10", "11"}

FACE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))


def load(path: Path) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def faces(im: Image.Image):
    arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
    h, w = arr.shape
    min_size = max(24, min(w, h) // 16)
    found = FACE.detectMultiScale(arr, scaleFactor=1.08, minNeighbors=5, minSize=(min_size, min_size))
    boxes = [(int(x), int(y), int(x + ww), int(y + hh)) for (x, y, ww, hh) in found]
    return boxes


def rotate90(im: Image.Image, k: int) -> Image.Image:
    # k: number of 90° CCW rotations (PIL rotate is CCW for expand)
    if k % 4 == 0:
        return im
    return im.transpose([Image.ROTATE_90, Image.ROTATE_180, Image.ROTATE_270][(k % 4) - 1])


def upright(im: Image.Image, pid: str) -> tuple[Image.Image, str]:
    """Rotate so faces are upright. Prefer the orientation with faces near the top half / eyes-up."""
    candidates = [0, 1, 2, 3] if pid in SIDEWAYS or im.width > im.height * 1.15 else [0, 2]
    # Always consider all 4 for known sideways shots.
    if pid in SIDEWAYS:
        candidates = [0, 1, 2, 3]
    best = None
    for k in candidates:
        rot = rotate90(im, k)
        boxes = faces(rot)
        score = 0
        if boxes:
            # prefer more faces, and faces in the upper 60%
            score += 100 * len(boxes)
            for x0, y0, x1, y1 in boxes:
                cy = (y0 + y1) / 2
                score += 40 if cy < rot.height * 0.62 else -10
                # face taller than wide slightly is typical upright; sideways faces are wider
                fw, fh = x1 - x0, y1 - y0
                score += 15 if fh >= fw * 0.9 else -8
        else:
            score -= 20
        # For known sideways originals that came in as landscape, prefer portrait if faces exist
        if pid in SIDEWAYS and rot.height >= rot.width:
            score += 8
        if best is None or score > best[0]:
            best = (score, k, rot, boxes)
    k = best[1]
    note = f"rot{k*90} faces={len(best[3])} score={best[0]}"
    return best[2], note


def inpaint_regions(im: Image.Image, pid: str) -> tuple[Image.Image, str]:
    if pid not in WATERMARK:
        return im, "no-wm"
    arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    notes = []

    # Generic: bright or high-contrast text-like areas near edges, plus known locations.
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    # bottom/top/side bands often hold credits
    if pid == "08":
        # 「胡萝卜没了」 typically a lower or corner credit
        notes.append("08-carrot")
        # search pale/white text in lower 30% and corners
        band = gray[int(h * 0.55) :, :]
        # high-luma small structures
        _, th = cv2.threshold(band, 200, 255, cv2.THRESH_BINARY)
        # also dark text on green
        _, th2 = cv2.threshold(band, 70, 255, cv2.THRESH_BINARY_INV)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
        th = cv2.morphologyEx(cv2.bitwise_or(th, th2), cv2.MORPH_CLOSE, k, iterations=2)
        # keep reasonably wide connected components (text lines)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(th, 8)
        local = np.zeros_like(th)
        for i in range(1, n):
            x, y, ww, hh, area = stats[i]
            if ww > 28 and 6 < hh < 80 and area > 80:
                local[y : y + hh, x : x + ww] = 255
        if local.any():
            mask[int(h * 0.55) :, :] = cv2.dilate(local, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 7)))
        else:
            # fallback: lower-right and lower-center bands
            mask[int(h * 0.82) :, int(w * 0.55) :] = 255
            mask[int(h * 0.88) :, :] = 255
    elif pid == "09":
        notes.append("09-sign-left")
        # signature watermark on the left
        mask[:, : max(8, int(w * 0.16))] = 255
        # but don't wipe faces: clear mask over detected faces
    elif pid == "10":
        notes.append("10-Teksefingre")
        # typically a lower credit line
        mask[int(h * 0.88) :, :] = 255
        # also try high-contrast text in bottom 20%
        band = gray[int(h * 0.75) :, :]
        edges = cv2.Canny(band, 60, 160)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k, iterations=2)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(closed, 8)
        local = np.zeros_like(closed)
        for i in range(1, n):
            x, y, ww, hh, area = stats[i]
            if ww > 40 and 5 < hh < 70:
                local[y : y + hh, x : x + ww] = 255
        if local.any():
            mask[int(h * 0.75) :, :] = np.maximum(
                mask[int(h * 0.75) :, :],
                cv2.dilate(local, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 7))),
            )
    elif pid == "11":
        notes.append("11-HEARTRATE")
        mask[int(h * 0.88) :, :] = 255
        band = gray[int(h * 0.70) :, :]
        edges = cv2.Canny(band, 60, 160)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k, iterations=2)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(closed, 8)
        local = np.zeros_like(closed)
        for i in range(1, n):
            x, y, ww, hh, area = stats[i]
            if ww > 40 and 5 < hh < 80:
                local[y : y + hh, x : x + ww] = 255
        if local.any():
            mask[int(h * 0.70) :, :] = np.maximum(
                mask[int(h * 0.70) :, :],
                cv2.dilate(local, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 7))),
            )

    # Never inpaint over faces
    for x0, y0, x1, y1 in faces(im):
        pad = 12
        mask[max(0, y0 - pad) : min(h, y1 + pad), max(0, x0 - pad) : min(w, x1 + pad)] = 0

    if mask.any():
        arr = cv2.inpaint(arr, mask, 5, cv2.INPAINT_TELEA)
        return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)), "+".join(notes) + f" px={int(mask.sum())}"
    return im, "+".join(notes) + " no-mask"


def union_box(boxes, w, h, pad=0.08):
    if not boxes:
        return 0, 0, w, h
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    pw, ph = int((x1 - x0) * pad), int((y1 - y0) * pad)
    return max(0, x0 - pw), max(0, y0 - ph), min(w, x1 + pw), min(h, y1 + ph)


def cover_crop(im: Image.Image, tw: int, th: int, focus=None) -> Image.Image:
    """Crop-to-cover around focus box (x0,y0,x1,y1) or center, then resize."""
    w, h = im.size
    scale = max(tw / w, th / h)
    # If the image already covers, crop a tw/th window
    cw, ch = int(tw / scale), int(th / scale)
    if focus:
        fx0, fy0, fx1, fy1 = focus
        cx, cy = (fx0 + fx1) / 2, (fy0 + fy1) / 2
        # try to include the whole focus
        if (fx1 - fx0) > cw or (fy1 - fy0) > ch:
            # need a larger window: we'll letterbox with blur later if needed
            pass
        x0 = int(cx - cw / 2)
        y0 = int(cy - ch / 2)
        # shift to include focus if possible
        if fx0 < x0:
            x0 = fx0
        if fy0 < y0:
            y0 = fy0
        if fx1 > x0 + cw:
            x0 = fx1 - cw
        if fy1 > y0 + ch:
            y0 = fy1 - ch
    else:
        x0, y0 = (w - cw) // 2, int((h - ch) * 0.28)
    x0 = max(0, min(x0, w - cw))
    y0 = max(0, min(y0, h - ch))
    crop = im.crop((x0, y0, x0 + cw, y0 + ch))
    return crop.resize((tw, th), Image.Resampling.LANCZOS)


def blur_fill(im: Image.Image, tw: int, th: int, focus=None) -> Image.Image:
    """Fit the subject (or whole image) inside tw/th, fill gaps with blurred cover."""
    w, h = im.size
    if focus:
        fx0, fy0, fx1, fy1 = focus
        # include a generous margin around both people
        mw, mh = int((fx1 - fx0) * 0.25), int((fy1 - fy0) * 0.35)
        sx0, sy0 = max(0, fx0 - mw), max(0, fy0 - mh)
        sx1, sy1 = min(w, fx1 + mw), min(h, fy1 + int(mh * 0.7))
        subject = im.crop((sx0, sy0, sx1, sy1))
    else:
        subject = im
    sw, sh = subject.size
    scale = min(tw / sw, th / sh)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    fitted = subject.resize((nw, nh), Image.Resampling.LANCZOS)
    bg = im.resize((tw, th), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(36))
    # slightly darken/desaturate edges so subject pops
    canvas = Image.new("RGB", (tw, th))
    canvas.paste(bg, (0, 0))
    canvas.paste(fitted, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


def contains_focus(crop_box, focus, ratio=0.96):
    if not focus:
        return True
    x0, y0, x1, y1 = crop_box
    fx0, fy0, fx1, fy1 = focus
    iw = max(0, min(x1, fx1) - max(x0, fx0))
    ih = max(0, min(y1, fy1) - max(y0, fy0))
    area = max(1, (fx1 - fx0) * (fy1 - fy0))
    return (iw * ih) / area >= ratio


def smart_cover(im: Image.Image, tw: int, th: int, focus=None) -> Image.Image:
    w, h = im.size
    scale = max(tw / w, th / h)
    cw, ch = int(round(tw / scale)), int(round(th / scale))
    if focus and ((focus[2] - focus[0]) > cw or (focus[3] - focus[1]) > ch):
        return blur_fill(im, tw, th, focus)
    return cover_crop(im, tw, th, focus)


def save_jpeg(im: Image.Image, path: Path, quality=90):
    im = im.convert("RGB")
    im.save(path, "JPEG", quality=quality, optimize=True, subsampling=0)


def make_icon(im: Image.Image, focus=None) -> dict[str, Image.Image]:
    # square face crop, slightly above center of faces
    w, h = im.size
    if focus:
        fx0, fy0, fx1, fy1 = focus
        cx = (fx0 + fx1) / 2
        cy = (fy0 + fy1) / 2 - (fy1 - fy0) * 0.08
        side = int(max(fx1 - fx0, fy1 - fy0) * 1.55)
        side = min(side, w, h)
        x0 = int(cx - side / 2)
        y0 = int(cy - side / 2)
        x0 = max(0, min(x0, w - side))
        y0 = max(0, min(y0, h - side))
        sq = im.crop((x0, y0, x0 + side, y0 + side))
    else:
        side = min(w, h)
        sq = im.crop(((w - side) // 2, (h - side) // 4, (w - side) // 2 + side, (h - side) // 4 + side))
    out = {}
    for name, size, extra in [
        ("apple-touch-icon.png", 180, None),
        ("icon-192.png", 192, None),
        ("icon-512.png", 512, None),
        ("icon-512-maskable.png", 512, 0.08),
        ("favicon-32.png", 32, None),
    ]:
        canvas_size = size
        if extra:
            # safe zone: scale down a bit and pad
            inner = int(size * (1 - 2 * extra))
            inner_im = sq.resize((inner, inner), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (size, size), (31, 95, 122))
            canvas.paste(inner_im, ((size - inner) // 2, (size - inner) // 2))
            out[name] = canvas
        else:
            out[name] = sq.resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)
    return out


def main():
    report = []
    cleaned = {}
    for i in range(1, 15):
        pid = f"{i:02d}"
        src = SRC / f"{pid}.jpg"
        if not src.exists():
            report.append({"id": pid, "error": "missing"})
            continue
        im = load(src)
        im, rot_note = upright(im, pid)
        im, wm_note = inpaint_regions(im, pid)
        clean_path = OUT / f"clean-{pid}.jpg"
        save_jpeg(im, clean_path, quality=93)
        boxes = faces(im)
        focus = union_box(boxes, *im.size, pad=0.18) if boxes else None
        hero = smart_cover(im, 1280, 720, focus)
        card = smart_cover(im, 1600, 1200, focus)
        widget = smart_cover(im, 1170, 2532, focus)
        save_jpeg(hero, OUT / f"hero-{pid}.jpg", 90)
        save_jpeg(card, OUT / f"card-{pid}.jpg", 90)
        save_jpeg(widget, OUT / f"widget-{pid}.jpg", 88)
        for name, img in [
            (f"hero-{pid}.jpg", hero),
            (f"card-{pid}.jpg", card),
            (f"widget-{pid}.jpg", widget),
        ]:
            img.save  # noqa
        # copy into icons/
        save_jpeg(hero, ICONS / f"hero-{pid}.jpg", 90)
        save_jpeg(card, ICONS / f"card-{pid}.jpg", 90)
        save_jpeg(widget, ICONS / f"widget-{pid}.jpg", 88)
        cleaned[pid] = {
            "src_size": list(Image.open(src).size),
            "clean_size": list(im.size),
            "faces": len(boxes),
            "rot": rot_note,
            "wm": wm_note,
            "focus": focus,
        }
        report.append({"id": pid, **cleaned[pid]})
        print(f"{pid}: {rot_note} | {wm_note} | faces={len(boxes)} clean={im.size}")

    (OUT / "process-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("wrote", OUT / "process-report.json")


if __name__ == "__main__":
    main()
