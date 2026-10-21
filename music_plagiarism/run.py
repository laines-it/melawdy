#!/usr/bin/env python3
"""Manual test CLI, independent of MeLawDy. GPL-3.0."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import html
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import quote

from core import ROOT, VENDOR, compare_infos, diagnostics, transcribe


def positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return result


def segment_seconds(value: str) -> int:
    result = int(value)
    if not 1 <= result <= 7:
        raise argparse.ArgumentTypeError("must be an integer between 1 and 7 seconds")
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Отдельная проверка алгоритма Mippia. Данные обрабатываются локально.")
    p.add_argument("--debug", action="store_true", help="Show a full traceback on error")
    commands = p.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Check dependencies and checkpoint hashes")
    doctor.add_argument("--comparator-only", action="store_true")
    commands.add_parser("weights", help="Download/verify the two pinned Mippia checkpoints")
    examples = commands.add_parser("examples", help="Generate synthetic note examples; no audio/ML dependencies")
    examples.add_argument("--directory", type=Path, default=ROOT / "examples")
    transcription = commands.add_parser("transcribe", help="Extract vocal notes from one audio file")
    transcription.add_argument("audio", type=Path)
    transcription.add_argument("--output", required=True, type=Path)
    for name in ("compare", "compare-json"):
        command = commands.add_parser(name, help="Compare audio files" if name == "compare" else "Compare saved Mippia note JSON files without audio models")
        command.add_argument("query", type=Path)
        command.add_argument("--reference", type=Path, action="append", required=True,
                             help="Reference file; repeat to search several files")
        command.add_argument("--top", type=positive, default=5, help="Best segment pairs per reference")
        command.add_argument("--batch-size", type=positive, default=4)
        command.add_argument("--output", type=Path, default=Path("results/result.json"))
        command.add_argument("--html", type=Path, help="HTML report (defaults to the JSON path with .html extension)")
    for command in (transcription, commands.choices["compare"]):
        command.add_argument("--device", choices=["cpu", "auto", "cuda"], default="cpu")
        command.add_argument("--separation-segment", type=segment_seconds, default=2,
                             help="Demucs window in seconds (default 2; larger values need more RAM)")
        command.add_argument("--cache-dir", type=Path, default=Path(".cache/transcriptions"))
    for command in (transcription, commands.choices["compare"], commands.choices["compare-json"]):
        command.add_argument("--threads", type=positive, default=1)
    return p


def generate_examples(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    # Eight bars, each with four quarter notes. This is deliberately synthetic.
    phrase = [60, 62, 64, 67, 65, 64, 62, 60, 67, 69, 71, 72, 71, 67, 64, 62]
    for name, pitches, bpm in (
        ("query", phrase, 120), ("same_melody", phrase, 120),
        ("octave_up", [p + 12 for p in phrase], 120),
        ("different", [61, 63, 66, 68] * 4, 120),
        ("no_notes", [], 120),
    ):
        bars = {}
        for bar in range(8):
            notes = []
            for beat in range(4):
                if pitches:
                    start = (bar * 4 + beat) * 60 / bpm
                    notes.append([start, start + 0.4, pitches[(bar * 4 + beat) % len(pitches)],
                                  100, beat * 12, beat * 12 + 9])
            bars[str(bar)] = notes
        data = {"title": name, "bpm": bpm, "rhythm": 4, "downbeat_start": 0.0,
                "beat_times": [i * 60 / bpm for i in range(33)], "vocal_info": bars}
        target = directory / f"{name}.json"
        if target.exists():
            # Preserve any user-edited fixture instead of silently replacing it.
            continue
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Synthetic examples: {directory.resolve()}")


def write_html(report: dict, path: Path) -> None:
    escape = lambda value: html.escape(str(value), quote=True)
    sections = []
    for match in report["matches"]:
        rows = []
        for pair in match["top_segments"]:
            rows.append("<tr>" + "".join(f"<td>{value}</td>" for value in (
                f"{pair['score']:.4f}", f"{pair['query_start']:.2f}–{pair['query_end']:.2f}",
                f"{pair['reference_start']:.2f}–{pair['reference_end']:.2f}",
            )) + "</tr>")
        sections.append(f"<section><h2>{escape(match['title'])}</h2><p>Наибольшее сходство: {match['score']:.4f} из 1</p>"
                        "<table><thead><tr><th>Сходство</th><th>Запрос, секунды</th><th>Эталон, секунды</th></tr></thead>"
                        f"<tbody>{''.join(rows)}</tbody></table></section>")
    players = []
    for label, audio in report.get("audio_files", {}).items():
        relative = os.path.relpath(audio, path.parent)
        players.append(f'<p>{escape(label)}</p><audio controls preload="metadata" src="{escape(quote(relative))}"></audio>')
    page = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Проверка музыкальных совпадений — Mippia</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 20px;color:#20202b}
section{border:1px solid #ddd;padding:20px;margin:20px 0;border-radius:12px}table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px;border-bottom:1px solid #ddd}audio{width:100%}small{color:#555}</style>
"""
    page += f"<h1>Проверка: {escape(report['query']['title'])}</h1><p>Статус: {escape(report['status'])}</p>"
    page += "<p>Сравниваются только указанные эталонные файлы. Баллы показывают сходство вокальных фрагментов; это не вероятность плагиата.</p>"
    page += "".join(players + sections)
    if not sections:
        page += "<p>Нет пригодных для сравнения фрагментов. Нужны вокальные ноты и минимум четыре полных такта с запасом по длительности.</p>"
    for skipped in report["skipped"]:
        page += f"<p>Пропущен: {escape(skipped['path'])} — {escape(skipped['reason'])}</p>"
    page += f"<small>Код Mippia: {escape(report['upstream_commit'])}. Модель: {escape(report['algorithm'])}.</small></html>"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = diagnostics(args.comparator_only)
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 1
        if args.command == "weights":
            from download_weights import download
            download()
            return 0
        if args.command == "examples":
            generate_examples(args.directory)
            return 0
        if args.command == "transcribe":
            output = args.output.resolve()
            if output == args.audio.resolve():
                raise ValueError("Transcription output must not overwrite the input audio")
            with redirect_stdout(sys.stderr):
                cached = transcribe(args.audio.resolve(), args.cache_dir.resolve(), device=args.device,
                                    threads=args.threads, separation_segment=args.separation_segment)
            output.parent.mkdir(parents=True, exist_ok=True)
            if cached != output:
                shutil.copyfile(cached, output)
            print(f"Transcription: {output}")
            return 0
        paths = [args.query.resolve(), *[p.resolve() for p in args.reference]]
        for path in paths:
            if not path.is_file():
                raise ValueError(f"File does not exist: {path}")
        audio_files = {}
        with redirect_stdout(sys.stderr):
            if args.command == "compare":
                audio_files = {f"Запрос: {paths[0].name}": str(paths[0])}
                audio_files.update({f"Эталон: {p.name}": str(p) for p in paths[1:]})
                paths = [transcribe(p, args.cache_dir.resolve(), device=args.device, threads=args.threads,
                                    separation_segment=args.separation_segment) for p in paths]
            result = compare_infos(paths[0], paths[1:], top=args.top, batch_size=args.batch_size, threads=args.threads)
        result["audio_files"] = audio_files
        output = args.output.resolve()
        html_path = (args.html or output.with_suffix(".html")).resolve()
        if output == html_path or output in paths or html_path in paths:
            raise ValueError("Report files must differ from each other and from the input files")
        if str(output) in audio_files.values() or str(html_path) in audio_files.values():
            raise ValueError("Report files must not overwrite input audio")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        write_html(result, html_path)
        print(f"Status: {result['status']}")
        for match in result["matches"]:
            pair = match["top_segments"][0]
            print(f"{match['score']:.4f}  {match['title']}  input {pair['query_start']:.2f}–{pair['query_end']:.2f}s"
                  f" ↔ reference {pair['reference_start']:.2f}–{pair['reference_end']:.2f}s")
        print(f"JSON: {output}\nHTML: {html_path}")
        return 0
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        if args.debug:
            raise
        print(f"Error: {exc}\nRun 'python run.py doctor' to check the standalone environment.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
