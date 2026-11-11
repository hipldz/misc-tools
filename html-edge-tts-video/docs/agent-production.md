# Agent production: evidence and shots

Read this for a local Agent delivering a complete new video. Web AI still returns only
`scenes.json` and `body.html`; existing projects can continue without a production plan.
The source schemas, immutable aspect ratio, and managed toolchain remain unchanged.

## Acquire what the viewer needs to see

Inspect sources before committing to the script. For a product capability, find the actual
operation and result. For a quantitative claim, find the original chart and comparison conditions.
A headline or repository homepage can establish identity but cannot demonstrate behavior.
Choose materials by the claims they explain; neither an asset quota nor a GIF quota establishes
quality. Authored diagrams are appropriate for mechanisms and labelled reconstructions.

Useful acquisition paths, in order of relevance to the subject:

- Follow the original article/repository to its figures, embedded media, or author's demo.
- Download a usable original asset or capture the relevant visible page excerpt.
- Use an authorized existing local recording or supplied image when it shows the needed detail.
- If a source is inaccessible, find another primary asset, narrow the claim, or identify the
  remaining gap. Generated artwork cannot establish observed product behavior.

Network and browser use require the authorization already applicable to the task. These commands
do not create permission and do not replace source/reuse judgment:

```bash
python main.py media fetch --source .local/work/my-video --url https://example.org/demo.gif --name original-demo.gif
python main.py media capture --source .local/work/my-video --url https://example.org/announcement --name excerpt.png --selector 'article h1'
python main.py media clip --source .local/work/my-video --input media/original-demo.gif --name demo.mp4 --start 2 --duration 6
```

These URLs and selectors illustrate the interface; choose the actual relevant source/excerpt.
Keep the original GIF as an input and use its converted MP4 for timed playback.

`fetch` streams one file, checks its signature against the chosen extension, and rejects HTML
error pages. It defaults to 32 MiB (`--max-mb` can raise this up to 128), with bounded timeouts.
It does not search for sources or decide reuse rights. `capture` opens one managed Headless Shell
context and page, defaults to a 1280×720 viewport at scale 1, optionally captures one CSS selector,
and closes the context even on failure. Selector captures larger than 2560×1440 are rejected;
capture a useful excerpt instead of an entire article. Browser state stays in `.local/playwright/`;
the selected image is copied into project `media/`.

`clip` accepts a project-local input and makes one silent MP4 using the Python environment's
FFmpeg. Defaults: up to 12 seconds, within 1280×1280, 15 fps, one encoding thread, and a 60-second
process timeout. `--duration` can select up to 30 seconds. It preserves the input. All three
commands use `--name` as a new filename in the selected project's `media/` and refuse to replace
an existing asset. No installation, system browser, or system FFmpeg fallback occurs.

Inspect acquired images and useful clip frames before composition: actual content, legibility,
dimensions, context, and whether the material supports the claim. A successful download alone
does not establish any of these. Preserve source appearance; add attribution where relevant.

## Keep an inspectable plan

Maintain project-local `production.json` while developing a complete Agent video. It connects
selected assets to canonical narration segments. This planning file is separate from the two
authored source files and is not a new `scenes.json` or manifest field. The runtime does not read
it or automatically implement the cuts.

Example for a three-scene project whose canonical narration contains the four cue ids below:

```json
{
  "version": 1,
  "treatment": "source-led",
  "assets": [
    {
      "id": "tool-demo",
      "path": "media/demo.mp4",
      "kind": "demo",
      "source": "https://example.org/project/original-demo.gif",
      "reuse": "Record the actual applicable permission or license here",
      "date": "Record the source date when it matters"
    }
  ],
  "shots": [
    {"scene": "intro", "cues": ["intro-01"], "assets": [], "shows": "The concrete task being investigated"},
    {"scene": "demo", "cues": ["demo-01"], "assets": ["tool-demo"], "shows": "The input and the tool action in the original recording"},
    {"scene": "demo", "cues": ["demo-02"], "assets": ["tool-demo"], "shows": "A readable crop of the resulting output, with the limitation identified"},
    {"scene": "outro", "cues": ["outro-01"], "assets": [], "shows": "The supported conclusion and unresolved question"}
  ]
}
```

Replace example descriptions and source information with actual observations; do not report the
example as acquired material. Asset fields:

| Field | Meaning |
|---|---|
| `id` | Unique asset identifier referenced by shots |
| `path` | Existing project-relative file inside `media/` |
| `kind` | `capture`, `demo`, `figure`, `reconstruction`, or `generated` |
| `source` | Original URL or identifiable supplied/local source |
| `reuse` | Actual permission, license, ownership, or other applicable reuse basis |
| `date` | Optional source/event date information when relevant |

Shot fields are `scene`, a non-empty `cues` array of that scene's canonical segment ids, an
`assets` array of selected asset ids, and `shows`, which describes the specific detail visible.
Use `assets: []` for a self-contained diagram or title. Multiple shots can share a cue or asset;
several consecutive cues can share a reading hold. List the selected composition assets, rather
than every unused downloaded input.

Use `source-led` for factual news/product/repository coverage: each content scene must use a
real capture, demo, or original figure; intro/outro can use titles. Explanatory inserts can still
use diagrams. Use `explanatory` for mechanisms or authored demonstrations; all narration still
needs a concrete planned visual. These labels describe the intended treatment, not proof that
an asset is authentic. Do not relabel generated artwork as a capture to satisfy a check.

## Implement shots inside a chapter

One scene can contain multiple shots. Keep a stable focus while the explanation holds, then
change crop, comparison, operation, or result when the subject of the sentence changes.
Do not mechanically cut with every subtitle, and do not repeat the narration as a wall of text.

Use `data-shot-cues` on any shot group inside its matching scene:

```html
<div data-studio-id="demo-result" data-studio-kind="group"
     data-shot-cues="demo-01 demo-02"
     style="position:absolute;left:40px;top:40px;width:1200px;height:490px">
  <video src="media/demo.mp4" muted playsinline preload="metadata"
         data-media-in="0" data-media-out="6" data-media-start="3" data-media-rate="1"
         style="width:100%;height:100%;object-fit:contain"></video>
</div>
```

The group follows its named cue windows on the actual/estimated narration timeline. A shot holds
through a subtitle gap until the next cue starts; the first/last cue's shot also holds to the
chapter edge. Several groups may show during the same cue. Runtime visibility is kept outside authored node styles,
so saving source geometry does not persist an accidentally hidden shot. Studio previews follow
the current time; use playback/scrubbing to inspect different shots, not one frame per chapter.

For a capture/demo-led chapter, add `data-frame="media"` to its `section`. This opts into
a plain Shell backdrop without the grid, outer border, or chapter rail, with compact dark
caption backing near the bottom. It affects that scene in both preview and render; no manifest
or global theme change is needed. Keep source details and attributions clear of the lower 13%
caption region. Without this attribute, the existing editorial frame is preserved.

Video mapping:

| Attribute | Meaning | Default |
|---|---|---|
| `data-media-in` | First source timestamp, seconds | `0` |
| `data-media-out` | Exclusive source endpoint, seconds | Source duration |
| `data-media-start` | Start in scene-relative seconds | `0` |
| `data-media-rate` | Positive playback speed multiplier | `1` |

Before its scene start the video is hidden and paused. While visible, its target is source-in
plus elapsed scene time times rate. With `loop`, it wraps within the selected source interval;
otherwise it holds the interval's last frame. Hidden shot videos pause. A cue group controls
visibility, not the clip clock: hiding/revealing a group does not restart the video. Choose a
matching scene start after TTS or pre-trim the input. Leaving all attributes off preserves the
existing scene-time playback model. Out points past source duration are clamped at playback.

Use the single deterministic inline module for a deliberate moving crop, data explanation,
or alignment more detailed than these controls. Derive it from cue timestamps/scene time, not
wall-clock animation. True source images can fill the frame; transparent CSS scene backgrounds
do not require enclosing them in a small card. Keep the important detail clear of Shell overlays.

## Check before TTS, then inspect the implemented result

```bash
python main.py check --source .local/work/my-video --production
python main.py tts --source .local/work/my-video
python main.py render --source .local/work/my-video --output my-video.mp4
```

`--production` requires the plan and checks its shape, existing local assets, corresponding
scene references, known cue ids, and visual coverage of every narration segment. Source-led
content scenes need at least one bound real-source asset. TTS/render also check a plan whenever
it exists. Normal checks still permit missing Web AI media slots as drafts; final rendering
requires local visual resources. Existing no-plan projects retain their normal workflow.

Technical checks cannot verify that `source` is genuine, `reuse` is sufficient, `shows` is true,
or the asset is actually visible at its planned cue. Review those at the relevant moments after
real TTS: the initial evidence, changes of focus, the demo's result, the densest crop, and the
longest subtitle. Look for tiny unreadable screenshots, unsupported claims, repeated captions
and headings, long unexplained holds, and decorative motion. Revise the shots or narration,
then rerun the production check. A valid plan is not an editorial quality score.

Deliver the video with a concise source/material summary and any remaining limitations. A
source-only draft or missing real demonstration must be identified as such.
