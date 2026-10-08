#!/usr/bin/env python3
"""qwen image studio — standalone edition.

A local web studio for Qwen-Image-2.1, derived from the helmstudio edition
(janishar/qwen-image-2.1-studio, MIT). Sessions with their settings and
reference images, reference images and takes, the gallery, the render queue
and its SSE progress — everything kept locally, in a data directory (default
``~/Qwen Image Studio``, with ``Input/`` for imported references and
``Output/`` for finished takes); nothing is sent anywhere.
Renders go through a local ComfyUI: the path is set under Paths in the page,
and the graphs mirror ComfyUI's own Qwen-Image-2.1 templates.

Standard library plus Pillow for image checks and thumbnails; Pillow is
optional, without it uploads are sniffed by magic bytes and thumbnails fall
back to the originals.

Usage:
    python web/server.py [--port N] [--data-dir DIR] [--comfyui DIR_OR_URL]
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import ipaddress
import json
import math
import mimetypes
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO, ClassVar
from urllib.parse import parse_qs, unquote, urlparse

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

#: The form's ratio choices.
RATIOS = {"1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"}
#: …and the size each renders at, about 4 MP like the original project.
RATIO_SIZES = {
    "1:1": (2048, 2048), "4:3": (2400, 1792), "3:4": (1792, 2400), "3:2": (2528, 1696),
    "2:3": (1696, 2528), "16:9": (2752, 1536), "9:16": (1536, 2752),
}

MAX_INPUTS = 10
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

PATHS_KEYS = ("comfyui",)

#: A reference image named in the prompt: ``@`` then its name, as the page inserts it.
MENTION_RE = re.compile(r"@([A-Za-z0-9._-]*[A-Za-z0-9_-])")
def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_name(text: str, default: str = "untitled") -> str:
    return SAFE_NAME.sub("-", text.strip()).strip(".-")[:80] or default


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except OSError:
        return None


def make_thumb(source: Path, target: Path, width: int = 320) -> bool:
    """A small PNG preview; keeps alpha. False when Pillow is missing."""
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(source) as img:
            img.load()
            ratio = width / max(1, img.width)
            thumb = img.resize((width, max(1, round(img.height * ratio))), Image.LANCZOS)
            thumb.save(target, "PNG")
        return True
    except OSError:
        return False


def sniff_image(path: Path) -> str | None:
    """A file's image extension by magic bytes, or None."""
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


# ---------------------------------------------------------------------------
# request guard: no auth, so refuse DNS rebinding and cross-site writes
# ---------------------------------------------------------------------------


def host_only(hostport: str) -> str:
    if hostport.startswith("["):
        return hostport[1:].split("]", 1)[0]
    return hostport.rsplit(":", 1)[0] if hostport.count(":") == 1 else hostport


def host_allowed(hostport: str, allowed: set[str]) -> bool:
    host = host_only(hostport).lower()
    if not host:
        return False
    if host == "localhost" or host in allowed:
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def request_guard(method: str, path: str, headers: Any, allowed: set[str]) -> tuple[int, str] | None:
    host = headers.get("Host", "")
    if not host_allowed(host, allowed):
        return 403, f"unrecognized Host header; start with --allow-host {host_only(host)} to allow it"
    if method in {"GET", "HEAD"}:
        return None
    origin = headers.get("Origin")
    if origin and (origin == "null" or urlparse(origin).netloc.lower() != host.lower()):
        return 403, "cross-origin request refused"
    if not origin and headers.get("Sec-Fetch-Site") == "cross-site":
        return 403, "cross-site request refused"
    route = urlparse(path).path
    if route == "/api/upload":
        return None if headers.get("X-Filename") else (400, "X-Filename header is required")
    if (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/json":
        return 415, "Content-Type must be application/json"
    return None


# ---------------------------------------------------------------------------
# state: sessions, references, takes and paths, in one local JSON store
# ---------------------------------------------------------------------------


class State:
    """Everything the studio keeps, in ``<data-dir>``:

        store.json           sessions (settings, inputs), the gallery, the paths
        Input/, Output/      every image, once: imports and finished takes —
                             the folders are the storage and the source of truth;
                             a file that is gone takes its entry with it
        thumbs/<id>.png      320px previews, derived — rebuilt from the folders
        stage/takes/…        renders in flight, moved out as they are adopted
    """

    def __init__(self, paths: dict[str, str], data_dir: Path) -> None:
        self.data_dir = data_dir.expanduser()
        self.thumbs_dir = self.data_dir / "thumbs"
        self.stage = self.data_dir / "stage"
        #: the user-facing folders, which hold every image exactly once
        self.input_dir = self.data_dir / "Input"
        self.output_dir = self.data_dir / "Output"
        for directory in (self.thumbs_dir, self.input_dir, self.output_dir,
                          self.stage / "takes", self.data_dir / "tmp"):
            directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._data = self._load()
        self.paths = {**paths, **{k: v for k, v in self._data.get("paths", {}).items() if k in paths and v}}
        if self._data.get("paths") != self.paths:
            self._data["paths"] = dict(self.paths)
            self._save()
        self._migrate_legacy_assets()
        self._sync_missing_files()

    # store ------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        file = self.data_dir / "store.json"
        try:
            data = json.loads(file.read_text())
            if isinstance(data, dict):
                return data
        except (OSError, ValueError) as exc:
            if file.exists():
                broken = self.data_dir / f"store.broken-{datetime.now():%Y%m%d-%H%M%S}.json"
                with contextlib.suppress(OSError):
                    file.replace(broken)
                print(f"[studio] store.json was unreadable ({exc}); kept it as {broken.name}", flush=True)
        return {"sessions": {}, "gallery": {}}

    def _save(self) -> None:
        file = self.data_dir / "store.json"
        tmp = file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1))
        os.replace(tmp, file)

    # user folders -----------------------------------------------------------
    def _free_input_name(self, original: str) -> str:
        """A file name free in Input/, derived from the import's own name."""
        stem, suffix = os.path.splitext(safe_name(Path(original).name, "reference"))
        suffix = suffix.lower() or ".png"
        name = f"{stem}{suffix}"
        taken = {e.get("file") for s in self._data["sessions"].values() for e in (s.get("inputs") or {}).values()}
        n = 1
        while (self.input_dir / name).exists() or name in taken:
            name = f"{stem}-{n}{suffix}"
            n += 1
        return name

    def _input_path(self, entry: dict[str, Any]) -> Path:
        """A reference's file: usually ``Input/<file>``, but a reference taken
        from the gallery shares the take's file and carries its relative path."""
        file_name = entry.get("file") or ""
        if "/" in file_name or os.sep in file_name:
            return self.data_dir / file_name
        return self.input_dir / file_name

    def _take_path(self, item: dict[str, Any]) -> Path:
        params = item.get("params") or {}
        name = params.get("name") or f"{item.get('title') or 'take'}.png"
        return self.output_dir / name

    def _referenced_assets(self) -> set[str]:
        """Asset ids still attached to a session reference or a gallery take."""
        referenced = {e.get("asset_id") for s in self._data["sessions"].values()
                      for e in (s.get("inputs") or {}).values()}  # fmt: skip
        referenced.update(item.get("asset_id") for item in self._data["gallery"].values())
        return referenced

    def _drop_thumbs(self, asset_ids: set[str]) -> None:
        """Delete the derived previews — the callers check references first."""
        for asset_id in asset_ids - {None, ""}:
            with contextlib.suppress(OSError):
                (self.thumbs_dir / f"{asset_id}.png").unlink()

    def _migrate_legacy_assets(self) -> None:
        """One-time: ``assets/`` used to keep an internal copy of every image
        while Input/ and Output/ held user-facing duplicates. The folders are
        the storage now; any lost file is restored from assets/ first, then
        the whole folder goes."""
        assets_dir = self.data_dir / "assets"
        if not assets_dir.is_dir():
            return
        with self.lock:
            pairs = [(self._input_path(e), e.get("asset_id") or "")
                     for s in self._data["sessions"].values()
                     for e in (s.get("inputs") or {}).values()]  # fmt: skip
            pairs += [(self._take_path(i), i.get("asset_id") or "")
                      for i in self._data["gallery"].values()]  # fmt: skip
        for path, asset_id in pairs:
            found = sorted(assets_dir.glob(f"{asset_id}.*")) if asset_id else []
            if not path.exists() and found:
                with contextlib.suppress(OSError):
                    shutil.copy2(found[0], path)
                    print(f"[studio] restored {path.name} from the old assets folder", flush=True)
        shutil.rmtree(assets_dir, ignore_errors=True)
        print("[studio] removed the old internal assets folder — the images live in Input/ and Output/", flush=True)

    def _sync_missing_files(self) -> None:
        """The user-facing folders are the truth, both ways: deleting a take or
        a reference in the studio removes its file, and a file that is gone —
        deleted in Finder, say — takes its gallery item or reference entry
        with it (plus the thumbs nothing else points at)."""
        with self.lock:
            gone: set[str] = set()
            dropped = False
            for take_id, item in list(self._data["gallery"].items()):
                if self._take_path(item).exists():
                    continue
                gone.add(item.get("asset_id") or "")
                del self._data["gallery"][take_id]
                dropped = True
            for session in self._data["sessions"].values():
                inputs = session.get("inputs") or {}
                for key, entry in list(inputs.items()):
                    if entry.get("file") and self._input_path(entry).exists():
                        continue
                    gone.add(entry.get("asset_id") or "")
                    del inputs[key]
                    dropped = True
            if not dropped:
                return
            referenced = self._referenced_assets()
            self._save()
        self._drop_thumbs(gone - referenced)

    # paths ----------------------------------------------------------------
    def dirs_info(self) -> dict[str, str]:
        """The folders shown in the gallery: storage, Input, Output."""
        return {"data": str(self.data_dir.resolve()), "input": str(self.input_dir.resolve()),
                "output": str(self.output_dir.resolve())}  # fmt: skip

    def reveal_dir(self, target: str) -> None:
        dirs = {"data": self.data_dir, "input": self.input_dir, "output": self.output_dir}
        if target not in dirs:
            raise ValueError("unknown folder: choose data, input or output")
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(dirs[target])])

    def paths_info(self) -> dict[str, Any]:
        return {k: {"path": v, "ok": bool(v) and (v.startswith(("http://", "https://"))
                or Path(v).expanduser().is_dir())} for k, v in self.paths.items()}  # fmt: skip

    def set_paths(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            for key, value in changes.items():
                if key not in self.paths:
                    raise ValueError(f"unknown path: {key}")
                value = str(value).strip()
                if value and key != "comfyui" and not Path(value).expanduser().is_dir():
                    raise ValueError(f"{key}: no directory at {value}")
                self.paths[key] = value
            self._data["paths"] = dict(self.paths)
            self._save()
            return self.paths_info()

    # sessions -------------------------------------------------------------
    def sessions(self) -> list[str]:
        with self.lock:
            return sorted((s["name"] for s in self._data["sessions"].values()), key=str.lower)

    def session(self, name: str, *, create: bool = False) -> dict[str, Any] | None:
        with self.lock:
            found = next((s for s in self._data["sessions"].values() if s["name"] == name), None)
            if found is None and create:
                found = {"id": uuid.uuid4().hex[:12], "name": name, "created": now_iso(), "settings": {}, "inputs": {}}
                self._data["sessions"][found["id"]] = found
                self._save()
            return found

    def session_name(self, requested: Any) -> str:
        with self.lock:
            active = self._data.get("active")
        return str(requested or active or "session-1").strip() or "session-1"

    def activate(self, name: str) -> dict[str, Any]:
        with self.lock:
            session = self.session(name, create=True)
            assert session is not None
            self._data["active"] = session["name"]
            self._save()
            return {"name": session["name"], "settings": session.get("settings") or {}}

    def rename(self, name: str, new_name: str) -> dict[str, Any]:
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("enter a name")
        with self.lock:
            session = self._existing(name)
            if new_name != session["name"] and any(
                s["name"] == new_name for s in self._data["sessions"].values() if s["id"] != session["id"]
            ):
                raise ValueError("a session with that name already exists")
            session["name"] = new_name
            if self._data.get("active") == name:
                self._data["active"] = new_name
            self._save()
            return self.activate(new_name)

    def delete_session(self, name: str) -> dict[str, Any]:
        """Delete the instance, its takes and files nothing else uses."""
        with self.lock:
            session = self._existing(name)
            owned_assets = {entry.get("asset_id") for entry in (session.get("inputs") or {}).values()}
            input_paths = [self._input_path(e) for e in (session.get("inputs") or {}).values()]
            take_paths = []
            for take_id, item in list(self._data["gallery"].items()):
                if item.get("session_id") == session["id"]:
                    owned_assets.add(item.get("asset_id"))
                    take_paths.append(self._take_path(item))
                    del self._data["gallery"][take_id]
            del self._data["sessions"][session["id"]]
            unreferenced = owned_assets - self._referenced_assets() - {None}
            remaining_paths = {self._input_path(e) for other in self._data["sessions"].values()
                               for e in (other.get("inputs") or {}).values()}  # fmt: skip
            remaining_paths.update(self._take_path(i) for i in self._data["gallery"].values())
            remaining = self.sessions()
            result = self.activate(remaining[0] if remaining else "session-1")
        self._drop_thumbs(unreferenced)
        for path in [*take_paths, *input_paths]:
            if path not in remaining_paths:
                with contextlib.suppress(OSError):
                    path.unlink()
        return result

    def _existing(self, name: str) -> dict[str, Any]:
        session = self.session(name)
        if session is None:
            raise ValueError(f"no session named {name!r}")
        return session

    def save_settings(self, name: str, settings: dict[str, Any]) -> None:
        with self.lock:
            session = self.session(name, create=True)
            assert session is not None
            old = session.get("settings") or {}
            merged = {k: v for k, v in old.items() if settings.get(k) is not None}
            merged.update({k: v for k, v in settings.items() if v is not None})
            if merged != old:
                session["settings"] = merged
                self._save()

    # references: the session's input images, in the order the CLI gets them
    def inputs(self, name: str) -> list[dict[str, Any]]:
        with self.lock:
            self._sync_missing_files()
            session = self.session(name)
            entries = ((session or {}).get("inputs") or {}).items()
            ordered = sorted(entries, key=lambda pair: pair[1].get("added") or "")
            return [{"name": key, **entry, "url": asset_url(entry["asset_id"]), "thumb": thumb_url(entry["asset_id"])}
                    for key, entry in ordered]  # fmt: skip

    def _add_input(self, session_name: str, name: str, entry: dict[str, Any]) -> str:
        with self.lock:
            session = self.session(session_name, create=True)
            assert session is not None
            taken = session.get("inputs") or {}
            if len(taken) >= MAX_INPUTS:
                raise ValueError(f"Qwen-Image-2.1 takes at most {MAX_INPUTS} reference images")
            stem, suffix = os.path.splitext(name)
            chosen = name
            while chosen in taken:
                chosen = f"{stem}-{uuid.uuid4().hex[:4]}{suffix}"
            session.setdefault("inputs", {})[chosen] = entry
            self._save()
            return chosen

    def upload(self, session: str, original: str, body: BinaryIO, length: int) -> dict[str, Any]:
        stem, suffix = os.path.splitext(original)
        if suffix.lower() not in IMAGE_TYPES:
            raise ValueError("references must be PNG, JPEG or WebP")
        found = self.session(session)
        if found is not None and len(found.get("inputs") or {}) >= MAX_INPUTS:
            raise ValueError(f"Qwen-Image-2.1 takes at most {MAX_INPUTS} reference images")
        path = self.staged("uploads", f"{safe_name(stem, 'reference')}{suffix.lower()}")
        with open(path, "wb") as f:
            while length > 0:
                chunk = body.read(min(1 << 20, length))
                if not chunk:
                    break
                f.write(chunk)
                length -= len(chunk)
        size = image_size(path)
        if size is None:
            sniffed = sniff_image(path)
            if sniffed is None:
                with contextlib.suppress(OSError):
                    path.unlink()
                    path.parent.rmdir()
                raise ValueError(f"{original} is not an image")
        # the staged upload moves into Input/ as the one and only copy
        file_name = self._free_input_name(original)
        asset_id = self.adopt(path, self.input_dir / file_name)
        with contextlib.suppress(OSError):
            path.parent.rmdir()
        entry = {"asset_id": asset_id, "original_name": original, "file": file_name,
                 "width": size[0] if size else None,
                 "height": size[1] if size else None, "added": now_iso()}  # fmt: skip
        return {"name": self._add_input(session, path.name, entry)}

    def delete_input(self, session: str, name: str) -> None:
        removed = None
        with self.lock:
            found = self.session(session)
            inputs = (found or {}).get("inputs") or {}
            if name in inputs:
                removed = inputs.pop(name)
                self._save()
        if removed is None:
            return
        # the file goes too, unless another session's reference uses it
        path = self._input_path(removed)
        still_used = any(self._input_path(e) == path
                         for s in self._data["sessions"].values()
                         for e in (s.get("inputs") or {}).values())  # fmt: skip
        if not still_used:
            with contextlib.suppress(OSError):
                path.unlink()
        # and the thumb, unless the gallery or another reference needs it
        with self.lock:
            unreferenced = removed.get("asset_id") not in self._referenced_assets()
        if unreferenced:
            self._drop_thumbs({removed.get("asset_id")})

    def clear_inputs(self, session: str) -> None:
        """Every reference image out of the session (the refresh button's reset)."""
        removed: list[dict[str, Any]] = []
        with self.lock:
            found = self.session(session)
            inputs = (found or {}).get("inputs") or {}
            if not inputs:
                return
            removed = list(inputs.values())
            found["inputs"] = {}
            self._save()
        with self.lock:
            still_used = {self._input_path(e) for s in self._data["sessions"].values()
                          for e in (s.get("inputs") or {}).values()}  # fmt: skip
            unreferenced = {e.get("asset_id") for e in removed} - self._referenced_assets()
        for path in {self._input_path(e) for e in removed}:
            if path not in still_used:
                with contextlib.suppress(OSError):
                    path.unlink()
        self._drop_thumbs(unreferenced)

    def take_as_input(self, session: str, take_id: str) -> dict[str, Any]:
        item = self.gallery_get(take_id)
        params = item.get("params") or {}
        name = params.get("name") or f"{take_id}.png"
        # no copy: the reference shares the take's file in Output/
        entry = {"asset_id": item["asset_id"], "original_name": name,
                 "file": f"Output/{name}",
                 "width": params.get("width"),
                 "height": params.get("height"), "added": now_iso()}  # fmt: skip
        return {"name": self._add_input(session, name, entry)}

    def attach_input(self, session: str, asset_id: str) -> dict[str, Any]:
        """Attach an already-stored image as a reference of the session — no
        new copy: the entry shares the file the store already has."""
        source = self._entry_for_asset(asset_id)
        if source is None:
            raise ValueError("the image file is no longer on disk")
        name = Path(source["original_name"] or source["file"] or "reference.png").name
        return {"name": self._add_input(session, name, {**source, "added": now_iso()})}

    def _entry_for_asset(self, asset_id: str) -> dict[str, Any] | None:
        """A session reference that owns this asset and still has its file."""
        with self.lock:
            for s in self._data["sessions"].values():
                for e in (s.get("inputs") or {}).values():
                    if e.get("asset_id") == asset_id and e.get("file") and self._input_path(e).exists():
                        return dict(e)
        return None

    def reuse_take(self, session: str, take_id: str) -> dict[str, Any]:
        """A take's references come back with its settings — re-attached to the
        session when their files still exist, skipped when they don't."""
        item = self.gallery_get(take_id)
        recorded = len(item.get("inputs") or [])
        added = 0
        with self.lock:
            for ref in item.get("inputs") or []:
                source = self._entry_for_asset(ref.get("asset_id"))
                if source is None:
                    continue
                self._add_input(session, Path(source["original_name"] or "reference.png").name, {
                    "asset_id": ref["asset_id"], "original_name": source["original_name"] or "reference.png",
                    "file": source["file"], "width": source.get("width"),
                    "height": source.get("height"), "added": now_iso()})  # fmt: skip
                added += 1
        return {"recorded": recorded, "added": added}

    def delete_input_asset(self, asset_id: str) -> None:
        """Delete an image from the gallery's Input tab: its reference entries
        go, and the file goes with them — unless a gallery take shares it."""
        with self.lock:
            path = self.asset_path(asset_id)
            owners = [(sid, key) for sid, s in self._data["sessions"].items()
                      for key, e in (s.get("inputs") or {}).items()
                      if e.get("asset_id") == asset_id]  # fmt: skip
            if not owners:
                raise ValueError("no reference uses this image")
            shared_take = any(i.get("asset_id") == asset_id for i in self._data["gallery"].values())
            for sid, key in owners:
                del self._data["sessions"][sid]["inputs"][key]
            self._save()
        if not shared_take and path is not None:
            with contextlib.suppress(OSError):
                path.unlink()
            self._drop_thumbs({asset_id})

    # assets ---------------------------------------------------------------
    def staged(self, kind: str, name: str) -> Path:
        path = self.stage / kind / uuid.uuid4().hex / Path(name).name
        path.parent.mkdir(parents=True)
        return path

    def adopt(self, path: Path, dest: Path) -> str:
        """A finished image joins the store: the file moves into its user
        folder (Input/ or Output/) as the one and only copy, gets a thumb,
        and an asset id the gallery and references address it by."""
        if dest.exists():
            raise ValueError(f"{dest.name} already exists in {dest.parent.name}/")
        asset_id = uuid.uuid4().hex[:12]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        make_thumb(dest, self.thumbs_dir / f"{asset_id}.png")
        return asset_id

    def asset_path(self, asset_id: str) -> Path | None:
        """The one file an asset id stands for: a reference's file in Input/
        or a take's file in Output/ — the folders are the storage."""
        if not re.fullmatch(r"[0-9a-f]{6,16}", asset_id):
            return None
        with self.lock:
            for s in self._data["sessions"].values():
                for e in (s.get("inputs") or {}).values():
                    if e.get("asset_id") == asset_id and e.get("file"):
                        return self._input_path(e)
            for item in self._data["gallery"].values():
                if item.get("asset_id") == asset_id:
                    return self._take_path(item)
        return None

    def asset_bytes(self, asset_id: str) -> tuple[bytes, str] | None:
        path = self.asset_path(asset_id)
        if path is None:
            return None
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return path.read_bytes(), ctype

    def thumb_bytes(self, asset_id: str) -> tuple[bytes, str] | None:
        if not re.fullmatch(r"[0-9a-f]{6,16}", asset_id):
            return None
        thumb = self.thumbs_dir / f"{asset_id}.png"
        if not thumb.is_file():
            source = self.asset_path(asset_id)
            if source is None or not make_thumb(source, thumb):
                return self.asset_bytes(asset_id)
        return thumb.read_bytes(), "image/png"

    def materialise(self, asset_id: str, name: str) -> str:
        """An asset as a file the CLI can read; it lives in Input/ or Output/."""
        path = self.asset_path(asset_id)
        if path is None:
            raise ValueError(f"reference image {name} is gone from the studio's folders")
        return str(path)

    # takes: the session's images in the gallery -----------------------------
    def takes(self, session: str) -> list[dict[str, Any]]:
        with self.lock:
            self._sync_missing_files()
            found = self.session(session)
            if found is None:
                return []
            items = [item for item in self._data["gallery"].values() if item.get("session_id") == found["id"]]
        items.sort(key=lambda item: item.get("created") or "", reverse=True)
        return [{"id": item["id"], "url": asset_url(item["asset_id"]), "thumb": thumb_url(item["asset_id"]),
                 "starred": bool(item.get("starred")), "params": item.get("params") or {}}
                for item in items]  # fmt: skip

    def gallery_all(self) -> list[dict[str, Any]]:
        with self.lock:
            self._sync_missing_files()
            names = {s["id"]: s["name"] for s in self._data["sessions"].values()}
            items = list(self._data["gallery"].values())
        items.sort(key=lambda item: item.get("created") or "", reverse=True)
        return [{"id": item["id"], "url": asset_url(item["asset_id"]), "thumb": thumb_url(item["asset_id"]),
                 "title": item.get("title") or "", "session": names.get(item.get("session_id"), "—"),
                 "file": (item.get("params") or {}).get("name") or f"{item.get('title') or 'take'}.png",
                 "params": item.get("params") or {}}
                for item in items]  # fmt: skip

    def inputs_all(self) -> list[dict[str, Any]]:
        """Every imported reference across sessions, once each — the gallery's Input tab."""
        with self.lock:
            self._sync_missing_files()
            names = {s["id"]: s["name"] for s in self._data["sessions"].values()}
            rows: list[dict[str, Any]] = []
            seen: set[str] = set()
            for s in self._data["sessions"].values():
                for entry in (s.get("inputs") or {}).values():
                    aid = entry.get("asset_id")
                    if not aid or aid in seen:
                        continue
                    seen.add(aid)
                    rows.append({"asset_id": aid, "name": Path(entry.get("file") or entry.get("original_name") or "image").name,
                                 "session": names.get(s["id"], "—"), "width": entry.get("width"),
                                 "height": entry.get("height"), "added": entry.get("added") or "",
                                 "url": asset_url(aid), "thumb": thumb_url(aid)})  # fmt: skip
        rows.sort(key=lambda row: row["added"], reverse=True)
        return rows

    def gallery_get(self, take_id: str) -> dict[str, Any]:
        with self.lock:
            item = self._data["gallery"].get(take_id)
        if item is None:
            raise ValueError(f"no take named {take_id!r}")
        return item

    def delete_take(self, take_id: str) -> None:
        with self.lock:
            item = self._data["gallery"].pop(take_id, None)
            if item is None:
                return
            # the take's own asset is referenced by nothing else once the item is gone
            unreferenced = item.get("asset_id") not in self._referenced_assets()
            self._save()
        if unreferenced:
            # the file is the storage: it goes only when nothing points at it
            with contextlib.suppress(OSError):
                self._take_path(item).unlink()
            self._drop_thumbs({item.get("asset_id")})

    def take_finished(self, job: dict[str, Any], output: Path) -> str:
        result = job["result"]
        settings = job["settings"]
        params = {
            "name": output.name, "prompt": settings["prompt"],
            "seed": settings["seed"], "steps": settings["steps"],
            "width": result["width"], "height": result["height"], "mode": result["mode"],
            "edit": bool(job["inputs"]), "created": job["created"], "elapsed": job["elapsed"], "settings": settings,
        }  # fmt: skip
        with self.lock:
            if job["session_id"] not in self._data["sessions"]:
                raise ValueError("the session was deleted while this render was running")
            # the render's file moves into Output/ as the one and only copy
            asset_id = self.adopt(output, self.output_dir / output.name)
            item = {
                "id": uuid.uuid4().hex[:12], "kind": "image", "asset_id": asset_id, "title": output.stem,
                "session_id": job["session_id"],
                "params": {k: v for k, v in params.items() if v not in (None, "")},
                "inputs": [{"asset_id": i["asset_id"], "role": "input"} for i in job["inputs"]],
                "created": job["created"], "starred": False,
            }  # fmt: skip
            self._data["gallery"][item["id"]] = item
            self._save()
        return f"[studio] kept {output.name} in the gallery (item {item['id']})"


def asset_url(asset_id: str) -> str:
    return f"/api/assets/{asset_id}"


def thumb_url(asset_id: str) -> str:
    return f"/api/assets/{asset_id}/thumb?w=320"


# ---------------------------------------------------------------------------
# runner: one render at a time
# ---------------------------------------------------------------------------


def as_int(value: Any, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number") from None
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return number


def resolve_mentions(prompt: str, names: list[str]) -> str:
    """``@name`` of a reference image → ``<imageN>``, its place in the list, as Qwen-Image-2.1 tags images.

    An ``@`` that names no reference (an email, a handle) stays as written.
    """
    index = {name: i for i, name in enumerate(names, 1)}
    return MENTION_RE.sub(lambda m: f"<image{index[m[1]]}>" if m[1] in index else m[0], prompt)


def clean_settings(req: dict[str, Any]) -> dict[str, Any]:
    """The form's settings, validated into what the ComfyUI graphs accept."""
    prompt = str(req.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("write a prompt")
    ratio = req.get("ratio") or None
    if ratio is not None and ratio not in RATIOS:
        raise ValueError(f"unknown aspect ratio {ratio}")
    settings: dict[str, Any] = {"prompt": prompt, "ratio": ratio}
    for key in ("width", "height"):
        if req.get(key) not in (None, ""):
            value = as_int(req[key], key, 256, 4096)
            if value % 32:
                raise ValueError(f"{key} must be a multiple of 32")
            settings[key] = value
    # Qwen's 2.1 model-card example uses 40 steps; ComfyUI's template uses 25.
    settings["steps"] = as_int(req.get("steps", 40), "steps", 1, 200)
    settings["seed"] = as_int(req.get("seed", 42), "seed", 0, 2**63 - 1)
    settings["transparent"] = bool(req.get("transparent"))
    return settings


# ---------------------------------------------------------------------------
# ComfyUI backend: renders through a local ComfyUI (its own models), so the
# studio can work with the quantized weights a diffusers pipeline cannot load.
#
# The graphs mirror the studio's own workflows “image_qwen_image_2_1_t2i” and
# “image_qwen_image_2_1_image_edit”: UNETLoader + CLIPLoader + VAELoader +
# TextEncodeQwenImage21 (+ QwenImage21Cache) + KSampler + VAEDecode. The
# parameters (prompt, steps, seed, size, references) are injected per render.
# ---------------------------------------------------------------------------

COMFY_PORTS = (8188, 8189, 8190)
COMFY_START_TIMEOUT = 180.0
#: The side of the square a reference is fitted to — the node takes a side, not
#: an area — so 1024 ≈ 1 MP, what the CLI does for an edit. Their own workflows use 1024.
COMFY_REFERENCE_RESOLUTION = 1024
#: The edit canvas' total-pixel budget, per the official 2.1 edit recipe: the
#: reference is resized to about this many pixels and the canvas should stay
#: close to that — a much larger canvas shifts the edit and the untouched
#: surroundings come out soft.
EDIT_PIXEL_BUDGET = 1024 * 1024


def validate_edit_settings(settings: dict[str, Any]) -> None:
    """Studio quality guardrails, not model limitations or official mandates."""
    if settings["steps"] < 25:
        raise ValueError("editing needs at least 25 steps; 40 is strongly recommended")
    width, height = settings.get("width"), settings.get("height")
    if bool(width) != bool(height):
        raise ValueError("editing needs both width and height, or leave both on Auto")
    if width and height and width * height > EDIT_PIXEL_BUDGET * 1.5:
        raise ValueError("edit canvas exceeds 1.5 megapixels; use Auto or about 1024 x 1024, then upscale")


def _http_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> Any:
    request = urllib.request.Request(url)
    if payload is not None:
        request.data = json.dumps(payload).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # ComfyUI explains a rejected graph in the body; that is the useful part
        detail = exc.read().decode("utf-8", "replace")[:800]
        with contextlib.suppress(Exception):
            detail = json.dumps(json.loads(detail).get("error", json.loads(detail)), ensure_ascii=False)[:800]
        raise ValueError(f"{exc.code} from {url.rsplit('/', 1)[-1]}: {detail}") from None


def comfy_alive(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/system_stats", timeout=1.5) as response:
            return response.status == 200
    except OSError:
        return False


def pick_option(options: list[str], *patterns: str) -> str | None:
    """First exact match, then first regex match, against ComfyUI's model list."""
    for pattern in patterns:
        if pattern in options:
            return pattern
    for pattern in patterns:
        if pattern.endswith("*"):
            stem = pattern[:-1]
            if match := next((o for o in options if o.startswith(stem)), None):
                return match
            continue
        regex = re.compile(pattern)
        if match := next((o for o in options if regex.search(o)), None):
            return match
    return None


def build_comfy_graph(mode: str, settings: dict[str, Any], ref_names: list[str], models: dict[str, str], client_id: str) -> dict[str, Any]:
    """The flat API-format graph: the studio's two workflows, parameterised."""
    prompt = settings["prompt"]
    # the CLI's own recipe for transparent takes (the 2.1 VAE keeps four channels)
    if settings.get("transparent"):
        prompt += " The image has alpha channel and the background is transparent."
    graph: dict[str, Any] = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": models["unet"], "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": models["clip"], "type": "qwen_image", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": models["vae"]}},
    }
    encode: dict[str, Any] = {
        "class_type": "TextEncodeQwenImage21",
        "inputs": {"clip": ["clip", 0], "prompt": prompt, "negative_prompt": "", "resolution": COMFY_REFERENCE_RESOLUTION},
    }
    if mode == "edit":
        encode["inputs"]["vae"] = ["vae", 0]
        for i, name in enumerate(ref_names, 1):
            graph[f"load{i}"] = {"class_type": "LoadImage", "inputs": {"image": name, "upload": "image"}}
            # the node's autogrow group reaches the API as "images.image_N"
            encode["inputs"][f"images.image_{i}"] = [f"load{i}", 0]
    graph["encode"] = encode

    width, height = settings.get("width"), settings.get("height")
    if width and height:
        latent_ref = ["latent", 0]
        graph["latent"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
    elif mode == "t2i":
        base = RATIO_SIZES.get(settings.get("ratio") or "1:1", RATIO_SIZES["1:1"])
        latent_ref = ["latent", 0]
        graph["latent"] = {"class_type": "EmptyLatentImage", "inputs": {"width": base[0], "height": base[1], "batch_size": 1}}
    elif mode == "edit" and settings.get("ratio"):
        # an edit canvas keeps the official ~1 MP pixel budget, whatever the ratio:
        # the 4 MP t2i sizes are four times what the references are conditioned at,
        # which is what makes the edited centre sharp and the surroundings soft
        rw, rh = (int(part) for part in settings["ratio"].split(":"))
        aspect = rw / rh
        latent_w = max(32, round(math.sqrt(EDIT_PIXEL_BUDGET * aspect) / 32) * 32)
        latent_h = max(32, round(math.sqrt(EDIT_PIXEL_BUDGET / aspect) / 32) * 32)
        latent_ref = ["latent", 0]
        graph["latent"] = {"class_type": "EmptyLatentImage", "inputs": {"width": latent_w, "height": latent_h, "batch_size": 1}}
    else:
        # the text node's latent is sized to the first reference image
        latent_ref = ["encode", 2]

    graph["cache"] = {"class_type": "QwenImage21Cache", "inputs": {"model": ["unet", 0], "device": "auto", "dtype": "default"}}
    graph["sample"] = {"class_type": "KSampler", "inputs": {
        "model": ["cache", 0], "positive": ["encode", 0], "negative": ["encode", 1], "latent_image": latent_ref,
        "seed": settings["seed"], "steps": settings["steps"], "cfg": 1,
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1,
    }}  # fmt: skip
    graph["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}}
    graph["save"] = {"class_type": "SaveImage", "inputs": {"images": ["decode", 0], "filename_prefix": f"qwen-studio/{client_id}"}}
    return graph


class ComfyBackend:
    """One ComfyUI server per studio: reuse one already running, else start it
    headless from the path the user set under ⚙ Paths."""

    def __init__(self, target: str, log_path: Path | None = None) -> None:
        self.target = target.strip().rstrip("/")
        self.log_path = log_path
        self.base: str | None = None
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def _log(self, line: str) -> None:
        print(f"[comfyui] {line}", flush=True)
        if self.log_path is not None:
            with contextlib.suppress(OSError):
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a") as f:
                    f.write(f"[comfyui {datetime.now():%H:%M:%S}] {line}\n")

    def _tail(self, lines: int = 12) -> str:
        """What the headless start said before it gave up — shown in the error."""
        if self.log_path is None or not self.log_path.is_file():
            return ""
        text = self.log_path.read_text(errors="replace").splitlines()[-lines:]
        return "\n".join(text)

    @staticmethod
    def _safe_for_edit(base: str) -> bool:
        """MPS Qwen 2.1 VAE encoding can silently corrupt reference latents.

        Check the server, not the Studio host: an explicit URL may point to CUDA.
        ComfyUI reports its launch arguments through /system_stats.
        """
        stats = _http_json(f"{base}/system_stats")
        devices = stats.get("devices", [])
        if not devices:
            raise ValueError("cannot verify ComfyUI device for safe image editing")
        return not any(d.get("type") == "mps" for d in devices) or "--cpu-vae" in stats.get("system", {}).get("argv", [])

    def resolve(self, *, editing: bool = False) -> str:
        with self.lock:
            if self.base and comfy_alive(self.base) and self._sees_models(self.base) and (not editing or self._safe_for_edit(self.base)):
                return self.base
            self.base = None
            if self.target.startswith(("http://", "https://")):
                if not comfy_alive(self.target):
                    raise ValueError(f"ComfyUI is not answering at {self.target}")
                if editing and not self._safe_for_edit(self.target):
                    raise ValueError("MPS image editing requires ComfyUI started with --cpu-vae; use a local folder path for automatic safe startup")
                self.base = self.target
                return self.base
            for port in COMFY_PORTS:
                base = f"http://127.0.0.1:{port}"
                if comfy_alive(base):
                    if self._sees_models(base) and (not editing or self._safe_for_edit(base)):
                        self.base = base
                        self._log(f"reusing the ComfyUI already running on {base}")
                        return base
                    self._log(f"ComfyUI on {base} lacks Qwen models or safe edit settings — starting our own")
            root = Path(self.target).expanduser()
            main_py = root / "ComfyUI" / "main.py"
            if not main_py.is_file():
                main_py = root / "main.py"
            if not main_py.is_file():
                raise ValueError(f"no ComfyUI main.py under {root}")
            port = next((p for p in COMFY_PORTS if not _port_busy(p)), COMFY_PORTS[0])
            python = self._find_python(root)
            args = [str(python), str(main_py), "--port", str(port), "--disable-auto-launch",
                    "--cache-classic"]  # release the previous render's buffers instead of accumulating
            if sys.platform == "darwin":
                # Keep diffusion on MPS; only VAE encoding/decoding runs on CPU.
                args.append("--cpu-vae")
            # the Comfy desktop app's model wiring, when present, so a headless
            # start sees the same models the desktop app sees
            desktop_yaml = Path("~/Library/Application Support/Comfy Desktop/shared_model_paths.yaml").expanduser()
            if desktop_yaml.is_file():
                args += ["--extra-model-paths-config", str(desktop_yaml)]
            self._log(f"starting ComfyUI headless on port {port} ({python})")
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                out = open(self.log_path, "a")
                out.write(f"\n[comfyui {datetime.now():%H:%M:%S}] {' '.join(args)}\n")
                out.flush()
            else:
                out = subprocess.DEVNULL
            self.proc = subprocess.Popen(
                args,
                cwd=str(main_py.parent), env=env, stdout=out, stderr=subprocess.STDOUT,
                start_new_session=True,
            )  # fmt: skip
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + COMFY_START_TIMEOUT
            while time.monotonic() < deadline:
                if comfy_alive(base):
                    self.base = base
                    self._log(f"ComfyUI is up on {base}")
                    return base
                if self.proc.poll() is not None:
                    raise ValueError("ComfyUI exited during startup (exit "
                                     f"{self.proc.returncode}):\n{self._tail()}")
                time.sleep(0.5)
            raise ValueError(f"ComfyUI did not come up within three minutes:\n{self._tail()}")

    @staticmethod
    def _find_python(root: Path) -> Path:
        """The interpreter that can actually run ComfyUI — torch decides, not existence.

        The desktop layout keeps it in ``ComfyUI/.venv``; a plain checkout may use
        ``.venv`` or ``venv``; a portable build ships ``standalone-env``. A
        ``standalone-env`` without torch is a real trap, so every candidate is asked.
        """
        candidates = [root / "ComfyUI" / ".venv" / "bin" / "python",
                      root / ".venv" / "bin" / "python",
                      root / "venv" / "bin" / "python",
                      root / "ComfyUI" / "venv" / "bin" / "python",
                      root / "standalone-env" / "bin" / "python"]
        tried = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                probe = subprocess.run([str(candidate), "-c", "import torch"], capture_output=True, timeout=90)
            except (OSError, subprocess.SubprocessError):
                tried.append(f"{candidate} (could not run)")
                continue
            if probe.returncode == 0:
                return candidate
            tried.append(f"{candidate} (no torch)")
        detail = "; ".join(tried) or "no Python found"
        raise ValueError(f"no ComfyUI Python with torch under {root} — tried: {detail}")

    @staticmethod
    def _sees_models(base: str) -> bool:
        try:
            models = _http_json(f"{base}/models/diffusion_models", timeout=5.0)
        except (OSError, ValueError):
            return False
        return any("qwen" in str(name).lower() for name in models)

    def ws_base(self) -> str:
        return self.base.replace("http://", "ws://", 1)

    def object_info(self) -> dict[str, Any]:
        return _http_json(f"{self.base}/object_info", timeout=10.0)

    def pick_models(self) -> dict[str, str]:
        """The model files for the graph, chosen from what this ComfyUI actually has."""
        info = self.object_info()
        chosen = {}
        for key, node, field, patterns in (
            ("unet", "UNETLoader", "unet_name",
             ("qwen_image_2.1_int8_convrot.safetensors", "qwen_image_2_1", r"qwen_image(?!_vae)")),
            ("clip", "CLIPLoader", "clip_name",
             ("qwen3vl_8b_int8_convrot.safetensors", "qwen3vl", r"qwen_?2\.?5_?vl", r"qwen.*vl")),
            ("vae", "VAELoader", "vae_name",
             ("qwen_image_2.1_vae_bf16.safetensors", "qwen_image_2_1_vae", "qwen_image_vae", r"qwen_image.*vae")),
        ):  # fmt: skip
            options = info.get(node, {}).get("input", {}).get("required", {}).get(field, [None])[0] or []
            found = pick_option(list(options), *patterns)
            if found is None:
                raise ValueError(f"ComfyUI has no Qwen-Image model for {node} — put the weights in its models folder")
            chosen[key] = found
        return chosen

    def upload(self, path: Path) -> str:
        """A reference image goes in through ComfyUI's own upload endpoint."""
        boundary = uuid.uuid4().hex
        name = f"qwen-studio-{uuid.uuid4().hex[:8]}{path.suffix.lower()}"
        body = bytearray()
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        body += path.read_bytes()
        body += f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(f"{self.base}/upload/image", data=bytes(body), method="POST")
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read())
        return result.get("name") or name

    def submit(self, graph: dict[str, Any], client_id: str) -> str:
        result = _http_json(f"{self.base}/prompt", {"prompt": graph, "client_id": client_id})
        return result["prompt_id"]

    def history(self, prompt_id: str) -> dict[str, Any]:
        return _http_json(f"{self.base}/history/{prompt_id}", timeout=10.0)

    def fetch_image(self, item: dict[str, Any]) -> bytes:
        query = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
        with urllib.request.urlopen(f"{self.base}/view?{query}", timeout=60) as response:
            return response.read()

    def interrupt(self) -> None:
        with contextlib.suppress(OSError, ValueError):
            _http_json(f"{self.base}/interrupt", {}, timeout=5.0)

    def shutdown(self) -> None:
        """Only the ComfyUI this studio started; one it found running is left alone."""
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        # it runs in its own session, so the whole group can be signalled
        with contextlib.suppress(Exception):
            os.killpg(proc.pid, signal.SIGTERM)
        for _ in range(30):  # three seconds to take the hint
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        with contextlib.suppress(Exception):
            os.killpg(proc.pid, signal.SIGKILL)


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


class Runner:
    def __init__(self, state: State) -> None:
        self.state = state
        self.comfy: ComfyBackend | None = None
        self.jobs: dict[str, dict[str, Any]] = {}
        self.pending: list[str] = []
        self.current: str | None = None
        self.proc: subprocess.Popen | None = None
        self.cond = threading.Condition()
        self.subscribers: list[queue.Queue] = []
        self.sub_lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2000)
        with self.sub_lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.sub_lock, contextlib.suppress(ValueError):
            self.subscribers.remove(q)

    def emit(self, kind: str, payload: Any) -> None:
        message = json.dumps({"type": kind, "data": payload})
        with self.sub_lock:
            for q in self.subscribers:
                with contextlib.suppress(queue.Full):
                    q.put_nowait(message)

    def log(self, job: dict[str, Any], line: str, rewrites: bool = False, kind: str | None = None) -> None:
        self.emit("log", {"session": job["session"], "job": job["id"], "line": line, "rewrites": rewrites, "kind": kind})

    def summary(self, job: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "session", "status", "created", "elapsed", "error", "argv_display", "result")
        return {**{k: job.get(k) for k in keys}, "prompt": job["settings"]["prompt"],
                "ratio": job["settings"]["ratio"], "seed": job["settings"]["seed"],
                "progress": dict(job["progress"])}  # fmt: skip

    def queue_state(self) -> list[dict[str, Any]]:
        with self.cond:
            ids = ([self.current] if self.current else []) + self.pending
            return [self.summary(self.jobs[i]) for i in ids]

    def submit(self, req: dict[str, Any]) -> dict[str, Any]:
        state = self.state
        session = state.session_name(req.get("session"))
        settings = clean_settings(req)
        inputs = state.inputs(session)
        if inputs:
            validate_edit_settings(settings)
        comfy_target = (state.paths.get("comfyui") or "").strip()
        if not comfy_target:
            raise ValueError("the ComfyUI path is not set — set it under Paths")
        if settings.get("enhance") or settings.get("think"):
            raise ValueError("the ComfyUI backend has no prompt enhancer")
        job_id = uuid.uuid4().hex[:10]
        output = state.stage / "takes" / f"take-{datetime.now():%m%d-%H%M%S}-{job_id[:4]}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        prompt = resolve_mentions(settings["prompt"], [i["name"] for i in inputs])
        if settings.get("width") and settings.get("height"):
            size = f"{settings['width']}×{settings['height']}"
        elif settings.get("ratio"):
            size = settings["ratio"]
        elif inputs:
            size = "auto · first reference"
        else:
            size = "1024×1024"
        session_id = state.session(session, create=True)["id"]
        job = {
            "id": job_id, "session": session, "session_id": session_id, "status": "queued", "created": now_iso(),
            "settings": settings, "inputs": inputs, "output": str(output),
            "argv_display": (f"comfyui · {'edit' if inputs else 'text → image'} · {size}"
                             f" · steps {settings['steps']} · seed {settings['seed']}"),  # fmt: skip
            "prompt_text": prompt, "progress": {"stage": None, "step": 0, "total": 0}, "result": {},
        }  # fmt: skip
        with self.cond:
            self.jobs[job_id] = job
            self.pending.append(job_id)
            self.cond.notify()
        self.emit("queue", self.queue_state())
        return self.summary(job)

    def cancel(self, job_id: str) -> bool:
        with self.cond:
            job = self.jobs.get(job_id)
            if job_id in self.pending:
                self.pending.remove(job_id)
                job["status"] = "cancelled"
                self.emit("queue", [self.summary(self.jobs[i]) for i in ([self.current] if self.current else []) + self.pending])
                return True
            if job_id == self.current and self.comfy is not None:
                job["status"] = "cancelling"
                self.comfy.interrupt()
                return True
        return False

    def _loop(self) -> None:
        while True:
            with self.cond:
                while not self.pending:
                    self.cond.wait()
                self.current = self.pending.pop(0)
                job = self.jobs[self.current]
            try:
                self._run(job)
            except Exception as exc:
                job["status"], job["error"] = "failed", str(exc)
                self.log(job, f"[studio] {exc}", kind="failed")
            finally:
                with self.cond:
                    self.current, self.proc = None, None
                self.emit("job", self.summary(job))
                self.emit("queue", self.queue_state())

    def _run(self, job: dict[str, Any]) -> None:
        job["status"] = "running"
        started = time.monotonic()
        self.emit("queue", self.queue_state())
        self.log(job, f"$ {job['argv_display']}", kind="cmd")
        try:
            self._run_comfy(job, started)
        except Exception as exc:
            job["status"], job["error"] = "failed", str(exc)
            self.log(job, f"[studio] {exc}", kind="failed")
        job["elapsed"] = round(time.monotonic() - started, 1)
        if job["status"] == "cancelling":
            job["status"] = "cancelled"
        elif job["status"] == "done":
            try:
                self.log(job, self.state.take_finished(job, Path(job["output"])))
            except Exception as exc:
                job["status"], job["error"] = "failed", f"{Path(job['output']).name} could not be kept: {exc}"
            self.emit("takes", {"session": job["session"]})
        Path(job["output"]).unlink(missing_ok=True)  # adopted by hardlink, or not worth keeping
        self.log(job, f"[studio] {job['status']} in {job['elapsed']}s", kind=job["status"])

    # ── the ComfyUI path: submit a graph, stream its progress, fetch the PNG ──
    def _run_comfy(self, job: dict[str, Any], started: float) -> None:
        settings, inputs = job["settings"], job["inputs"]
        mode = "edit" if inputs else "t2i"
        target = (self.state.paths.get("comfyui") or "").strip()
        log_path = self.state.data_dir / "logs" / "comfyui.log"
        if self.comfy is None:
            self.comfy = ComfyBackend(target, log_path)
        elif self.comfy.target != target:
            self.comfy.shutdown()
            self.comfy = ComfyBackend(target, log_path)
        base = self.comfy.resolve(editing=mode == "edit")
        job["progress"].update(stage="load", step=0, total=0)
        self.emit("progress", {"id": job["id"], "progress": job["progress"], "result": job["result"]})
        client_id = f"qwen-studio-{job['id']}"
        ref_names = []
        for i, ref in enumerate(inputs, 1):
            name = self.comfy.upload(Path(self.state.materialise(ref["asset_id"], ref["name"])))
            ref_names.append(name)
            self.log(job, f"[studio] reference {i} → ComfyUI as {name}")
        graph = build_comfy_graph(mode, {**settings, "prompt": job["prompt_text"]}, ref_names, self.comfy.pick_models(), client_id)
        encode_inputs = graph["encode"]["inputs"]
        latent = graph["sample"]["inputs"]["latent_image"]
        latent_desc = "first reference" if latent[0] == "encode" else f"{graph[latent[0]]['inputs']['width']}×{graph[latent[0]]['inputs']['height']}"
        self.log(job, "[studio] graph injected → "
                  f"unet {graph['unet']['inputs']['unet_name']} · clip {graph['clip']['inputs']['clip_name']} · vae {graph['vae']['inputs']['vae_name']}"
                  f" · latent {latent_desc} · steps {graph['sample']['inputs']['steps']} · seed {graph['sample']['inputs']['seed']}"
                  f" · cfg {graph['sample']['inputs']['cfg']} · {graph['sample']['inputs']['sampler_name']}/{graph['sample']['inputs']['scheduler']}"
                  f" · refs {len(ref_names)} · transparent {'on' if settings.get('transparent') else 'off'}")
        if mode == "edit" and latent[0] == "latent":
            # the official docs' own caution: an edit canvas far from the reference's
            # resized size degrades — name the size the recipe would have used
            first = next((i for i in job["inputs"] if i.get("width") and i.get("height")), None)
            if first is not None:
                ratio = first["width"] / first["height"]
                rec_w = max(32, round(math.sqrt(1024 * 1024 * ratio) / 32) * 32)
                rec_h = max(32, round(math.sqrt(1024 * 1024 / ratio) / 32) * 32)
                self.log(job, f"[studio] note: edits look best near the reference's own scale — "
                              f"about {rec_w}×{rec_h} here; {settings['width']}×{settings['height']} may go soft")
        prompt_id = self.comfy.submit(graph, client_id)
        self._comfy_wait(job, client_id, prompt_id)
        if job["status"] == "cancelling":
            return
        history = self.comfy.history(prompt_id).get(prompt_id) or {}
        if str((history.get("status") or {}).get("status_str", "")).lower() not in ("success", ""):
            raise ValueError("ComfyUI reported an unsuccessful status")
        item = next((img for outputs in (history.get("outputs") or {}).values()
                     for img in (outputs.get("images") or [])), None)
        if item is None:
            raise ValueError("ComfyUI finished but returned no image")
        output = Path(job["output"])
        output.write_bytes(self.comfy.fetch_image(item))
        size = image_size(output) or (settings.get("width") or 1024, settings.get("height") or 1024)
        job["result"].update(width=size[0], height=size[1], mode="RGB")
        self.log(job, f"Saved {output} ({size[0]}x{size[1]}, mode=RGB)")
        job["status"] = "done"

    def _comfy_wait(self, job: dict[str, Any], client_id: str, prompt_id: str) -> None:
        """Stream the render's progress; falls back to polling without a websocket client."""
        emit = lambda: self.emit("progress", {"id": job["id"], "progress": job["progress"], "result": job["result"]})  # noqa: E731
        try:
            import websocket  # the websocket-client package
        except ImportError:
            websocket = None
        if websocket is None:
            self.log(job, "[studio] websocket-client missing — progress will be coarse (install it with: pip install websocket-client)")
            while True:
                if job["status"] == "cancelling":
                    return
                history = self.comfy.history(prompt_id).get(prompt_id)
                if history is not None:
                    status = str((history.get("status") or {}).get("status_str", "")).lower()
                    if status == "error":
                        raise ValueError("ComfyUI reported an execution error")
                    if status in ("success", "interrupted"):
                        if status == "interrupted":
                            job["status"] = "cancelling"
                        return
                    job["progress"].update(stage="denoise", step=0, total=0)
                    emit()
                time.sleep(2.0)
        connection = websocket.create_connection(f"{self.comfy.ws_base()}/ws?clientId={client_id}",
                                                 timeout=15, enable_multithread=True)  # fmt: skip
        try:
            while True:
                if job["status"] == "cancelling":
                    return
                try:
                    frame = connection.recv()
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    continue
                if not isinstance(frame, str):
                    continue  # preview frames are binary
                message = json.loads(frame)
                kind, data = message.get("type"), message.get("data") or {}
                if data.get("prompt_id") != prompt_id:
                    continue
                if kind == "progress":
                    job["progress"].update(stage="denoise", step=data.get("value", 0), total=data.get("max", 0))
                    emit()
                elif kind == "executing":
                    if data.get("node") is None:
                        return
                    if data.get("node") == "decode":
                        job["progress"].update(stage="decode", step=0, total=0)
                        emit()
                elif kind == "execution_success":
                    return
                elif kind == "execution_interrupted":
                    job["status"] = "cancelling"
                    return
                elif kind == "execution_error":
                    raise ValueError(data.get("exception_message") or "ComfyUI reported an execution error")
        finally:
            connection.close()

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "qwen-image-studio"
    state: State
    runner: Runner
    allowed_hosts: ClassVar[set[str]] = set()

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _error(self, message: str, code: int = 400) -> None:
        self._json({"error": message, "message": message}, code)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def _guarded(self) -> bool:
        refusal = request_guard(self.command, self.path, self.headers, self.allowed_hosts)
        if refusal:
            self._error(refusal[1], refusal[0])
            return True
        return False

    def _route(self, handler: Callable[[str, dict[str, str]], Any]) -> None:
        if self._guarded():
            return
        url = urlparse(self.path)
        try:
            result = handler(url.path, {k: v[0] for k, v in parse_qs(url.query).items()})
            if result is not None:
                self._json(result)
        except (ValueError, KeyError) as exc:
            self._error(str(exc))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # never drop the connection without a response
            self._error(f"{type(exc).__name__}: {exc}", 500)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_PUT(self) -> None:
        if not self._guarded():
            self._error("not found", 404)

    do_PATCH = do_DELETE = do_PUT

    def do_GET(self) -> None:
        self._route(self._get)

    def do_POST(self) -> None:
        self._route(self._post)

    def _get(self, path: str, query: dict[str, str]) -> Any:
        state, session = self.state, self.state.session_name(query.get("session"))
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/") :])
        if path == "/api/events":
            return self._events()
        if path == "/api/config":
            return {"paths": state.paths_info(), "sessions": state.sessions(), "active": state.session_name(None),
                    "data_dir": str(state.data_dir.resolve()), "input_dir": str(state.input_dir.resolve()),
                    "output_dir": str(state.output_dir.resolve()),
                    "settings": (state.session(state.session_name(None)) or {}).get("settings") or {}}  # fmt: skip
        if path == "/api/inputs":
            return state.inputs(session)
        if path == "/api/inputs/all":
            return state.inputs_all()
        if path == "/api/takes":
            return state.takes(session)
        if path == "/api/gallery":
            return state.gallery_all()
        if path == "/api/queue":
            return self.runner.queue_state()
        if m := re.fullmatch(r"/api/assets/([0-9a-f]+)/thumb", path):
            found = state.thumb_bytes(m[1])
            if found is None:
                return self._error("not found", 404)
            return self._send(200, *found)
        if m := re.fullmatch(r"/api/assets/([0-9a-f]+)", path):
            found = state.asset_bytes(m[1])
            if found is None:
                return self._error("not found", 404)
            return self._send(200, *found)
        return self._error("not found", 404)

    def _post(self, path: str, query: dict[str, str]) -> Any:
        state = self.state
        if path == "/api/upload":
            original = Path(unquote(self.headers.get("X-Filename") or "upload")).name
            length = int(self.headers.get("Content-Length") or 0)
            result = state.upload(state.session_name(query.get("session")), original, self.rfile, length)
            self.runner.emit("inputs", {})
            return result
        body = self._body()
        session = state.session_name(body.get("session"))
        if path == "/api/render":
            return self.runner.submit({**body, "session": session})
        if path == "/api/cancel":
            return {"ok": self.runner.cancel(str(body.get("id")))}
        if path == "/api/paths":
            return state.set_paths(body.get("paths") or {})
        if path == "/api/session/activate":
            return state.activate(session)
        if path == "/api/session/save":
            state.save_settings(session, body.get("settings") or {})
            return {"ok": True}
        if path == "/api/session/rename":
            old = session
            result = state.rename(session, str(body.get("new_name", "")))
            with self.runner.cond:  # in-flight jobs keep logging under the new name
                for job in self.runner.jobs.values():
                    if job.get("session") == old:
                        job["session"] = result["name"]
            return result
        if path == "/api/session/delete":
            with self.runner.cond:
                jobs = [j["id"] for j in self.runner.jobs.values()
                        if j.get("session") == session and j.get("status") in ("queued", "running")]
            for job_id in jobs:
                self.runner.cancel(job_id)
            return state.delete_session(session)
        if path == "/api/inputs/delete":
            state.delete_input(session, str(body.get("name")))
            return {"ok": True}
        if path == "/api/inputs/attach":
            return state.attach_input(session, str(body["asset_id"]))
        if path == "/api/inputs/delete-asset":
            state.delete_input_asset(str(body["asset_id"]))
            return {"ok": True}
        if path == "/api/inputs/clear":
            state.clear_inputs(session)
            return {"ok": True}
        if path == "/api/reveal":
            state.reveal_dir(str(body.get("target") or ""))
            return {"ok": True}
        if path == "/api/takes/delete":
            state.delete_take(str(body["id"]))
            return {"ok": True}
        if path == "/api/takes/use":
            return state.take_as_input(session, str(body["id"]))
        if path == "/api/takes/reuse":
            return state.reuse_take(session, str(body.get("take_id") or body.get("id") or ""))
        return self._error("not found", 404)

    def _static(self, rel: str) -> None:
        target = (STATIC_DIR / rel).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            return self._error("not found", 404)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        return self._send(200, target.read_bytes(), ctype)

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = self.runner.subscribe()
        try:
            self.wfile.write(f"data: {json.dumps({'type': 'queue', 'data': self.runner.queue_state()})}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.runner.unsubscribe(q)


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


#: Where the studio kept everything before images moved to ``~/Qwen Image Studio``.
LEGACY_DATA_DIRS = (Path("~/Library/Application Support/Qwen Image Studio").expanduser(),)


def migrate_legacy_data(new_dir: Path) -> None:
    """One-time move of the old Application Support store into the user folder.

    Only when the new folder has no store.json yet; a target that already exists
    (a fresh server-env, say) is left alone. The emptied legacy folder is removed.
    """
    if (new_dir / "store.json").exists():
        return
    new_dir.mkdir(parents=True, exist_ok=True)
    for legacy in LEGACY_DATA_DIRS:
        if not legacy.is_dir() or legacy.resolve() == new_dir.resolve():
            continue
        print(f"[studio] moving the old data from {legacy} to {new_dir}", flush=True)
        for child in list(legacy.iterdir()):
            target = new_dir / child.name
            if target.exists():
                continue
            try:
                shutil.move(str(child), str(target))
            except OSError as exc:
                print(f"[studio] could not move {child.name}: {exc}", flush=True)
        with contextlib.suppress(OSError):
            legacy.rmdir()  # gone only when everything above moved out


def watch_stdin() -> None:
    """Exit when the launching app goes away: stdin's pipe closes with it."""

    def follow() -> None:
        try:
            while sys.stdin.buffer.read(4096):
                pass
        except Exception:
            pass
        terminate()

    threading.Thread(target=follow, daemon=True).start()


def terminate(_: Any = None, __: Any = None) -> None:
    """The one exit path: every render and the ComfyUI we started go first."""
    runner = getattr(Handler, "runner", None)
    if runner is not None:
        if runner.comfy is not None:
            with contextlib.suppress(Exception):
                runner.comfy.shutdown()
        if runner.proc and runner.proc.poll() is None:
            with contextlib.suppress(Exception):
                os.killpg(runner.proc.pid, signal.SIGTERM)
    os._exit(0)


def install_term_handlers() -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, terminate)
    atexit.register(terminate)


def main() -> None:
    env = os.environ.get
    parser = argparse.ArgumentParser(description="qwen image studio — standalone edition")

    parser.add_argument("--comfyui", default=env("QWEN_COMFYUI", ""),
                        help="ComfyUI: an install directory (started headless) or an http URL (reused)")
    parser.add_argument("--data-dir", default=env("QWEN_STUDIO_DATA",
                        "~/Qwen Image Studio"), help="where sessions, assets and takes live")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8730)
    parser.add_argument("--allow-host", default="", help="extra Host names to accept, comma-separated")
    parser.add_argument("--exit-on-stdin-eof", action="store_true", help="exit when the parent app closes stdin")
    args = parser.parse_args()

    if args.exit_on_stdin_eof and not sys.stdin.isatty():
        watch_stdin()

    data_dir = Path(args.data_dir).expanduser()
    if args.data_dir == "~/Qwen Image Studio" or data_dir.name == "Qwen Image Studio":
        migrate_legacy_data(data_dir)

    state = State({"comfyui": args.comfyui}, data_dir)
    Handler.state = state
    Handler.runner = Runner(state)
    Handler.allowed_hosts = {h.strip().lower() for h in [args.host, *args.allow_host.split(",")] if h.strip()}
    install_term_handlers()
    print(f"qwen image studio on http://{args.host}:{args.port}", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        StudioServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
