"""Opt-in network smoke against the release's synthetic recording."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from media_eyes.core import MediaEyes

with TemporaryDirectory(prefix="media-eyes-url-") as directory:
    engine = MediaEyes(Path(directory), roots=[])
    media = engine.open_media(sys.argv[1])
    assert media["has_video"] and media["has_audio"]
    for timestamp in engine.timestamps(media["media_id"], 0, 2, 2):
        assert engine.frame(media["media_id"], timestamp).read_bytes().startswith(b"\xff\xd8")
    print("Public URL download and timestamped frame extraction passed")
