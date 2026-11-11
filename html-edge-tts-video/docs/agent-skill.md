# Agent Workflow

This package turns two authored files and optional local media into a narrated HTML explainer,
tutorial, scientific demo, or presentation MP4. Keep the authored source separate from the stable
shell and generated assets. Each video must have its own project
folder under `.local/work`; `.local/work/starter/` is a read-only tracked template and must never be
edited as a project.

## Director modes (creative policy)

Follow `docs/video-director.md`. Use source-led reporting for news and factual product/repository
coverage, `tutorial` for software workflows, `interactive` for time-driven mechanisms, and
`presentation` when a static visual explanation fits the subject. Treatment and mode are director
decisions, not new `scenes.json` fields. A chapter can contain several shots.
Choose a content palette (paper, warm, science, dark-local) according to the brief,
but keep source full-frame backgrounds transparent: Shell theming is not yet configurable.
Do not reproduce Shell captions, timecodes, progress, or chapter rails in authored HTML.

## Preflight brief

Resolve the subject and intended outcome before creating a project. Infer routine choices from
the request and existing session context; ask only when missing information materially changes
the result and cannot reasonably be inferred. State useful assumptions and continue independent
work. Do not ask again about choices or permissions already resolved.

Use these defaults unless the request points elsewhere:

- informed general audience;
- roughly 2-3 minutes, with chapter and shot counts chosen for the explanation;
- infer the narration language from the request and use its default voice;
- `16:9`;
- research current primary or official sources when factual freshness matters and network access
  is authorized by the current environment;
- acquire useful real source media for factual coverage; choose asset count by coverage of key
  claims, rather than a fixed quota;
- no additional mandatory inclusions or exclusions.

These defaults do not authorize network access, installation, browser work, or rendering against
current environment restrictions. Use existing authorization; do not create an extra approval
flow. When real materials cannot be acquired, use available user media, narrow the claims, or
deliver a clearly limited source draft rather than claiming a completed source-led video.

## Source contract

```text
.local/work/<project-slug>/
  scenes.json      // Required
  body.html        // Required
  production.json  // Agent complete-video plan; optional for Web AI drafts and legacy projects.
  media/           // Optional
  captions.json    // Optional. Stores manual timing overrides only.
```

Choose a unique kebab-case `<project-slug>` and orientation before writing any source. The manifest
stores an immutable `aspectRatio`; use a new project instead of changing an existing orientation.
Create a landscape project (the default) or a portrait project with:

```bash
python main.py init --target .local/work/<project-slug>
python main.py init --target .local/work/<portrait-slug> --aspect-ratio 9:16
```

Then edit only the copied files in that new project folder. Never target `.local/work/starter/` and
never place a video's `scenes.json` or `body.html` directly in `.local/work/`.

`scenes.json` must contain at least two scenes. Start with `id: "intro"` and end with
`id: "outro"`. Default to an editorial knowledge-show voice: open directly with the subject, a
concrete fact, or the central question; close with a concise synthesis or forward-looking
implication. Do not force a greeting, sign-off, or thanks unless the user requests a presenter-led
style. Require:

- `id`: unique lowercase letters, numbers, and hyphens.
- `category`: a short chapter label, within 12 CJK characters or about 24 Latin characters.
- `narration.segments`: the only spoken-text source. Give every segment a document-wide unique
  lowercase id and grammatically complete text; each segment is an authored subtitle cut.

The Web AI prompt deliberately uses a simpler submission shape with one `narration` string per
scene. Studio must normalize that draft before validation and writing; a string is never valid in a
saved project. Code agents that write project folders directly must author the canonical segment
shape above.

For `9:16`, use 2-3 CJK characters or one short English word of at most 8 letters for every
`category`. The shell retains one horizontal chapter rail without scene numbers. Its segment
boundary dots remain proportional to narration time; each category is centered between its two
boundary dots while an independent label layer autofits it to at most two lines. Author portrait scenes as a vertical reading flow with stacked
visuals and short copy; do not rely on a responsive landscape-to-portrait conversion.

Visible titles, summaries, labels, charts, and diagrams belong in `body.html`, not duplicated scene
metadata. Write `body.html` as a complete document from `<!doctype html>` through `</html>`. Use one
`<section class="content-scene" data-scene="id">` per scene, do not hard-code an initial active
class, and include all project CSS in `<style>`.

Compose primarily inside the top 75% because the shell overlays captions and chapters across the
bottom of the frame. The recommended content boundary is `y=540` for `1280x720`, or `y=960` for
`720x1280`. This is a generation guideline, not a build gate: Studio may place content below it,
the shell remains above source visuals, and the user judges overlap in the live preview.

Put one `<div class="scene-canvas">` directly inside every scene and make it absolute with `inset:0`.
Give every top-level object inside it a unique `data-studio-id`, a valid `data-studio-kind`, and
inline absolute pixel geometry (`left`, `top`, `width`, `height`). Prefer `top + height` within the
recommended content boundary and keep internal group content inside its declared box.
Scope source layout and backgrounds to `#stage` or scene elements; never style `html`, `body`, shell
controls, captions, or chapter elements from `body.html`.

Default to stable compositions. Use shell-owned deterministic motion presets on top-level objects
only when motion guides attention:
`fade`, `rise`, `slide-left`, `wipe-left`, `zoom-in`, `ken-burns-in`, `pan-left`, `pan-right`, and
`pulse-once`. Declare one with `data-motion`; optional normalized `data-motion-delay` and
`data-motion-duration` values control its entrance window. Limit `data-motion` entrance presets to at most two top-level objects per scene: one
dominant move and one grouped reveal. This does NOT limit scripted deterministic actions
(typing, cursor movement, SVG path drawing, charts or parameter simulation) inside a
group for tutorial/interactive modes. Such actions must derive strictly from `sceneTime`
or `sceneProgress` via the one allowed inline module and must not use wall-clock timers.
Use grouped reveals and still frames whenever they explain better than motion.

Use a bright editorial blackboard/newspaper palette: pale blue, mint, seafoam, warm white, and dark
teal ink, with one restrained warm or medium-blue accent. Avoid dark full-frame backgrounds, neon,
and glassmorphism. Let the stable shell supply the soft gray-green graph-paper background and selected-canvas
frame border; keep full-frame source backgrounds transparent. Use pale blue, mint, seafoam, or warm-white
tints only on localized content surfaces that should sit above the grid. Transparent CSS backgrounds
do not require shrinking source images into cards: a real capture or demo may fill the authored
frame, with its important details kept clear of Shell overlays. For capture/demo-led chapters,
`data-frame="media"` on the scene opts into a plain frame without the grid, border, or chapter rail;
see the production guide for its lower caption region. Prefer one focal point per shot, strong hierarchy, whitespace,
controlled typography, and an explanatory visual. Keep ordinary titles at or below
64px, multi-column titles at or below 56px, and reserve up to 88px for short intro headlines. Build
repeated columns with container Grid tracks such as `minmax(0, 1fr)`, not fixed `vw` card widths.
Avoid decorative dashboards and irrelevant control panels. In tutorial mode, a focused
terminal/editor/browser mockup or a real rights-cleared screenshot is legitimate core
teaching content, not decorative UI; label reconstructions clearly as demonstrations.
Avoid card walls, nested boxes, horizontal overflow, and duplicated Shell transport UI.

## Agent production and media

A local Agent producing a complete new video owns acquisition, shot design, narration, and final
verification. Read [Agent production](agent-production.md) and maintain `production.json` in the
selected project as the visible plan connecting local assets, scene ids, narration cue ids, and
specific details shown. Choose `source-led` treatment for factual coverage, or `explanatory` for
mechanisms and authored demonstrations. Every canonical narration cue needs shot coverage;
source-led content chapters need real capture/demo/figure material. Intro and outro may use title
cards. Do not add these planning fields to `scenes.json` or `manifest.json`.

The plan supplements the authored files; it does not drive cuts, prove source authenticity, or
substitute for watching the result. Use cue-linked groups, timed media, or a deterministic visual
module to implement the intended shots in `body.html`. Recheck the plan after changing visuals or
narration. Existing projects and Web AI imports remain usable without a plan; omitting a plan is
not an Agent production review pass.

Follow the source-led reporting section in `docs/video-director.md` before committing to narration
and layouts. Acquire the excerpt, original chart, product capture, or actual demo that makes the
claim inspectable; a verified URL alone is insufficient. Asset count follows key claim coverage.
Preserve source appearance even when its palette differs from the authored theme. Use authored
diagrams for mechanisms and generated artwork for supplementary context, keeping both distinct
from observed product behavior.

When network and tools are authorized and available, search for suitable official, public-domain, permissively
licensed, or user-authorized images and video, download them into the selected project's `media/`
directory, and reference them with project-relative paths such as `media/diagram.webp`. Prefer
official product imagery for factual specificity and licensed editorial or stock footage for context.
Never hotlink remote assets or
silently use media with unclear reuse rights. If acquisition is blocked, try available primary
assets or user media, narrow the claim, or explicitly deliver a limited draft. Empty media slots
are appropriate for a Web AI handoff, not a completed Agent video.

Keep media inside the project; do not create a shared global asset workspace. Use descriptive,
stable filenames and useful image `alt` text. Check each downloaded file's actual type, dimensions,
and visual content before using it. Use PNG, JPEG, WebP, AVIF, GIF, MP4, or WebM assets. Prefer a few
meaningful assets integrated into the explanation over decorative filler.

Use the project's `media fetch`, `media capture`, and `media clip` commands for lightweight
acquisition and conversion; their arguments and examples are in [Agent production](agent-production.md).
They use the managed browser/FFmpeg constraints and do not authorize network access themselves.

Project videos are muted because narration is the final audio track. The shell synchronizes an
active scene's video to scene-relative time, including deterministic seeking during frame capture.
Optional `data-media-in`, `data-media-out`, `data-media-start`, and `data-media-rate` select a source
interval, scene-relative start, and speed. Defaults preserve existing video behavior. Use
`data-shot-cues` on a shot group to show it during named narration cues; one cue may show several
groups. See the production guide for exact timing and editable-preview behavior. Prefer a stable
reading hold when the material needs inspection rather than a cut at every subtitle.

## Optional scripted visuals

Use HTML, CSS, and SVG for authored explanations and source annotation. When Canvas or WebGL
materially improves the explanation, include at most one inline `<script type="module">` and export:

```js
export async function mount(context) {}
export function renderAtTime(seconds, context) {}
export function destroy() {}
```

Derive every frame from `seconds`, `sceneTime`, and `sceneProgress`. Do not start an independent
`requestAnimationFrame` loop. Pin exact dependency versions. The module receives the root, scenes,
timeline, duration, media base, render mode, active scene, scene index, and scene progress.

## Language

For short technology news, product updates, and repository coverage, use
[write-tech-narration](../.agents/skills/write-tech-narration/SKILL.md) to select the spoken detail,
divide information between narration and visuals, and revise the script before TTS.
A script-only request does not start the video production workflow.

For narration, follow the director guide's spoken editorial guidance and any available
writing reference explicitly requested by the user. Missing reference skills must not be
presented as applied. Keep useful scope qualifications, source dates, and evidence labels
on screen or in the handoff; speak them when they materially affect the story, rather than
turning every news item into a sequence of verification reminders.

Follow an explicit user choice, then a saved Studio choice, then infer the dominant language from
the request or imported narration. Support `zh-CN` and `en-US`. Do not silently translate imported
source. Let the resolved language choose the default voice. Agent builds use Edge TTS unless the
user explicitly requests Azure Speech. Pass `--provider azure` only for that explicit request;
missing Azure configuration is an error and must not silently fall back.

## Build

For a final narrated video, use this order:

```bash
python main.py check --source .local/work/<project-slug> --production
python main.py tts --source .local/work/<project-slug>
python main.py render --source .local/work/<project-slug> --size 720p --output <project-slug>.mp4
```

Run the production check before TTS and again after changing narration, assets, or shots. When
`production.json` exists, TTS and render also recheck it. The check covers structure, local paths,
corresponding scene references, and cue coverage. It cannot establish that a source is true, a
crop is readable, the cuts explain the subject, or narration sounds natural.

The `tts` command creates real narration and WordBoundary timing. Studio automatically creates an
in-memory estimated timeline when current TTS is unavailable, so interactive preview and scrubbing
do not require a build. The legacy `offline` command writes isolated debug assets under
`generated/preview/` and never replaces final narration. Use `studio` when an interactive preview
or caption edit is useful. Caption text edits write directly to `scenes.json` and normalize every
scene to the same segment schema using the current timeline cuts, invalidate old audio immediately,
and preserve the text even if the next TTS attempt
fails. TTS speaks one continuous utterance per scene, then maps WordBoundary timing back onto the
authored segments without choosing new subtitle cuts. Manual timing overrides are replaced whenever
TTS is regenerated. Per-scene audio and WordBoundary metadata are content-addressed by the actual
spoken text and voice settings. Changing subtitle cuts without changing that spoken text reuses the
scene audio; changing one scene's words regenerates only that scene before the project narration is
recomposed. A relative output name resolves inside the selected project, for example the command above
creates `.local/work/<project-slug>/output/<project-slug>.mp4`. Pass a filename, not a path; renders
cannot be directed outside the project output directory.

After `tts`, verify that `generated/timeline.json` contains at least one non-empty cue for the intro,
every content scene, and the outro. After rendering, use the bundled FFmpeg and the local preview to
check that the final MP4 decodes without container or codec errors and inspect representative
frames at the first active intro cue, a middle scene, and the outro. Confirm that the visible
caption matches the narration at each sampled time. Do not hand off a render with missing,
mismatched, or undecodable opening captions.

Use `python main.py prompt --topic "<topic>" --aspect-ratio 16:9` only when the user wants a prompt
to paste into a browser-based AI. Code agents should follow this document directly instead.

The shell URL `http://<host_url>:<port>/pipeline/shell/index.html` is an internal Studio/rendering
surface. Studio owns interactive playback; `?render=1` enables deterministic rendering.

The shell owns the scene transition. It defaults to 0.4 seconds and derives opacity from absolute
composition time. Change it with `--transition`, or use `0` to disable it. Do not add a second
transition system to source files.

## Toolchain

- Install dependencies only with `python main.py install`.
- Use Python Playwright's Chromium Headless Shell installed with `--only-shell chromium`.
- Keep the managed browser, recordings, profiles, screenshots, traces, and temporary Playwright
  files under `.local/playwright/`; never use Playwright's user-level cache or a system browser.
- Use only the FFmpeg binary bundled by `imageio-ffmpeg`.
- Let actual audio and WordBoundary metadata determine the final timeline.
- Treat narration timing as the authority for the derived composition timeline.
- Do not use wall-clock CSS animations, animated GIF timing, or independent animation loops for
  rendered motion. Drive motion from composition time, scene time, or scene progress; prefer synced
  MP4/WebM over GIF.
- Render captions as shell DOM.
- Never modify the tracked starter while creating a video. Create and work in a separate
  `.local/work/<project-slug>/` directory.
- Pipeline commands read the project directly and store timeline/audio under its `generated/`
  directory and renders under its `output/` directory.
- Before finishing changes to package code, run `python main.py check`.

<!-- HTML_VIDEO_DIRECTOR_V2 -->
