# Agent Media Kit — Video & Audio Tools for AI Coding Agents

[![CI](https://github.com/MajorTomLeee/agent-media-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/MajorTomLeee/agent-media-kit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Turn gameplay recordings, UI demos, website videos and voice notes into evidence your coding agent can use.**

Local files or website links → timestamped images and audio evidence → your agent's next action.

Built by [Bowie](https://github.com/MajorTomLeee), with AI assistance. Designed for Claude Code, Claude Agent SDK, Cursor and other MCP clients. See the [Wanaka integration](https://github.com/Wanaka-studio/wanaka-platform/pull/9255) for a production agent adapter with project-isolated attachments, pinned installation and credential-safe subprocesses.

## Why Agent Media Kit?

“Build a game like this recording.” “Explain what changed at 00:12.” “Use my voice note as requirements.”

A transcript alone misses what happened on screen. A summary alone makes it hard to check details. Agent Media Kit gives your agent real frames, precise sampling timestamps and repeatable access to specific segments. The agent decides what to inspect next using your task context.

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
    "agent-media-kit": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/MajorTomLeee/agent-media-kit@v0.2.0", "agent-media-kit"]
    }
  }
}
```

Claude Code:

```sh
claude mcp add agent-media-kit -- uvx --from git+https://github.com/MajorTomLeee/agent-media-kit@v0.2.0 media-eyes
```

Then ask:

> Open /absolute/path/gameplay.mp4. Look across the video, then inspect the jump and collision segments more closely. Explain the observed controls, gameplay loop and visual feedback before implementing them.

For local speech transcription, change the package argument to:

```text
agent-media-kit[transcription] @ git+https://github.com/MajorTomLeee/agent-media-kit@v0.2.0
```

The first transcription downloads the Whisper model. Default: `base`, CPU int8. Set `MEDIA_EYES_WHISPER_MODEL` to select another model. Alternatively install `whisper-cli` from whisper.cpp and set `MEDIA_EYES_WHISPER_CPP_MODEL` to your local ggml model file; the included Dockerfile builds that backend with the multilingual base model.

### Try it without your own recording

A tiny [synthetic demo video](https://github.com/MajorTomLeee/agent-media-kit/releases/download/v0.2.0/media-eyes-demo.mp4) is available in the release. Give that URL to your agent and ask it to open the media and inspect the interval from 0 to 2 seconds. It contains a test pattern and a tone, **not speech**; use your own voice note to try transcription.

## Tools

| Tool | Purpose |
| --- | --- |
| `open_media(source)` | Open a file or supported website URL; get a media ID, duration and stream flags |
| `get_overview(media_id, count=8)` | Sample across the whole video |
| `get_frame(media_id, timestamp)` | Look at a specific moment |
| `inspect_segment(media_id, start, end, count=12)` | Get sequential frames from a selected interval |
| `read_transcript(media_id, start=0, end=null)` | Read cached speech transcription |
| `get_audio_segment(media_id, start, end)` | Get an audio clip, up to 60 seconds |
| `analyze_media(media_id, start=0, end=null)` | Locate scene changes and silence to choose segments |
| `analyze_audio(media_id, start, end)` | Opt-in cloud descriptions of music/sound, up to 60 seconds |
| `cleanup_cache()` | Apply bounded derived-cache retention |

Times are seconds. Image outputs alternate timestamp labels and JPEG image blocks. Each observation is limited to 24 images. Frame labels identify requested seek times, not certified packet presentation timestamps. Sampling can miss brief actions; use denser inspection when needed.

`get_frame` also accepts `format="png"` and `width=1920` (320–2560). `read_transcript` accepts `language="zh"`/`"en"`/`"auto"`: website captions take priority, with manual/automatic provenance; absent captions fall back to local speech recognition of only the requested interval, in chunks up to 10 minutes. Captions may cover only part of an interval. Scene detection samples at 2 fps; silence detection is not semantic audio understanding.

## One link, interchangeable retrieval backends

`open_media(source, backend="yt-dlp")` is free by default. There is no automatic paid fallback or automatic reading of your browser cookies.

For ordinary Bilibili BV/AV videos, a webpage HTTP 412 triggers one fallback to the public WBI-signed API, using yt-dlp's pinned signing and stream parser. Requested `?p=N` parts are preserved. This does not log in, solve CAPTCHAs, or unlock paid/preview-only videos. API and CDN requests still use the public-IP socket guard. If the API is also blocked, the tool reports the real failure category and HTTP status rather than claiming it watched the video.

Website failures include `PLATFORM_BLOCKED` (HTTP 412/429), `ACCESS_REQUIRED` (401/403), `SOURCE_UNAVAILABLE` (404/410), and `DRM_UNSUPPORTED`. Safe lifecycle/fallback diagnostics go to stderr as JSON; MCP results remain on stdout. Credentials, cookies and signed CDN URLs are not included in diagnostic records.

Run the real website smoke yourself after installing the package:

```bash
python tests/smoke_website.py 'https://www.bilibili.com/video/BV1pg411W79J/'
```

This exercises the installed MCP JSON interface, actual download and AV merging, six timestamped frames, and a WAV segment. The GitHub Actions **Agent Media Kit CI → Run workflow** path runs the same opt-in live check on a public-DNS Linux runner. Ordinary CI uses the stable synthetic fixture; third-party website access is verified separately rather than hidden behind mocked tests. Site policy changes can still require renewed verification.

| Backend | Configuration | Scope |
| --- | --- | --- |
| `yt-dlp` | None | All installed extractors, including Bilibili, YouTube, Douyin, TikTok and Xiaohongshu; actual access varies |
| `cobalt` | `MEDIA_EYES_COBALT_URL` (HTTPS); optional `MEDIA_EYES_COBALT_API_KEY` | Your own/authorized unified Cobalt API, including Bilibili and major overseas sites |
| `tikhub` | `MEDIA_EYES_TIKHUB_API_KEY` | Bilibili, Douyin and TikTok adapters; commercial opt-in |

Cobalt and TikHub resolve media addresses; Agent Media Kit still reads the actual media for frames and audio. Bilibili's separate video/audio streams are merged locally. Returned CDN addresses and redirects must pass the same public-IP checks. Provider keys are sent only to the configured provider API, never to media CDNs. Cobalt's public instance is not a free API for third-party projects. See [Cobalt API docs](https://github.com/imputnet/cobalt/blob/main/docs/api.md) and [TikHub's endpoint reference](https://github.com/TikHub/TikHub-API-Python-SDK/blob/main/docs/reference.md).

Only select a service backend after configuring it in the MCP server's environment. A website appearing in an upstream support list is **not** an end-to-end verification claim. Current automated network smoke downloads the synthetic release video; commercial provider adapters have contract tests, not paid live verification. Other TikHub platforms (Xiaohongshu/Kuaishou/WeChat Channels) are not implemented adapters yet.

### Optional sound and music analysis

Install `agent-media-kit[audio-analysis]`, then explicitly set `MEDIA_EYES_GEMINI_API_KEY` and `MEDIA_EYES_GEMINI_MODEL` to a model available in your Google account. Calling `analyze_audio` sends only the requested clip to Google and may incur charges. Results are model-generated descriptions with absolute timestamps, not guaranteed observations or speech transcripts. Without both variables no cloud call is made. The provider boundary is tested without spending API credits.

## Credits

[claude-video-vision](https://github.com/jordanrendric/claude-video-vision) informed the scene/silence, segment inspection and optional audio-backend design. The implementation here is independently written; upstream deserves credit for demonstrating the workflow. Retrieval relies on yt-dlp, optional Cobalt/TikHub APIs, and FFmpeg; local speech uses whisper.cpp or faster-whisper. These components retain their own licenses; no AGPL Cobalt source is vendored into this MIT project.

## Claude Agent SDK

```typescript
import { query } from '@anthropic-ai/claude-agent-sdk';

for await (const message of query({
  prompt: 'Inspect /absolute/path/gameplay.mp4 and use it as a gameplay reference.',
  options: {
    mcpServers: {
      'agent-media-kit': {
        command: 'uvx',
        args: ['--from', 'git+https://github.com/MajorTomLeee/agent-media-kit@v0.2.0', 'agent-media-kit'],
      },
    },
    allowedTools: ['mcp__agent-media-kit__*'],
  },
})) {
  console.log(message);
}
```

## Embed in a product

The Python `MediaEyes` engine and CLI use the same implementation as MCP. `agent-media-kit --json` accepts one JSON request on stdin and returns an MCP-shaped result on stdout, suitable for a subprocess adapter. Use `--cache-dir` for project/session isolation and repeated `--allow-root` flags to restrict local-file access. The `media-eyes` command and `media_eyes` Python import remain compatibility aliases from the initial release.

```sh
printf '%s' '{"tool":"open_media","arguments":{"source":"/absolute/path/demo.mp4"}}' | agent-media-kit --json
```

## Limits and deployment

If a proxy uses fake-IP DNS (for example, resolves public sites to `198.18.x.x`), URL access is rejected intentionally. Configure real public DNS for the media worker; do not disable the private-network checks. Website support also depends on yt-dlp and each site's access policy.

- Finite files up to 256 MiB and one hour. Live streams are outside this release.
- Website retrieval defaults to yt-dlp; explicitly selectable Cobalt and TikHub adapters are available. Site support depends on extractor health, geography and access; login/DRM content is not promised.
- Speech transcription does not understand music or sound effects. Optional `analyze_audio` uses a separately configured cloud model; it is disabled by default and is not enabled in Wanaka.
- Derived cache entries expire after 7 days and are evicted oldest-first above 2 GiB. A cross-process lock prevents duplicate downloads and conflicting transcriptions; concurrent calls wait up to 30 seconds then return a retryable busy error. Original local files are never removed. `cleanup_cache` runs retention immediately.
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

Agent Media Kit 为 AI agent 提供按需观察音视频的工具：上传文件或给链接，先看全片，再查看具体时间段，读取语音转写，并把观察结果用于编程、创作或分析。核心返回真实画面与时间戳，理解由你已有的 agent 完成。

适用于 Claude 视频理解、Claude Code 看视频、MCP 视频分析、游戏录屏参考、音频转写和语音需求输入。安装与接口见上面的 Quick start；FFmpeg 为必需依赖，语音转写需启用 `transcription` extra。

## License

MIT. FFmpeg, yt-dlp, Whisper models and other dependencies retain their own licenses.
