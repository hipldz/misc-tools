# HTML Video Director — evidence, shots, and explanation

> Creative rules only. The authoritative source/runtime contract remains `docs/agent-skill.md`.
> Preserve canonical `scenes.json` with `narration.segments` for agent-authored files, and exactly
> one standalone `body.html`. A local Agent producing a complete video also maintains the
> [production plan](agent-production.md); this does not change either source schema.
> For Web AI copy/import, follow `docs/source-prompt.md` and return only two files.

## 1. Select the viewing experience before the tool

| Intent | Mode | On screen | Preferred rendering |
|---|---|---|---|
| News, product or repository coverage | source-led reporting | relevant source excerpt, original figure, actual operation/result | real local captures, muted demo clips, crops and annotations |
| Teach a workflow or software | `tutorial` | stepwise terminal/editor/browser demos, result and revision | CSS/SVG, deterministic visual module, real muted local MP4 footage |
| Explain a scientific mechanism | `interactive` | growing curves, parameter changes, molecular diagram | SVG/Canvas/Three.js if needed, deterministic visual module |
| A subject best explained by a static comparison or diagram | `presentation` | readable visual relationships and one focal point | stable compositions and selective `data-motion` presets |

`mode` is a director decision, not a required metadata field. Do **not** invent fields in
`scenes.json` or `manifest.json`. If the user explicitly asks for an interactive webpage
as the *deliverable*, an MP4 alone is insufficient; this package can demonstrate the interaction
in a video, but should not claim the delivered MP4 is clickable.

## 2. Build shots from the material

For source-led reporting, inspect and acquire the relevant source visuals first. Decide what they
actually support, then draft narration and shots together. Do not finish an abstract script and
attach a few images afterward. For a mechanism, start from the process or causal relationship the
viewer needs to see; an authored explanation can be the main visual.

Scenes are chapters, not individual shots. A single chapter may move from context to a readable
crop, an operation, and a result. Use cuts, crop changes, comparisons, or highlights when the
explanation changes focus; a title entrance or subtitle change alone is not a new shot. Do not
force a cut every few seconds. Leave time to inspect diagrams and read relevant source details.

In the Agent's `production.json`, record which scene and narration cues a shot supports, its local
assets, and what is visibly shown. The schema and runtime controls are in
[Agent production](agent-production.md). Before authoring, resolve:

- **One learning outcome:** a verb + object, e.g. “see how changing the antibiotic concentration changes population growth.”
- **Visible evidence or process:** identify the specific paragraph, data feature, operation,
  result, or causal change being explained. A generic interface or role diagram cannot establish
  that a real product performed the claimed operation.
- **Camera direction:** choose ONE attention focal point; moving the whole group is preferable to many floating boxes.
- **Narration alignment:** show the detail while it is discussed and leave a reading hold.
  Let speech explain cause, meaning, or limits while the image carries inspectable detail; do not
  repeat the full narration as headings and bullet lists.
- **Truth label:** if the screen is reconstructed, mark `操作示意` or `界面示意` unobtrusively. Never present simulation as real login results.
- **Review target:** identify moments that need visual inspection, such as a cut, a clip result,
  the densest source crop, and the longest caption.

### Software tutorial shot decisions

Show a concrete task, the input or action that matters, its visible result, and any revision
needed to understand the outcome. Include tool choice or code only when it explains the behavior.
Prefer an authorized actual demonstration when available; label an authored example as a
reconstruction and do not narrate it as a personally observed execution. Let the task determine
the sequence and length; audio remains authoritative for final timing.

### Source-led reporting for news and factual coverage

Apply this workflow to news roundups, product announcements, and repository coverage when
the user permits real media. Respect a different requested treatment or code-only brief.
Choose the stories and their evidence before committing to a slide layout.

1. Open the original source and establish its publication date, the event date when different,
   and what it actually supports. A search snippet or a secondhand headline is insufficient.
   For GitHub project sharing, follow the repository's official website, documentation and
   case-study links before choosing the angle. Pick a concrete task, example or result that
   makes this project interesting; do not stop at paraphrasing its About section. Keep a quick
   sharing video brief: deeper research should improve the selected detail and source shots,
   rather than automatically turning the story into a mechanism lesson.
2. Acquire the visual that makes the story concrete:
   - Article or announcement: a real capture of the relevant excerpt with enough title/date
     context to identify it; use the original chart or figure when discussing its data.
   - Repository or product demo: the author's actual demo GIF/video or a permitted local
     demonstration. A repository page establishes identity; it does not demonstrate behavior.
   - Social announcement: the accessible original post. If only an archive is accessible,
     label it as an archive and retain the original link; do not recreate it as a real capture.
3. For complete Agent production, record source, acquisition/reuse basis, local asset path,
   date when relevant, and the detail shown in `production.json`. Record useful clip intervals
   in the implemented media timing. Keep source attribution visible where it helps the viewer.
   Web AI drafts can identify intended source excerpts in HTML comments and retain two-file output.
4. Write the spoken explanation around the acquired material. For each important sentence,
   identify the paragraph, chart feature, operation, or result visible at that moment.
   Hold a readable crop while discussing it; move to another detail when the explanation moves.
5. News story scenes should normally spend most of their runtime showing real source material.
   Use titles, diagrams, and generated artwork for framing or explanation. A checked source URL
   plus a generic illustration does not count as showing the source.

Preserve the source's appearance and the context needed to understand an excerpt. Attribute
the source in the scene content; keep dates, units, qualifications, and relevant chart labels
legible. Cropping and highlights may guide attention but must not change the meaning. Do not
reuse one generic image as the dominant visual for unrelated stories, fabricate screenshots,
or imply that an illustrative reconstruction is a recorded execution.

When a repository or official website address is a viewing destination, make it a readable
content object rather than burying it in the attribution fine print. At a 1280×720 design size,
start around 24–28px for in-scene addresses and 28–32px for the closing project list; shorten to
`owner/repo` with an explicit GitHub label when necessary. Keep addresses above the caption area
and hold them long enough to read. A company homepage may feature another product: identify the
page accurately and never present that product as the repository's subject.

Use the lightweight `media fetch`, `media capture`, and `media clip` commands described in
[Agent production](agent-production.md). They do not grant network or browser authorization.
Capture only the relevant material, following the existing browser and media constraints.
Use one managed Headless Shell browser and one page at a time, bounded timeouts, and close it
after capture, including on failure. Keep capture state under `.local/playwright/`, then copy
selected final images into the project's `media/`. Avoid whole-site capture batches, long
screen recordings, or starting a heavy demo solely to obtain a shot on a constrained machine.
Prefer an existing authorized demo clip when it already shows the needed behavior.

For an animated repository GIF, keep the original as an input and convert a useful short
excerpt into a project-local MP4/WebM with the `imageio-ffmpeg` binary. This is a media-asset
conversion, separate from exporting the complete video. Use the shell's synchronized muted
video playback; do not rely on a GIF's wall-clock playback for rendered motion. Static source
crops can use a motion preset or the allowed deterministic module for a deliberate zoom or
highlight aligned to narration. Preserve reading holds; motion is not a substitute for evidence.

If acquisition is blocked, first look for another available primary asset or use supplied media.
Otherwise narrow the claim, reconsider the story, or deliver an explicitly limited source draft.
An explanatory visual may explain a mechanism, but cannot satisfy missing evidence for real
product behavior. Do not report a completed source-led production with empty slots or substitute
generated art and call the source-visual requirement met.

### Spoken editorial voice

For short technology coverage, apply
[write-tech-narration](../.agents/skills/write-tech-narration/SKILL.md) before TTS.
It owns the detailed narration editing guidance and includes optional rewrite examples.
The general guidance below also applies to other factual subjects.

When the user supplies a writing skill or sample, read it and adapt its voice to speech while
preserving factual attribution. Do not claim to follow a named skill that could not be found.
Without a reference, use short, natural sentences that explain the interesting detail directly.

Open on a concrete development, surprising detail, or useful question. Give each story its own
reason to be included: what happened, which detail matters, and the implication supported by
the source. Let the material determine the structure rather than repeating the same numbered
introduction and summary for every story.

Revise lines that merely announce the next item, describe the video's plan, or conclude that
"AI is entering work and life" without adding anything specific. Put routine date/source checks
and minor qualifications in visual labels or the handoff. Keep them in the spoken explanation
when they change the audience's understanding, such as a demo being unavailable as a product.
Keep company-reported results attributed; never invent personal use, experiments, reactions,
or product availability to make the narration sound more human.

Before TTS, read the draft as spoken language. A sentence that could introduce an unrelated
story unchanged is a candidate for replacement with a concrete detail or removal. Check that
each consequential claim has a useful visual at the corresponding moment, rather than leaving
one headline or illustration on screen through an entire paragraph.

## 3. Use the smallest technology that works

- HTML/CSS/SVG: typography, terminal typewriting, simple diagrams, step reveals and charts.
- One inline `type="module"` visual script: deterministic curves, cursors, numeric changes, Canvas/WebGL. It **must** export `mount()` and `renderAtTime()`; optional `destroy()`.
- Local project media: existing real screenshots, screencasts, official assets, or pre-rendered complex shots; place under `media/`. Videos are muted and scene-time synchronized by the shell.
- Manim/Remotion/Three.js as **optional producers** of a short local visual asset, not dependencies of this core project.

**Never** use independent `setTimeout`, `setInterval`, wall-clock CSS infinite loops, `Date.now()`,
`Math.random()` at frame time, or independently scheduled `requestAnimationFrame` in generated
visuals. Use `sceneTime` and `sceneProgress` from Shell. Scrubbing to the same time twice must
produce the same image. For browser-seekable animation, SVG stroke offsets and computed transforms
are usually safer than fire-and-forget CSS animation.

### Deterministic module example

This snippet belongs inside the sole inline `<script type="module">` at the end of `body.html`.
The target element must belong to the right `<section data-scene="...">` and should be inside a
Studio-editable grouped object.

```js
let codeLines;
let cursor;
export function mount({ root }) {
  codeLines = root.querySelector('[data-scene="code-demo"] .typed-code');
  cursor = root.querySelector('[data-scene="code-demo"] .cursor');
}
export function renderAtTime(_seconds, { scene, sceneProgress }) {
  if (!codeLines || !cursor) return;
  if (scene.id !== 'code-demo') return;
  const p = Math.max(0, Math.min(1, sceneProgress));
  const source = 'const html = await model.generate(prompt);';
  const count = Math.floor(source.length * Math.min(1, p / 0.72));
  codeLines.textContent = source.slice(0, count);
  cursor.style.opacity = p < 0.88 ? '1' : '0';
}
export function destroy() { codeLines = null; cursor = null; }
```

For all timelines, the DOM written by `renderAtTime()` should depend only on its inputs;
no mutable incremental counters and no hidden dependency on previous calls.

## 4. Visual system (content-level themes)

These palettes apply to authored scene content **only**. Keep stage and scene CSS backgrounds
transparent; shell theming is not configurable here. This does not require shrinking original
material into tinted cards. A real capture, figure, or demo can fill the authored frame while
the shell overlays remain on top. Keep the important detail above the caption region.

| Preset | Surface | Ink | Accent | Best for |
|---|---|---|---|---|
| `paper` | `#F8F9FC` | `#182334` | `#8B5CF6` | AI software tools, design/tutorial |
| `warm` | `#FFF8EC` | `#3E332A` | `#EA9062` | accessible general education |
| `science` | `#EAF7FB` | `#143C45` | `#139EA8` | biology, medicine, data/science |
| `dark-local` | `#101C2F` | `#F4F6FF` | `#A99BFF` | terminal/editor **panel only** |

Store visual tokens as CSS custom properties within `#stage` / `.content-scene`, not on `html` or
`body`. Preserve readable contrast and font sizes after downscaling. Keep graphical detail legible
at 720p. Prefer pale backgrounds with an isolated dark code pane, rather than a full dark stage.

## 5. Section rail, subtitles, and safe region

Stable Shell owns caption DOM and the chapter rail, not `body.html`.

- Default existing layout: keep primary authored objects in upper **75%** of frame as the current
  source contract advises. The explicit 1280x720 design boundary is `y=540`.
- Verify longest two-line subtitle stays clear of the focus point and chapter rail.
- A capture/demo-led scene may use `data-frame="media"` for a plain frame without the grid,
  border, or chapter rail. Keep the important source detail above its lower 13% caption region.

## 6. Quality gates

Before delivering a final video:

1. Verify scene ids, canonical `narration.segments`, matching `[data-scene]`, Studio ids, and CSS rules.
2. For Agent production, run `python main.py check --source .local/work/<slug> --production`
   before TTS and again after changes to the shots, assets, or narration.
3. When preview is authorized, scrub meaningful cuts, dynamic actions, and their results;
   check that seeking backward gives the same picture.
4. Inspect the planned review targets for legibility, visual hierarchy, and caption overlap.
5. Run TTS and render; verify MP4 decodes and captions correspond to narration.
6. State clearly when a demo is an illustrative reproduction, not an actual executed command.
7. If actual rendering was not done, deliver source only and explicitly state that it is unverified.

For source-led reporting, also verify before TTS that the planned real assets exist locally,
each story's key spoken details match the material shown, and the draft has been edited for
natural speech. At delivery, distinguish real captures/demos, original data, reconstructions,
and generated illustrations; list any source visuals that could not be acquired. Syntax checks
alone do not establish this editorial quality.

**Compatibility:** `production.json` is for a complete new Agent production; Web AI output and
legacy sources still use the existing two-file contract. Existing media retain their behavior
without the optional shot and clip attributes. A structural production check does not certify
source authenticity, editorial quality, or good pacing.
