Create a narrated HTML explainer video with deliberate camera language and teaching actions.
Choose source-led reporting, tutorial, interactive, or presentation treatment from the subject
and requested outcome.

Topic: {{TOPIC}}
Audience: {{AUDIENCE}}
Tone: {{TONE}}
Preferred scene count: {{SCENE_COUNT}}
Language: {{LANGUAGE_INSTRUCTION}}
Aspect ratio: {{ASPECT_RATIO}}. {{ASPECT_RATIO_INSTRUCTION}}
Additional requirements: {{NOTES}}

## Creative direction (not additional output files)
- Use source-led reporting for news and factual product/repository coverage, `tutorial` for
  teaching a workflow, `interactive` for a mechanism or changing graph, and `presentation` when
  a static visual comparison fits the explanation.
- In tutorial mode show the relevant input, operation, and visible result. Include code or a
  revision when needed to explain the task; let the material determine the sequence.
- In interactive mode use time-deterministic diagrams, not an actual input listener: this
  delivers a seekable MP4 demonstration rather than a clickable web application.
- Do not invent product features, real screenshots, benchmarks, or executed results.
  Label code/editor/chat reproductions as `操作示意` when not real captures.
- Default content theme is light paper; allow warm, science, and dark-local panels according
  to the topic. The Shell background itself is fixed in the current version, so `#stage`
  and scene full-frame backgrounds must remain transparent.
- Treat the Shell caption and chapter overlays as reserved space: do not draw footers,
  chapter progress, captions or timecodes in `body.html`.

### News and source-led coverage

For news, product announcements, or repository coverage, select and inspect original sources
before drafting narration. Establish publication/event dates and the scope of the evidence.
Plan each key spoken detail alongside a concrete source visual: the relevant article capture,
original chart, product screenshot, or actual repository demo clip. Let the explanation move
between useful source details instead of holding a generic title card through every story.
Scenes are chapters and may contain several visual shots. Change focus when the explanation
changes, while leaving enough time to read a source crop or understand a result. Do not repeat
full narration on screen or force a cut at every sentence. Choose useful media by claim coverage,
rather than fitting a fixed asset count.
Real source material should normally carry most of the story footage when available and permitted.
Generated artwork can supplement the explanation; it does not stand in for a real screenshot.

If tools and reuse permissions allow acquisition, use descriptive local asset paths. If binary
assets cannot be acquired in this Web AI workflow, create explicit `media/` slots and identify
their intended source URL/excerpt in nearby HTML comments. Do not claim those files exist or
invent a product screen or demonstration. Preserve the original source appearance and meaningful
context. Keep attribution, dates, and relevant units legible in the scene content. Distinguish
an inaccessible post's archive from the original. Moving demos should use a local muted MP4/WebM;
time-sensitive GIFs must be converted before final rendering.

This Web AI planning adds no output files or metadata fields. Do not output `production.json`,
download scripts, or binary assets. Return only the two files specified below.

## Output contract

Author only `scenes.json` and `body.html`. An optional `media/` folder may hold local assets.
`body.html` must be one complete HTML document: it must begin with `<!doctype html>`, contain
`<html>`, `<head>`, and `<body>`, and end with `</body></html>`. Never return an HTML fragment,
truncate the document, or use ellipses/placeholders for omitted markup or CSS.
Keep the implementation compact enough to return in full: reuse CSS classes and shared components.
If output space is limited, reduce decorative detail rather than omitting scenes, styles, or closing
tags.

- Make `scenes.json` contain at least two scenes. Start with `id: "intro"` and end with
  `id: "outro"`. Count both scenes within the preferred scene count.
- Write the intro as a knowledge-show cold open: begin directly with the subject, a concrete fact,
  a tension, or the central editorial question. Write the outro as a concise synthesis or
  forward-looking implication. Do not force a greeting, sign-off, or thanks unless the requested
  tone explicitly calls for a visible presenter.
- Give every scene a unique lowercase `id`, a short `category`, and one natural, grammatically
  complete `narration` string. This is the Web AI submission format: do not split the narration,
  invent subtitle ids, or output a `segments` object. Studio converts the string into canonical
  subtitle segments before it writes the project to disk, so the saved project still has only one
  spoken-text schema. Keep a
  category within 12 CJK characters or about 24 Latin characters; use a compact chapter label such
  as `示例`, `核心流程`, `Example`, or `Application` rather than a sentence. For a 9:16 project,
  use only 2-3 CJK characters or one short English word of at most 8 letters.
- Put every visible title, label, diagram, chart, and explanatory element in `body.html`.
- Add one `<section class="content-scene" data-scene="id">` for every scene. Do not hard-code an
  initial `active` or `is-active` class; the stable shell controls scene visibility.
- Keep all project CSS inside a `<style>` element in `body.html`.
- Scope backgrounds and document-level layout to `#stage` or scene elements. Do not style `html`,
  `body`, shell controls, captions, or chapter elements because source styles are embedded into the
  stable shell document.
- Do not add keyboard handlers, scene navigation buttons, or scene-switching events. The stable
  shell and Studio Source Editor own scene selection and playback.

### Narration voice

Default to an invisible editorial narrator, not an AI assistant talking about how it will answer a
user. Make the subject itself the grammatical focus. Each scene should advance through a concrete
claim, named evidence or examples, and the practical consequence. Allow evidence-backed editorial
judgment, but avoid empty advice, fake collaboration, and meta commentary about the presentation.

Unless the requested format is explicitly a tutorial, interview, or presenter-led show, avoid
first- and second-person framing such as “I”, “we”, “you”, `我`, `我们`, and `你`, unless an
explicitly requested writing reference calls for that voice. Adapt an available reference to
spoken language; do not claim to have read a missing skill or invent personal experience. Silently rewrite
assistant-like formulas such as `接下来我们`, `让我们`, `我们不只…而是…`, `不要只问…而要问…`,
`值得注意的是`, `可以看到`, `不难发现`, `总的来说`, and `希望能帮助你`. Express the actual
claim in direct, specific language rather than mechanically deleting phrases.

For news, open with the interesting development and speak in short, natural sentences. Avoid
giving every story the same "second item / third item / shared trend" framing, generic AI-era
conclusions, or a string of verification reminders. Keep dates and routine qualifications in
visual source labels; explain them aloud when they materially affect the story. Attribute
company-reported results and distinguish announced, demonstrated, and available products.
Before delivery, read the narration as speech and verify that its key details match what is shown.

For short technology coverage, choose one main detail per story and give it enough explanation;
do not fit every story into the same background/features/impact/reminder outline. Divide the work
between sound and image: speak the meaningful change, cause, or tradeoff, while readable source
visuals retain exact figures, dates, names, and test conditions. Keep units and comparison scope
clear in speech. Explain limitations aloud when they materially change the claim, including
unreleased availability; for audio-only output, retain all information needed to understand it.
Connect sentences through concrete causes or consequences. Casual phrases such as "that's wild"
or "the battery won't like that" do not replace missing explanation. During revision, remove
sentences whose deletion loses no information and generic judgments that fit unrelated stories.
Keep natural sentence-length variation. Leave time to read source visuals; if a draft runs long,
cut secondary detail before increasing delivery speed. Word counts estimate duration and do not
establish a natural voice. Do not claim to have listened to audio that was never generated.

### Studio-editable scene objects

Author the selected aspect ratio on its fixed design canvas: `1280x720` for `16:9` or `720x1280`
for `9:16`. Studio scales that canvas for smaller previews. Do not build a responsive orientation
switch.

Put one `<div class="scene-canvas">` directly inside every scene. Make it `position:absolute` with
`inset:0`. Every top-level visual object inside that canvas must:

- have a document-wide unique `data-studio-id`, such as `intro-title` or `process-diagram`;
- have `data-studio-kind="text"`, `"group"`, `"shape"`, `"image"`, or `"video"`;
- use inline `position:absolute` plus pixel `left`, `top`, `width`, and `height` values;
- preferably end at or above the shell-overlay boundary: `top + height <= 540` on landscape or
  `top + height <= 960` on portrait. This is a composition recommendation rather than a validity
  rule; captions remain layered above source media and overlap is judged in Studio preview.

The default is a stable composition without object-by-object entrances. Add deterministic motion
only when it directs attention to a meaningful change. A top-level object may use one shell preset through
`data-motion="fade"`, `"rise"`, `"slide-left"`, `"wipe-left"`, `"zoom-in"`,
`"ken-burns-in"`, `"pan-left"`, `"pan-right"`, or `"pulse-once"`. Optional normalized
`data-motion-delay` and `data-motion-duration` values control the entrance window. Use no more than
two `data-motion` entrance presets in one scene. This limit does not ban scripted
deterministic instructional motion within a grouped chart, terminal, or browser mockup.
Any such module must be driven by the Shell clock through `renderAtTime()` and must
not start its own animation loop. Prefer stable reading holds over decorative motion.

Studio uses those stable ids and inline geometry to select, drag, resize, edit, insert, and delete
objects while writing the result back to `body.html`. A top-level `group` may use Grid, Flexbox,
SVG, or normal document flow internally, so charts and diagrams do not need absolute positioning
for every child. Its internal content must stay inside the declared group box; reduce copy, spacing,
or type size instead of allowing overflow. Give directly editable text its own top-level
`data-studio-kind="text"` object. Keep object ids stable when revising an existing file.

### Optional media slots

Use HTML, CSS, and inline SVG for authored explanations and annotations. For real source material,
reference a descriptive project-local slot such as
`media/product-cutaway.webp` or `media/process-demo.mp4`. The Studio Source Editor will show that
path as missing so the user can upload, paste, or replace the corresponding file later.

Do not claim that a binary media file is included in the two code blocks. Do not invent opaque
filenames or unstable hotlinked URLs, and do not embed large base64 payloads. Give images useful
`alt` text. Write video elements as muted visual material, for example:

```html
<video src="media/process-demo.mp4" muted playsinline loop preload="metadata"></video>
```

The stable shell synchronizes project video to scene-relative time; narration remains the final
audio track. Prefer MP4/WebM for moving media. Avoid animated GIF for timing-sensitive motion
because GIF playback follows wall-clock time and cannot be deterministically sought during render.
Optional video attributes `data-media-in="2"`, `data-media-out="8"`, `data-media-start="3"`,
and `data-media-rate="1"` select source seconds 2–8, beginning at scene second 3 at normal speed.
Before that start the clip is hidden; after its interval it holds the last frame, or loops within
the selected interval when `loop` is present. Omit these attributes for ordinary scene-time playback.

Use this complete `body.html` structure as the integration pattern. Expand it with one full section
for every scene instead of omitting repeated sections:

```html
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Presentation video</title>
    <style>
      #stage {
        background: transparent;
        color: #173b3d;
      }
      .content-scene {
        position: absolute;
        inset: 0;
        overflow: hidden;
      }
      .scene-canvas {
        position: absolute;
        inset: 0;
      }
    </style>
  </head>
  <body>
    <section class="content-scene" data-scene="intro">
      <div class="scene-canvas">
        <h1
          data-studio-id="intro-title"
          data-studio-kind="text"
          style="position:absolute;left:90px;top:90px;width:920px;height:110px"
        >Opening title</h1>
      </div>
    </section>

    <section class="content-scene" data-scene="next-scene">
      <div class="scene-canvas">
        <h2
          data-studio-id="next-title"
          data-studio-kind="text"
          style="position:absolute;left:90px;top:70px;width:900px;height:80px"
        >Next idea</h2>
      </div>
    </section>

    <section class="content-scene" data-scene="outro">
      <div class="scene-canvas">
        <h2
          data-studio-id="outro-title"
          data-studio-kind="text"
          style="position:absolute;left:90px;top:120px;width:900px;height:90px"
        >Closing takeaway</h2>
      </div>
    </section>
  </body>
</html>
```

The `data-scene` values must exactly match the ids and order in `scenes.json`. Never put `active`,
`is-active`, captions, a progress bar, or playback controls in this markup. Keep Studio-editable
objects out of the bottom 20% caption and chapter area.

## Visual direction

Use a bright editorial blackboard/newspaper style rather than a dark technology theme. Build from
pale blue, mint, seafoam, and warm off-white surfaces with dark teal or blue-green ink. Use one
restrained coral, yellow, or medium-blue accent when emphasis is needed. Avoid dark navy or black
full-frame backgrounds, neon glows, glassmorphism, and high-contrast cyberpunk styling.

Design the result like a coherent educational video:
one focal point per shot, precise narration-to-visual correspondence, clear hierarchy,
and a dominant demonstrable change. For software tutorials show a readable terminal, code
editor, browser, cursor, or output window when relevant. For scientific mechanisms show
diagrams, charts, changes in parameters, and causal consequences. Avoid decorative card
walls, tiny pseudo-code, irrelevant dashboard chrome, and multiple competing focal points.

For a capture/demo-led scene, optional `data-frame="media"` on its section selects a plain Shell
frame without the grid, outer border, or chapter rail. Keep important details clear of the lower
13% where compact backed captions appear. This is an HTML attribute, not a new output file or
manifest field. Without it, retain the standard layout below.

The stable shell already draws the soft gray-green graph-paper grid behind source content and the
selected-canvas frame border over the finished video.
Keep full-frame scene CSS backgrounds transparent. Real source images, figures, and clips may
fill the authored frame; transparent CSS does not require shrinking them into cards or preserving
visible grid behind every image. Keep relevant details clear of Shell overlays. Use very light
translucent blue, mint, seafoam, or warm-white tints on authored content surfaces.
Do not recreate the outer border, full-frame grid, captions, or chapter rail in `body.html`.

Design only for the selected immutable `{{ASPECT_RATIO}}` stage; do not add a responsive orientation
switch. A 9:16 project should use a single vertical reading flow, stacked diagrams, shorter visible
copy, and at most two compact columns when the content truly needs them. A 16:9 project may use
wider presentation layouts. Make the same CSS fit smaller Studio previews. Treat typography as
presentation text, not poster lettering:

- Keep a normal scene title at or below `clamp(36px, 4vw, 64px)`. A title sharing the frame with two
  or more columns should stay at or below `clamp(32px, 3.5vw, 56px)`.
- Reserve `clamp(44px, 5.2vw, 88px)` only for a short intro headline. Do not use a 90-120px heading
  on ordinary content scenes.
- Keep body copy at or below `clamp(18px, 1.6vw, 28px)` and repeated card/diagram labels at or below
  `clamp(18px, 1.8vw, 30px)`. Use no more than two title lines and keep Chinese title lines concise.
- Reduce font size or copy length when text wraps unexpectedly; never let text push another visual
  outside the scene.

Size repeated columns from their container rather than from the browser viewport. For two- or
three-column layouts, use Grid with `minmax(0, 1fr)` and give children `min-width: 0`; do not assign
each card a `vw` width. Keep gaps inside the grid's available width. For example:

```css
.scene-title {
  font-size: clamp(36px, 4vw, 64px);
  line-height: 1.08;
}
.three-column {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(16px, 2vw, 32px);
}
.three-column > * {
  min-width: 0;
}
```

Prefer keeping source content in the top 75% of the frame. The shell overlays captions and chapters
across the bottom 25%, so any source content placed there may be covered. This is intentional and
should remain visible in Studio preview rather than causing a build failure. The stable video shell
owns captions, the compact chapter rail, playback, timing, rendering, and deterministic scene
transitions. Do not recreate those elements in `body.html`.

Prefer HTML, CSS, and SVG. Avoid infinite or wall-clock CSS animation. Use shell motion presets or
derive visual state from composition time so preview scrubbing and frame rendering reproduce the
same image. If JavaScript is unnecessary, include no `<script>` at all. A normal
`<script>` is invalid. If an active Canvas or WebGL visual is genuinely useful, include exactly one
inline `<script type="module">` in `body.html`; do not use a `src` attribute. Pin imported dependency
versions, derive every frame from the provided absolute time, and do not start an independent
`requestAnimationFrame` loop.

When a module is needed, insert this interface immediately before the document's closing `</body>`:

```html
<script type="module">
  let host;

  export async function mount({ root }) {
    host = root.querySelector('[data-scene="intro"]');
  }

  export function renderAtTime(seconds, { sceneProgress }) {
    if (!host) return;
    host.style.setProperty("--scene-progress", String(sceneProgress));
  }

  export function destroy() {
    host = null;
  }
</script>
```

Before returning the two files, verify: the first scene is `intro` with a direct editorial opening;
the last scene is `outro` with a concise synthesis; `body.html` runs from `<!doctype html>` through
`</html>` without omitted sections or styles; every scene has one matching section and one
`.scene-canvas`; every top-level object has a unique `data-studio-id`, a valid `data-studio-kind`,
and inline absolute geometry; no scene starts active; CSS does not target `html` or `body`;
objects preferably remain above the 75% shell-overlay boundary; headings respect the size limits; every
multi-column group fits inside its object bounds without horizontal overflow or clipped children;
and an optional script is one inline module exporting both `mount()` and `renderAtTime()`.

## Delivery

Return exactly two fenced code blocks with filenames: `scenes.json` in a `json` fence and
`body.html` in an `html` fence. The `body.html` fence must contain the complete document from
`<!doctype html>` through `</html>`, with no omitted sections, truncation, or ellipses.

<!-- HTML_VIDEO_DIRECTOR_V2 -->
