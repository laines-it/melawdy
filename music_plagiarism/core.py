"""Standalone adapter to Mippia's original four-bar similarity algorithm.

Copyright (c) 2026 MeLawDy contributors. GPL-3.0.
No imports from the website, database, or its ML package.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "mippia"
COMMIT = "109c703242546e88914d8dbf04311e06bc3113cb"
PIPELINE_VERSION = "cpu-adapter-v2"


def upstream():
    """Import only the original comparator; audio dependencies stay optional."""
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    import compare
    import compare_utils
    import torch
    return compare, compare_utils, torch


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: expected a finite number")
    return float(value)


def load_info(path: Path) -> dict:
    """Read plain JSON, never deserialize arbitrary Python objects/jsonpickle."""
    with path.open(encoding="utf-8") as stream:
        info = json.load(stream)
    if not isinstance(info, dict):
        raise ValueError(f"{path}: expected a JSON object")
    bpm = number(info.get("bpm"), "bpm")
    if bpm <= 0:
        raise ValueError("bpm must be positive")
    if info.get("rhythm") != 4:
        raise ValueError("This comparator supports 4/4 only; upstream piano rolls assume 48 steps/bar")
    downbeat = number(info.get("downbeat_start"), "downbeat_start")
    beats = info.get("beat_times")
    if not isinstance(beats, list) or len(beats) < 2:
        raise ValueError("beat_times must contain at least two timestamps")
    beats = [number(x, "beat_times") for x in beats]
    if any(b <= a for a, b in zip(beats, beats[1:])):
        raise ValueError("beat_times must be strictly increasing")
    if downbeat < 0 or downbeat > beats[-1]:
        raise ValueError("downbeat_start must lie within the track")
    vocal = info.get("vocal_info") or {}
    if not isinstance(vocal, dict):
        raise ValueError("vocal_info must be an object keyed by bar number")
    for bar, notes in vocal.items():
        if not str(bar).isdigit() or not isinstance(notes, list):
            raise ValueError("vocal_info: expected nonnegative bar numbers and lists of notes")
        for note in notes:
            if not isinstance(note, list) or len(note) != 6:
                raise ValueError("Each note must contain [start_seconds, end_seconds, pitch, velocity, start_step, end_step]")
            values = [number(x, "vocal note") for x in note]
            if (values[0] < 0 or values[1] < values[0] or not 0 <= values[2] <= 127
                    or values[2] != int(values[2]) or not 0 <= values[4] < 48
                    or values[5] < values[4]):
                raise ValueError("Invalid note time, MIDI pitch, or quantized position")
    info.update(bpm=bpm, beat_times=beats, downbeat_start=downbeat, vocal_info=vocal)
    info.setdefault("title", path.stem)
    return info


def segments(info: dict):
    _, utils, torch = upstream()
    if not any(info["vocal_info"].values()):
        return []
    bar_seconds = (info["beat_times"][1] - info["beat_times"][0]) * 4
    if info["beat_times"][-1] - info["downbeat_start"] < bar_seconds * 4:
        return []
    rolls, starts, points = utils.infos_to_pianorolls(info, True)
    result = []
    for index, roll in rolls["vocal"].items():
        start = info["downbeat_start"] + bar_seconds * starts[index]
        end = start + bar_seconds * 4
        # Do not compare padded fragments extending beyond the actual recording.
        if end > info["beat_times"][-1] + 1e-6:
            continue
        notes = utils.remove_1(points["vocal"][index])
        if len(notes) < 5:
            continue
        image = torch.as_tensor(roll.T.copy()).unsqueeze(0).float()
        result.append((utils.quantize_image(image).squeeze(0), notes, start, end))
    return result


def compare_infos(query_path: Path, reference_paths: list[Path], *, top: int = 5,
                  batch_size: int = 4, threads: int = 1) -> dict:
    compare, _, torch = upstream()
    torch.set_num_threads(threads)
    query = load_info(query_path)
    query_segments = segments(query)
    output = {
        "algorithm": "Mippia vocal segment similarity, 4 bars",
        "upstream_commit": COMMIT,
        "adapter_version": PIPELINE_VERSION,
        "scope": "Only the supplied reference files are searched",
        "notice": "Similarity scores are not probabilities or legal conclusions about plagiarism",
        "query": {"title": query["title"], "path": str(query_path), "segments": len(query_segments)},
        "status": "ok" if query_segments else "no_query_segments",
        "matches": [],
        "skipped": [],
    }
    for path in reference_paths:
        reference = load_info(path)
        refs = segments(reference)
        if not refs:
            output["skipped"].append({"path": str(path), "reason": "No usable four-bar vocal segments"})
            continue
        if not query_segments:
            continue
        best = []
        # Bound tensor allocation independently of song/catalog length.
        with torch.inference_mode():
            for qi in range(0, len(query_segments), batch_size):
                qs = query_segments[qi:qi + batch_size]
                for ri in range(0, len(refs), batch_size):
                    rs = refs[ri:ri + batch_size]
                    scores = compare.calculate_metric_optimized(
                        torch.stack([s[0] for s in qs])[:, None],
                        torch.stack([s[0] for s in rs])[None],
                        [s[1] for s in qs], [s[1] for s in rs],
                        torch.full((len(qs), 1), query["bpm"]),
                        torch.full((1, len(rs)), reference["bpm"]), "cpu",
                    )
                    if not torch.isfinite(scores).all():
                        raise ValueError("Upstream comparator returned non-finite scores")
                    for i, q in enumerate(qs):
                        for j, r in enumerate(rs):
                            best.append({"score": round(float(scores[i, j]), 6),
                                         "query_start": q[2], "query_end": q[3],
                                         "reference_start": r[2], "reference_end": r[3]})
                    best = sorted(best, key=lambda x: x["score"], reverse=True)[:top]
        output["matches"].append({"title": reference["title"], "path": str(path),
                                   "score": best[0]["score"], "segments": len(refs), "top_segments": best})
    output["matches"].sort(key=lambda m: m["score"], reverse=True)
    if query_segments and not output["matches"]:
        output["status"] = "no_reference_segments"
    return output


def choose_device(requested: str) -> str:
    import torch
    available = torch.cuda.is_available()
    if requested == "cuda" and not available:
        raise ValueError("CUDA is not available. Use --device cpu (the Docker image is CPU-only)")
    return "cuda" if requested == "cuda" or requested == "auto" and available else "cpu"


def transcribe(path: Path, cache_dir: Path, *, device: str = "cpu", threads: int = 1,
               separation_segment: int = 2) -> Path:
    if not path.is_file():
        raise ValueError(f"Audio file does not exist: {path}")
    if not shutil.which("ffmpeg"):
        raise ValueError("ffmpeg is missing. Use the standalone Docker image or install ffmpeg")
    options = f"{PIPELINE_VERSION}:{device}:{separation_segment}"
    digest = hashlib.sha256((options + file_hash(path)).encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{digest}.json"
    if cached.exists():
        load_info(cached)
        print(f"Using cached transcription: {path.name}", file=sys.stderr)
        return cached
    manifest = json.loads((ROOT / "UPSTREAM.json").read_text())
    for item in manifest["weights"]:
        model = VENDOR / item["path"]
        if not model.is_file() or file_hash(model) != item["sha256"]:
            raise ValueError("Missing or invalid model checkpoint. Run: python run.py weights")
    upstream()
    import torch
    device = choose_device(device)
    torch.set_num_threads(threads)
    os.environ["MIPPIA_DEVICE"] = device
    os.environ["MIPPIA_DEMUCS_SEGMENT"] = str(separation_segment)
    # This CLI is single-process/single-job; upstream model globals use this device.
    import segment_transcription as module
    module.device = device
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="mippia-", dir=cache_dir) as work:
        work = Path(work).resolve()
        audio = work / "input.wav"
        converted = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(path), "-vn", "-ar", "44100", "-ac", "2", str(audio),
        ], capture_output=True, text=True)
        if converted.returncode:
            raise ValueError(f"ffmpeg could not decode {path.name}: {converted.stderr.strip()}")
        print(f"Transcribing {path.name} on {device}; this may take several minutes", file=sys.stderr)
        try:
            os.chdir(work)
            result = Path(module.segment_transcription(str(audio)))
            data = load_info(result)
        finally:
            os.chdir(previous)
        data.update(title=path.stem, source_audio=str(path), source_sha256=file_hash(path),
                    upstream_commit=COMMIT, adapter_version=PIPELINE_VERSION)
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(cached)
    return cached


def diagnostics(comparator_only: bool = False) -> dict:
    dependencies = ["torch", "numpy", "pandas", "jsonpickle", "tqdm"]
    if not comparator_only:
        dependencies += ["torchaudio", "torchvision", "librosa", "soundfile", "demucs", "timm", "madmom", "pretty_midi", "mido"]
    checks = {name: importlib.util.find_spec(name) is not None for name in dependencies}
    if not comparator_only:
        checks["ffmpeg"] = shutil.which("ffmpeg") is not None
        spec = importlib.util.find_spec("madmom")
        checks["madmom_models_metadata"] = bool(spec and spec.origin
            and (Path(spec.origin).parent / "models/__init__.py").is_file())
        manifest = json.loads((ROOT / "UPSTREAM.json").read_text())
        for item in manifest["weights"]:
            path = VENDOR / item["path"]
            checks[item["path"]] = path.is_file() and file_hash(path) == item["sha256"]
    return {"ready": all(checks.values()), "python": sys.version.split()[0],
            "upstream_commit": COMMIT, "checks": checks}
