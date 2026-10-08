#!/usr/bin/env python3
"""Check that every setting in the form lands in the ComfyUI graph.

Runs without a GPU and without ComfyUI: it builds the same graphs a render
would and asserts each parameter's destination. Use it after changing the
backend, or whenever you want to confirm a control really takes effect.

    app/.venv/bin/python app/verify_params.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
from server import RATIO_SIZES, build_comfy_graph  # noqa: E402

MODELS = {"unet": "qwen_image_2.1_int8_convrot.safetensors",
          "clip": "qwen3vl_8b_int8_convrot.safetensors",
          "vae": "qwen_image_2.1_vae_bf16.safetensors"}
BASE = {"prompt": "a bauhaus poster", "steps": 40, "seed": 42, "ratio": None, "transparent": False}

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    print("== text → image · defaults ==")
    g = build_comfy_graph("t2i", BASE, [], MODELS, "cid")
    dims = (g["latent"]["inputs"]["width"], g["latent"]["inputs"]["height"])
    check(f"no ratio → 1:1 {RATIO_SIZES['1:1']}", dims == RATIO_SIZES["1:1"], str(dims))
    check("steps → KSampler", g["sample"]["inputs"]["steps"] == 40)
    check("seed → KSampler", g["sample"]["inputs"]["seed"] == 42)
    check("prompt → the encode node", g["encode"]["inputs"]["prompt"] == BASE["prompt"])
    check("models → the loaders", g["unet"]["inputs"]["unet_name"] == MODELS["unet"]
          and g["clip"]["inputs"]["clip_name"] == MODELS["clip"]
          and g["vae"]["inputs"]["vae_name"] == MODELS["vae"])
    check("chain encode→sample→decode→save",
          g["sample"]["inputs"]["positive"] == ["encode", 0]
          and g["decode"]["inputs"]["samples"] == ["sample", 0]
          and g["save"]["inputs"]["images"] == ["decode", 0])
    check("no references → no image inputs", not any(k.startswith("images.") for k in g["encode"]["inputs"]))
    check("model runs through the cache node",
          g["sample"]["inputs"]["model"] == ["cache", 0] and g["cache"]["inputs"]["model"] == ["unet", 0])

    print("== text → image · every ratio ==")
    for ratio, size in RATIO_SIZES.items():
        graph = build_comfy_graph("t2i", {**BASE, "ratio": ratio}, [], MODELS, "cid")
        got = (graph["latent"]["inputs"]["width"], graph["latent"]["inputs"]["height"])
        check(f"{ratio} → {size[0]}×{size[1]}", got == size, str(got))

    print("== width / height override the ratio ==")
    g = build_comfy_graph("t2i", {**BASE, "ratio": "16:9", "width": 512, "height": 768}, [], MODELS, "cid")
    check("explicit size wins", (g["latent"]["inputs"]["width"], g["latent"]["inputs"]["height"]) == (512, 768))

    print("== transparent background ==")
    g = build_comfy_graph("t2i", {**BASE, "transparent": True}, [], MODELS, "cid")
    check("the CLI's alpha instruction is appended",
          g["encode"]["inputs"]["prompt"].endswith("The image has alpha channel and the background is transparent."))
    g = build_comfy_graph("t2i", BASE, [], MODELS, "cid")
    check("nothing is appended when off", g["encode"]["inputs"]["prompt"] == BASE["prompt"])

    print("== edit · reference images ==")
    for refs, steps, seed in ((1, 8, 7), (3, 25, 99)):
        names = [f"ref{i}.png" for i in range(refs)]
        g = build_comfy_graph("edit", {**BASE, "steps": steps, "seed": seed}, names, MODELS, "cid")
        check(f"{refs} reference(s) → images.image_1..{refs}",
              all(g["encode"]["inputs"][f"images.image_{i}"] == [f"load{i}", 0] for i in range(1, refs + 1)))
        check(f"{refs} reference(s) → a LoadImage each",
              all(g[f"load{i}"]["class_type"] == "LoadImage" for i in range(1, refs + 1)))
        check(f"{refs} reference(s) → the encode node gets the vae", g["encode"]["inputs"]["vae"] == ["vae", 0])
        check(f"{refs} reference(s) → steps and seed land", g["sample"]["inputs"]["steps"] == steps and g["sample"]["inputs"]["seed"] == seed)
        check(f"{refs} reference(s) → size follows the first image (the node's latent)",
              g["sample"]["inputs"]["latent_image"] == ["encode", 2])
    check("the reference resolution stays within the node's 4096 limit",
          build_comfy_graph("edit", BASE, ["a.png"], MODELS, "cid")["encode"]["inputs"]["resolution"] <= 4096)

    print("== edit · explicit size ==")
    g = build_comfy_graph("edit", {**BASE, "width": 640, "height": 640}, ["ref1.png"], MODELS, "cid")
    check("an explicit size uses its own latent", g["sample"]["inputs"]["latent_image"] == ["latent", 0]
          and g["latent"]["inputs"]["width"] == 640)

    print("== edit · a ratio keeps the ~1 MP edit budget ==")
    for ratio in ("1:1", "3:2", "16:9"):
        g = build_comfy_graph("edit", {**BASE, "ratio": ratio}, ["ref1.png"], MODELS, "cid")
        w, h = g["latent"]["inputs"]["width"], g["latent"]["inputs"]["height"]
        check(f"edit {ratio} → budget-sized canvas (not the {RATIO_SIZES[ratio][0]}×{RATIO_SIZES[ratio][1]} t2i size)",
              (w, h) != RATIO_SIZES[ratio] and w * h <= 1024 * 1024 * 1.1, f"{w}×{h}")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
