"""Standalone CLEWS fragment search used by the accompanying Colab notebook.

The upstream model is downloaded separately; no website imports are used.
"""
import argparse
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import torch
from omegaconf import OmegaConf

SCHEMA = "melawdy-clews-colab-v1"
REPO_COMMIT = "517de18676e08799b51c6597a0f2af61f7a70799"
EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".webm"}
FIELDS = ["reference", "distance", "query_start", "query_end", "reference_start", "reference_end"]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decode(path, sr, max_seconds):
    with tempfile.TemporaryFile() as output:
        proc = subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
            "-t", str(max_seconds + 1), "-vn", "-ac", "1", "-ar", str(sr),
            "-f", "f32le", "pipe:1",
        ], stdout=output, stderr=subprocess.PIPE, timeout=180)
        if proc.returncode:
            raise ValueError(proc.stderr.decode(errors="replace")[-1500:])
        output.seek(0)
        audio = np.frombuffer(output.read(), dtype="<f4").copy()
    if len(audio) > max_seconds * sr:
        raise ValueError(f"Запись длиннее {max_seconds} секунд. Загрузите более короткий файл.")
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError("Пустое или повреждённое аудио.")
    return audio


def load_model(repo, checkpoint, device):
    sys.path.insert(0, str(repo))
    conf = OmegaConf.load(checkpoint.parent / "configuration.yaml")
    if conf.model.name != "clews":
        raise ValueError("Выбран checkpoint другой архитектуры; требуется CLEWS.")
    module = importlib.import_module("models.clews")
    model = module.Model(conf.model, sr=int(conf.data.samplerate))
    # Only the checksum-verified official Zenodo checkpoint is used by the notebook.
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"], strict=True)
    del state
    model.eval().to(device)
    return model, conf


def extract(path, model, cache_dir, model_hash, config_hash, window, hop, batch_size, device, max_seconds):
    audio_hash = sha256(path)
    identity = dict(schema=SCHEMA, audio_sha256=audio_hash, model_sha256=model_hash,
                    repo_commit=REPO_COMMIT, configuration_sha256=config_hash, window=window, hop=hop,
                    samplerate=model.sr, min_rms=0.0001, max_seconds=max_seconds)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache_path = cache_dir / (key + ".npz")
    if cache_path.exists():
        with np.load(cache_path, allow_pickle=False) as saved:
            return dict(path=str(path), sha256=audio_hash, duration=float(saved["duration"]),
                        starts=saved["starts"], vectors=saved["vectors"], cache=str(cache_path))
    audio = decode(path, model.sr, max_seconds)
    nwin = int(round(window * model.sr))
    nhop = int(round(hop * model.sr))
    if len(audio) < nwin:
        raise ValueError(f"Нужно не менее {window:g} секунд аудио; короткие записи не дополняются повторением.")
    positions = list(range(0, len(audio) - nwin + 1, nhop))
    if positions[-1] != len(audio) - nwin:
        positions.append(len(audio) - nwin)
    positions = [p for p in positions if np.sqrt(np.mean(audio[p:p+nwin].astype(np.float64)**2)) >= 0.0001]
    if not positions:
        raise ValueError("Все окна слишком тихие: анализ не выполнен.")
    vectors = []
    with torch.inference_mode():
        for offset in range(0, len(positions), batch_size):
            chunk = positions[offset:offset + batch_size]
            samples = np.stack([audio[p:p+nwin] for p in chunk])
            z = model(torch.from_numpy(samples).to(device), shingle_len=window, shingle_hop=window)
            z = z[:, 0, :].float().cpu().numpy()
            if not np.isfinite(z).all():
                raise ValueError("Модель вернула некорректные векторы.")
            vectors.append(z)
            print(f"  {path.name}: {min(offset + batch_size, len(positions))}/{len(positions)} окон", flush=True)
    result = dict(path=str(path), sha256=audio_hash, duration=len(audio)/model.sr,
                  starts=np.asarray(positions, dtype=np.float64)/model.sr,
                  vectors=np.concatenate(vectors), cache=str(cache_path))
    temporary = cache_path.with_suffix(".tmp.npz")
    np.savez_compressed(temporary, vectors=result["vectors"], starts=result["starts"], duration=result["duration"])
    os.replace(temporary, cache_path)
    return result


def find_matches(query, ref, window, count):
    # Same segment metric as CLEWS: squared Euclidean distance / embedding dimension.
    q = torch.from_numpy(query["vectors"])
    r = torch.from_numpy(ref["vectors"])
    from lib.tensor_ops import pairwise_distance_matrix
    distances = pairwise_distance_matrix(q, r, mode="nsqeuc").numpy()
    available = distances.copy()
    matches = []
    for _ in range(count):
        index = np.unravel_index(np.argmin(available), available.shape)
        score = float(available[index])
        if not math.isfinite(score):
            break
        qs, rs = float(query["starts"][index[0]]), float(ref["starts"][index[1]])
        matches.append(dict(reference=ref["path"], distance=score,
                            query_start=qs, query_end=qs+window,
                            reference_start=rs, reference_end=rs+window))
        # Suppress near-duplicate windows in both recordings, retaining separate repetitions.
        qm = np.abs(query["starts"] - qs) < window * 0.75
        rm = np.abs(ref["starts"] - rs) < window * 0.75
        available[np.ix_(qm, rm)] = np.inf
    return matches, distances


def main():
    parser = argparse.ArgumentParser()
    for name in ("repo", "checkpoint", "query", "references", "cache", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--hop", type=float, default=5)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--matches-per-track", type=int, default=3)
    parser.add_argument("--max-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.hop <= 0 or args.batch_size < 1 or args.matches_per_track < 1 or args.max_seconds < 20:
        parser.error("Некорректные параметры поиска.")
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.query.is_file():
        raise ValueError("Выберите исследуемый файл в ячейке загрузки.")
    refs = sorted(p for p in args.references.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)
    if not refs:
        raise ValueError("Загрузите хотя бы одну запись для сравнения.")
    torch.manual_seed(43)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Устройство:", device, flush=True)
    if device == "cpu":
        print("GPU отсутствует; обработка на CPU может быть медленной.", flush=True)
    model_hash = sha256(args.checkpoint)
    config_hash = sha256(args.checkpoint.parent / "configuration.yaml")
    model, conf = load_model(args.repo, args.checkpoint, device)
    window = float(conf.model.shingling.len)
    if args.hop > window:
        raise ValueError("Шаг больше окна создаёт пропуски; уменьшите hop.")
    def embed(path):
        return extract(path, model, args.cache, model_hash, config_hash, window, args.hop,
                       args.batch_size, device, args.max_seconds)
    query = embed(args.query)
    matches, errors, excluded, manifest = [], [], [], []
    best_matrix, best_score = None, float("inf")
    for path in refs:
        print("Сравнение:", path.name, flush=True)
        try:
            if sha256(path) == query["sha256"]:
                excluded.append(dict(path=str(path), reason="Файл идентичен исследуемому по SHA-256"))
                continue
            ref = embed(path)
            found, matrix = find_matches(query, ref, window, args.matches_per_track)
            matches.extend(found)
            manifest.append({k: ref[k] for k in ("path", "sha256", "duration", "cache")})
            if found and found[0]["distance"] < best_score:
                best_score = found[0]["distance"]
                best_matrix = dict(distances=matrix, query_starts=query["starts"], reference_starts=ref["starts"])
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(dict(path=str(path), error=str(exc)))
            print("Не обработан:", path.name, str(exc), flush=True)
            if device == "cuda":
                torch.cuda.empty_cache()
    matches.sort(key=lambda m: m["distance"])
    report = dict(schema=SCHEMA, status="ranked_candidates" if matches else "analysis_not_completed",
                  notice="Это ранжирование сходства, не процент плагиата. Ближайший кандидат может быть несходным.",
                  repo_commit=REPO_COMMIT, checkpoint_sha256=model_hash, configuration_sha256=config_hash, device=device,
                  metric="squared_euclidean_div_embedding_dimension", window_seconds=window,
                  hop_seconds=args.hop, query={k: query[k] for k in ("path", "sha256", "duration", "cache")},
                  references=manifest, errors=errors, excluded=excluded, matches=matches)
    (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.output / "matches.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(matches)
    if best_matrix is not None:
        np.savez_compressed(args.output / "best_match_matrix.npz", **best_matrix)
    elif (args.output / "best_match_matrix.npz").exists():
        (args.output / "best_match_matrix.npz").unlink()
    print(f"Готово: {len(manifest)} записей обработано; {len(errors)} ошибок; {len(excluded)} исключено.", flush=True)


if __name__ == "__main__":
    main()
