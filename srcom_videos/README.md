# srcom-videos

Small, game-agnostic helper library: fetch the top runs of a speedrun.com
leaderboard and download their videos **small** (capped resolution and frame
rate, video only).

```bash
pip install -e srcom_videos
python -m srcom_videos list --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=GC" --top 5
python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=GC" --top 5 --out data/videos --height 480 --fps 30
```

From Python:

```python
from srcom_videos import SrcomClient, top_runs, download_video, DownloadOptions

client = SrcomClient(cache_dir="data/cache/srcom")
runs = top_runs(client, "pikmin2", "All Treasures", {"Console (AT)": "GC"}, n=3)
for run in runs:
    if run.videos:
        download_video(run.videos[0].canonical_url, "data/videos", run.slug(), DownloadOptions(max_height=480))
```

- Games, categories, variables and values can be given by name or id.
- API responses are cached on disk (default TTL 24 h) and requests are rate limited.
- Downloads prefer an H.264 stream that already fits the limits. Audio is dropped,
  and ffmpeg (bundled through `imageio-ffmpeg`) re-encodes only when no stream fits.
- `download` writes `manifest.json` next to the videos with each run's metadata and status.
- `cut_clip()` copies a time range out of a video (for keeping only the parts you need).
- YouTube needs a JavaScript runtime for yt-dlp; Node is used by default (`DownloadOptions.js_runtime`).
