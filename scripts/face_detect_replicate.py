#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, io, math, json, tempfile, pathlib, requests
from typing import Tuple, Optional, Dict, Any
from PIL import Image
import numpy as np
import replicate
from dotenv import load_dotenv
load_dotenv()
TARGET = 1024

def _expand_box(x0,y0,x1,y1,W,H, margin=(0.12,0.35)):
    # margem lateral 12%, margem inferior 35% (mais queixo)
    w, h = x1-x0, y1-y0
    dx, dy_top, dy_bot = int(w*margin[0]), int(h*margin[0]), int(h*margin[1])
    x0 = max(0, x0 - dx)
    x1 = min(W, x1 + dx)
    y0 = max(0, y0 - dy_top)
    y1 = min(H, y1 + dy_bot)
    return x0, y0, x1, y1

def _to_square(x0,y0,x1,y1,W,H):
    # transforma em quadrado centralizado dentro do frame
    w, h = x1-x0, y1-y0
    side = max(w, h)
    cx, cy = x0 + w//2, y0 + h//2
    sx0, sy0 = max(0, cx - side//2), max(0, cy - side//2)
    sx1, sy1 = min(W, sx0 + side), min(H, sy0 + side)
    # re-ajusta se cortou borda
    if sx1 - sx0 < side:
        sx0 = max(0, sx1 - side)
    if sy1 - sy0 < side:
        sy0 = max(0, sy1 - side)
    return sx0, sy0, sx1, sy1

def _bytes_of_image(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def _run_replicate_model(slug: str, file_path: str, extra: Optional[Dict[str, Any]] = None):
    client = replicate.Client()
    input_payload = {"image": open(file_path, "rb")}
    if extra: input_payload.update(extra)

    if ":" in slug:
        version = slug.split(":", 1)[1]
        pred = client.predictions.create(version=version, input=input_payload)
    else:
        pred = client.predictions.create(model=slug, input=input_payload)

    import time
    while pred.status in {"starting","processing"}:
        time.sleep(1.5)
        pred = client.predictions.get(pred.id)
    if pred.error:
        raise RuntimeError(pred.error + (f"\nlogs:\n{pred.logs}" if pred.logs else ""))
    return pred.output


def detect_face_bbox(img_path: str) -> Optional[Tuple[int,int,int,int]]:
    """Tenta detector principal, depois fallback. Retorna (x0,y0,x1,y1)."""
    b = _bytes_of_image(img_path)
    main = os.getenv("REPLICATE_FACE_DETECTOR","").strip()
    fb   = os.getenv("REPLICATE_FACE_DETECTOR_FALLBACK","").strip()

    # 1) Anime Face Detector (YOLO) → geralmente retorna lista de bboxes [x,y,w,h] ou [x0,y0,x1,y1]
    if main:
        try:
            out = _run_replicate_model(main, img_path)
            # tolera múltiplos formatos
            # exemplos esperados: [{"bbox":[x,y,w,h], "conf":0.9}, ...]  ou [[x0,y0,x1,y1], ...]
            if isinstance(out, dict) and "boxes" in out:
                boxes = out["boxes"]
            else:
                boxes = out
            if not boxes: raise RuntimeError("sem caixas")
            box = boxes[0]
            if isinstance(box, dict) and "bbox" in box:
                x, y, w, h = [int(v) for v in box["bbox"]]
                return x, y, x+w, y+h
            # lista direta
            if len(box) == 4:
                x0, y0, x1, y1 = [int(v) for v in box]
                # se veio em (x,y,w,h)
                if x1 < img_path.__len__():  # heurística boba, mantém mesmo
                    pass
                return x0, y0, x1, y1
        except Exception as e:
            print("[detect] main falhou:", e)

    # 2) Fallback: mediapipe-face (pode devolver landmarks; derivamos bbox)
    if fb:
        try:
            out = _run_replicate_model(fb, b)
            # tolerar formatos: {"bbox":[x0,y0,x1,y1]} ou {"landmarks":[[x,y],...]}
            if isinstance(out, dict):
                if "bbox" in out and len(out["bbox"])==4:
                    x0,y0,x1,y1 = [int(v) for v in out["bbox"]]
                    return x0,y0,x1,y1
                if "landmarks" in out and out["landmarks"]:
                    xs = [pt[0] for pt in out["landmarks"]]
                    ys = [pt[1] for pt in out["landmarks"]]
                    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
        except Exception as e:
            print("[detect] fallback falhou:", e)

    return None

def crop_with_detector(img_path: str, out_png: str) -> str:
    im = Image.open(img_path).convert("RGBA")
    W,H = im.size
    box = detect_face_bbox(img_path)
    if box is None:
        # fallback: centro 80% + boca
        s = int(min(W,H)*0.8); cx,cy=W//2,int(H*0.55)
        x0,y0 = max(0,cx-s//2), max(0,cy-s//2)
        x1,y1 = min(W,x0+s),   min(H,y0+s)
    else:
        x0,y0,x1,y1 = box
        x0,y0,x1,y1 = _expand_box(x0,y0,x1,y1,W,H, margin=(0.14,0.40))
        x0,y0,x1,y1 = _to_square(x0,y0,x1,y1,W,H)

    crop = im.crop((x0,y0,x1,y1)).resize((TARGET,TARGET), Image.LANCZOS)
    pathlib.Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_png, "PNG")
    return out_png
