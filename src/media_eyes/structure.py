"""Observable scene transitions and silence, not semantic event predictions."""

import re


def analyze(engine, media_id, start=0.0, end=None, scene_threshold=0.3, silence_db=-35.0):
    media = engine.metadata(media_id)
    end = media["duration"] if end is None else end
    engine.timestamps(media_id, start, end, 1)
    if not 0.05 <= scene_threshold <= 0.95 or not -80 <= silence_db <= -10:
        raise ValueError("Scene threshold must be 0.05–0.95; silence threshold -80 to -10 dB")
    base = [
        "ffmpeg",
        "-protocol_whitelist",
        "file,pipe",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        str(start),
        "-i",
        media["path"],
        "-t",
        str(end - start),
    ]
    scenes = []
    if media["has_video"]:
        output = engine.run(
            [
                *base,
                "-an",
                "-vf",
                f"scale=320:-2,fps=2,select='gt(scene,{scene_threshold})',metadata=print:file=-",
                "-f",
                "null",
                "-",
            ],
            timeout=300,
        )
        scenes = [start + float(t) for t in re.findall(r"pts_time:([\d.]+)", output)]
    silences = []
    if media["has_audio"]:
        output = engine.run(
            [
                *base,
                "-vn",
                "-af",
                f"silencedetect=noise={silence_db}dB:d=0.5,ametadata=print:file=-",
                "-f",
                "null",
                "-",
            ],
            timeout=300,
        )
        pending = None
        for kind, value in re.findall(r"lavfi\.silence_(start|end)=([\d.]+)", output):
            timestamp = start + float(value)
            if kind == "start":
                pending = timestamp
            elif pending is not None:
                silences.append({"start": pending, "end": min(timestamp, end)})
                pending = None
        if pending is not None:
            silences.append({"start": pending, "end": end})
    return {
        "start": start,
        "end": end,
        "scene_changes": [t for t in scenes if start <= t < end][:100],
        "silences": silences[:100],
        "truncated": len(scenes) > 100 or len(silences) > 100,
        "recommended_segments": [
            {"start": max(start, t - 1), "end": min(end, t + 2)} for t in scenes[:12]
        ],
        "scope": "Scene sampling at 2 fps and silence >=0.5s; not speech, music or sound-effect identification. Brief transitions may be missed.",
    }
