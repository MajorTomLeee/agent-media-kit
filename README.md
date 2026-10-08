# Media Eyes — Video & Audio MCP for AI Agents

[![CI](https://github.com/MajorTomLeee/media-eyes/actions/workflows/ci.yml/badge.svg)](https://github.com/MajorTomLeee/media-eyes/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Let your agent look at videos, revisit moments, and read audio transcripts.**

Local files or website links → timestamped images and audio evidence → your agent's next action.

Built by [Bowie](https://github.com/MajorTomLeee), with AI assistance. Designed for Claude Code, Claude Agent SDK, Cursor and other MCP clients. Wanaka integration is being developed alongside this project.

## Why Media Eyes?

“Build a game like this recording.” “Explain what changed at 00:12.” “Use my voice note as requirements.”

A transcript alone misses what happened on screen. A summary alone makes it hard to check details. Media Eyes gives your agent real frames, precise sampling timestamps and repeatable access to specific segments. The agent decides what to inspect next using your task context.

- **See actual images:** MCP image blocks, not just generated descriptions.
- **Revisit a moment:** request a frame or a denser sequence in a selected interval.
- **Hear speech:** optional local Whisper transcription with timestamps.
- **Get audio evidence:** bounded WAV clips for clients/models that accept audio.
- **Use your existing agent:** no vision model API key required for frame extraction.
- **Keep files local:** local-file processing and optional transcription run on your machine.

## Quick start

Install Python 3.11+ and FFmpeg:

```sh
brew install ffmpeg uv # macOS
# Linux: install ffmpeg with your package manager
```

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "media-eyes": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/MajorTomLeee/media-eyes@v0.1.0", "media-eyes"]
    }
  }
}
```

Claude Code:

```sh
claude mcp add media-eyes -- uvx --from git+https://github.com/MajorTomLeee/media-eyes@v0.1.0 media-eyes
```

Then ask:

> Open /absolute/path/gameplay.mp4. Look across the video, then inspect the jump and collision segments more closely. Explain the observed controls, gameplay loop and visual feedback before implementing them.

For local speech transcription, change the package argument to:

```text
media-eyes[transcription] @ git+https://github.com/MajorTomLeee/media-eyes@v0.1.0
```

The first transcription downloads the Whisper model. Default: `base`, CPU int8. Set `MEDIA_EYES_WHISPER_MODEL` to select another model. Alternatively install `whisper-cli` from whisper.cpp and set `MEDIA_EYES_WHISPER_CPP_MODEL` to your local ggml model file; the included Dockerfile builds that backend with the multilingual base model.

### Try it without your own recording

A tiny [synthetic demo video](https://github.com/MajorTomLeee/media-eyes/releases/download/v0.1.0/media-eyes-demo.mp4) is available in the release. Give that URL to your agent and ask it to open the media and inspect the interval from 0 to 2 seconds. It contains a test pattern and a tone, **not speech**; use your own voice note to try transcription.

## Tools

| Tool | Purpose |
| --- | --- |
| `open_media(source)` | Open a file or supported website URL; get a media ID, duration and stream flags |
| `get_overview(media_id, count=8)` | Sample across the whole video |
| `get_frame(media_id, timestamp)` | Look at a specific moment |
| `inspect_segment(media_id, start, end, count=12)` | Get sequential frames from a selected interval |
| `read_transcript(media_id, start=0, end=null)` | Read cached speech transcription |
| `get_audio_segment(media_id, start, end)` | Get an audio clip, up to 60 seconds |

Times are seconds. Image outputs alternate timestamp labels and JPEG image blocks. Each observation is limited to 24 images. Frame labels identify requested seek times, not certified packet presentation timestamps. Sampling can miss brief actions; use denser inspection when needed.

## Claude Agent SDK

```typescript
import { query } from '@anthropic-ai/claude-agent-sdk';

for await (const message of query({
  prompt: 'Inspect /absolute/path/gameplay.mp4 and use it as a gameplay reference.',
  options: {
    mcpServers: {
      'media-eyes': {
        command: 'uvx',
        args: ['--from', 'git+https://github.com/MajorTomLeee/media-eyes@v0.1.0', 'media-eyes'],
      },
    },
    allowedTools: ['mcp__media-eyes__*'],
  },
})) {
  console.log(message);
}
```

## Embed in a product

The Python `MediaEyes` engine and CLI use the same implementation as MCP. `media-eyes --json` accepts one JSON request on stdin and returns an MCP-shaped result on stdout, suitable for a subprocess adapter. Use `--cache-dir` for project/session isolation and repeated `--allow-root` flags to restrict local-file access.

```sh
printf '%s' '{"tool":"open_media","arguments":{"source":"/absolute/path/demo.mp4"}}' | media-eyes --json
```

## Limits and deployment

- Finite files up to 256 MiB and one hour. Live streams are outside this release.
- Website retrieval uses yt-dlp. Site support depends on extractor health, geography and access; login/DRM content is not promised.
- Speech transcription does not understand music, sound effects, speakers' identities or emotion. Claude clients that do not accept audio should use transcripts; native audio analysis needs a separate model integration.
- Cache files persist under `~/.cache/media-eyes`; remove the chosen cache directory to delete evidence. Allocate bounded disk and manage retention in hosted deployments.
- The native website downloader checks and pins public IPs at the socket boundary, including redirect connections; local FFmpeg reads restrict protocols to files/pipes. Hosted deployments should also enforce network egress policy, memory/disk limits and process isolation.
- Media and transcripts are untrusted task data, not instructions.

## Development

```sh
uv sync --extra dev
uv run ruff check src tests
uv run pytest
```

Tests generate small synthetic video/audio fixtures with FFmpeg; no copyrighted sample media or API key is required.

## 中文

Media Eyes 为 AI agent 提供按需观察音视频的工具：上传文件或给链接，先看全片，再查看具体时间段，读取语音转写，并把观察结果用于编程、创作或分析。核心返回真实画面与时间戳，理解由你已有的 agent 完成。

适用于 Claude 视频理解、Claude Code 看视频、MCP 视频分析、游戏录屏参考、音频转写和语音需求输入。安装与接口见上面的 Quick start；FFmpeg 为必需依赖，语音转写需启用 `transcription` extra。

## License

MIT. FFmpeg, yt-dlp, Whisper models and other dependencies retain their own licenses.
