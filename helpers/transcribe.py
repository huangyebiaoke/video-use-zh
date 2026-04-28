"""Transcribe a video with FunASR (local, no API key needed).

Extracts mono 16kHz audio via ffmpeg, runs FunASR paraformer-zh with VAD,
punctuation restoration, and optional speaker diarization. Writes output in
a Scribe-compatible JSON format so downstream tools (pack_transcripts.py,
render.py) work unchanged.

Cached: if the output file already exists, the transcription is skipped.

Usage:
    python helpers/transcribe.py <video_path>
    python helpers/transcribe.py <video_path> --edit-dir /custom/edit
    python helpers/transcribe.py <video_path> --num-speakers 2
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def extract_audio(video_path: Path, dest: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def funasr_transcribe(
    audio_path: Path,
    num_speakers: int | None = None,
) -> dict:
    """Run FunASR transcription and return Scribe-compatible JSON.

    Uses the paraformer-zh model with VAD and punctuation restoration.
    Speaker diarization is supported via cam++ if num_speakers is provided.

    Returns a dict in Scribe format:
    {"words": [{"type": "word", "text": "...", "start": 0.0, "end": 0.1, "speaker_id": "speaker_0"}, ...]}
    """
    from funasr import AutoModel

    model_kwargs: dict = {
        "model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
        "punc_model": "ct-punc",
        "device": "mps",
    }

    # Check if we have enough memory for diarization
    use_diarization = num_speakers is not None and num_speakers > 0
    if use_diarization:
        model_kwargs["spk_model"] = "cam++"

    model = AutoModel(**model_kwargs, disable_update=True)

    result = model.generate(
        input=str(audio_path),
        batch_size_s=300,
        hotword="",
    )

    # Parse result into Scribe-compatible format
    words: list[dict] = []

    if isinstance(result, list):
        result = result[0] if result else {}

    # FunASR paraformer returns: {"text": "...", "timestamp": [[start_ms, end_ms, word], ...], ...}
    timestamp = result.get("timestamp", [])
    text_full = result.get("text", "")

    # Speaker info if diarization was used
    speaker_list = result.get("spk_list", [])
    # spk_info is a list of [start_ms, end_ms, speaker_id] per utterance
    spk_info = result.get("spk_info", [])

    # Build word entries from timestamp
    prev_end_ms: int | None = None
    current_spk: str = "speaker_0"

    # Build a speaker map: time range -> speaker_id
    speaker_segments: list[tuple[int, int, str]] = []
    for seg in spk_info:
        if len(seg) >= 3:
            speaker_segments.append((int(seg[0]), int(seg[1]), f"speaker_{seg[2]}"))

    def get_speaker_at(time_ms: int) -> str:
        for seg_start, seg_end, spk_id in speaker_segments:
            if seg_start <= time_ms <= seg_end:
                return spk_id
        # Fallback: find closest segment
        if not speaker_segments:
            return "speaker_0"
        closest = min(speaker_segments, key=lambda s: abs(s[0] - time_ms))
        return closest[2]

    # paraformer-zh returns timestamp as [[start_ms, end_ms], ...] (2-element)
    # without embedded word text. The text field contains space-separated chars.
    # Map each timestamp entry to its corresponding character.
    text_chars = text_full.replace(" ", "").replace("\u3000", "")

    for i, entry in enumerate(timestamp):
        if len(entry) < 2:
            continue
        start_ms, end_ms = int(entry[0]), int(entry[1])

        # Get character for this timestamp
        word_text = text_chars[i] if i < len(text_chars) else ""

        # Add spacing gap if there's a significant pause (> 200ms)
        if prev_end_ms is not None:
            gap = start_ms - prev_end_ms
            if gap > 200:
                words.append({
                    "type": "spacing",
                    "start": prev_end_ms / 1000.0,
                    "end": start_ms / 1000.0,
                })

        # Determine speaker
        speaker_id = get_speaker_at(start_ms)

        # Detect audio events (parenthesized text like laughs, sighs)
        clean_text = word_text.strip()
        if clean_text.startswith("(") and clean_text.endswith(")"):
            words.append({
                "type": "audio_event",
                "text": clean_text.lstrip("(").rstrip(")"),
                "start": start_ms / 1000.0,
                "end": end_ms / 1000.0,
                "speaker_id": speaker_id,
            })
        else:
            words.append({
                "type": "word",
                "text": clean_text,
                "start": start_ms / 1000.0,
                "end": end_ms / 1000.0,
                "speaker_id": speaker_id,
            })

        prev_end_ms = end_ms

    # Build final output matching Scribe format
    # Add word count info
    word_count = sum(1 for w in words if w.get("type") == "word")

    return {
        "text": text_full,
        "words": words,
        "word_count": word_count,
        "source": "funasr",
        "model": "paraformer-zh",
    }


def transcribe_one(
    video: Path,
    edit_dir: Path,
    language: str | None = None,  # ignored, kept for API compatibility
    num_speakers: int | None = None,
    verbose: bool = True,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists.
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    if verbose:
        print(f"  extracting audio from {video.name}", flush=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.wav"
        extract_audio(video, audio)
        size_mb = audio.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"  transcribing {video.stem}.wav ({size_mb:.1f} MB) with FunASR", flush=True)
        payload = funasr_transcribe(audio, num_speakers)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s")
        word_count = payload.get("word_count", len([w for w in payload.get("words", []) if w.get("type") == "word"]))
        print(f"    words: {word_count}")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video with FunASR")
    ap.add_argument("video", type=Path, help="Path to video file")
    ap.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit output directory (default: <video_parent>/edit)",
    )
    ap.add_argument(
        "--language",
        type=str,
        default=None,
        help="Ignored (kept for API compatibility). FunASR auto-detects.",
    )
    ap.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Optional number of speakers when known. Enables speaker diarization.",
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    transcribe_one(
        video=video,
        edit_dir=edit_dir,
        language=args.language,
        num_speakers=args.num_speakers,
    )


if __name__ == "__main__":
    main()
