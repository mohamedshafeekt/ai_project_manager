"""
Meeting Ingestion Connector (Teams / VTT / JSON / Raw Text)
Normalizes transcripts into numbered lines with speaker and timestamp attribution
so every downstream draft can cite exact line numbers (PRD Feature 1 & Principle 5).
"""

import json
import re
from typing import Any


def parse_transcript(raw_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parses a transcript string (VTT, JSON, or plain speaker lines) into:
    - lines: [{"line_number": 1, "speaker": "Alice", "timestamp": "00:01:12", "text": "..."}]
    - attendees: sorted unique list of speakers
    """
    cleaned = raw_text.strip()
    if not cleaned:
        return [], []

    # 1. Try JSON format (e.g., list of {"speaker": ..., "text": ...})
    if cleaned.startswith("[") or cleaned.startswith("{"):
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "lines" in data:
                data = data["lines"]
            if isinstance(data, list):
                lines = []
                speakers = set()
                for idx, item in enumerate(data, start=1):
                    speaker = str(item.get("speaker", "Unknown")).strip()
                    text = str(item.get("text", "")).strip()
                    ts = str(item.get("timestamp", "")).strip()
                    if text:
                        lines.append({
                            "line_number": idx,
                            "speaker": speaker,
                            "timestamp": ts,
                            "text": text,
                        })
                        if speaker and speaker != "Unknown":
                            speakers.add(speaker)
                return lines, sorted(list(speakers))
        except json.JSONDecodeError:
            pass

    # 2. Try WebVTT format (Teams standard export)
    if cleaned.startswith("WEBVTT"):
        return _parse_vtt(cleaned)

    # 3. Standard line-by-line parsing:
    # Supports: "[00:04:12] Alice: text", "04:12 - Alice: text", or "Alice: text"
    lines = []
    speakers = set()
    line_num = 1

    pattern = re.compile(
        r"^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*)?([A-Za-z][A-Za-z0-9 ._-]{0,40}):\s*(.+)$"
    )

    for raw_line in cleaned.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        match = pattern.match(raw_line)
        if match:
            ts = (match.group(1) or "").strip()
            speaker = match.group(2).strip()
            text = match.group(3).strip()
        else:
            ts = ""
            speaker = "Speaker"
            text = raw_line

        lines.append({
            "line_number": line_num,
            "speaker": speaker,
            "timestamp": ts,
            "text": text,
        })
        if speaker and speaker != "Speaker":
            speakers.add(speaker)
        line_num += 1

    return lines, sorted(list(speakers))


def _parse_vtt(vtt_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parses Teams WebVTT format (<v Speaker Name>Text</v>)."""
    lines = []
    speakers = set()
    blocks = re.split(r"\r?\n\r?\n", vtt_text)
    line_num = 1

    ts_pattern = re.compile(r"(\d{2}:\d{2}:\d{2})\.\d{3}\s*-->")
    voice_pattern = re.compile(r"<v\s+([^>]+)>(.*?)(?:</v>|$)", re.DOTALL)

    for block in blocks:
        block = block.strip()
        if not block or block.startswith("WEBVTT"):
            continue

        ts_match = ts_pattern.search(block)
        ts = ts_match.group(1) if ts_match else ""

        v_match = voice_pattern.search(block)
        if v_match:
            speaker = v_match.group(1).strip()
            text = " ".join(v_match.group(2).split())
        else:
            # Fallback to lines after timestamp
            sublines = [
                raw_line.strip()
                for raw_line in block.splitlines()
                if "-->" not in raw_line and not raw_line.strip().isdigit()
            ]
            text = " ".join(sublines)
            speaker = "Speaker"

        if text:
            lines.append({
                "line_number": line_num,
                "speaker": speaker,
                "timestamp": ts,
                "text": text,
            })
            if speaker != "Speaker":
                speakers.add(speaker)
            line_num += 1

    return lines, sorted(speakers)


def format_transcript_for_llm(lines: list[dict[str, Any]]) -> str:
    """Formats numbered transcript lines cleanly for LLM prompt ingestion."""
    formatted = []
    for line in lines:
        ts = f"[{line['timestamp']}] " if line.get("timestamp") else ""
        formatted.append(f"Line {line['line_number']}: {ts}{line['speaker']}: {line['text']}")
    return "\n".join(formatted)
