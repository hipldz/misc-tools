---
name: html-edge-tts-video
description: Create locally rendered narrated explainers, software tutorials, source-led technology reports, and presentation videos from scenes.json and body.html. Use for acquiring and editing project-local source media, aligning narration with visible evidence, generating Edge TTS or Azure Speech narration and captions, and rendering an MP4 in Simplified Chinese or US English.
---

# HTML TTS Video

Read `docs/agent-skill.md` completely before performing any task with this skill. Follow it as the
single canonical agent workflow and constraint reference.

For treatment, camera language, and editorial review read `docs/video-director.md`.
For a local Agent producing a complete video, also read [Agent production](docs/agent-production.md):
it covers real-media acquisition, the project-local `production.json` plan, cue-linked shots,
clip timing, and `check --production`. These supplement the two-file source contract;
Web AI still returns exactly `scenes.json` and `body.html`.

For news roundups and factual product or repository coverage, use the director guide's
source-led reporting workflow: inspect and acquire useful evidence first, then design shots
and narration together. A source link or headline alone does not demonstrate a product's behavior.
Honor an available user-specified writing reference.
For short technology or AI news narration, also read
[write-tech-narration](.agents/skills/write-tech-narration/SKILL.md) before drafting or revising the script.

Resolve material gaps in the brief using the workflow's defaults and existing authorization.
Do not introduce a routine confirmation gate. Media commands do not grant network access;
follow the current environment's permissions and resource limits.

<!-- HTML_VIDEO_DIRECTOR_V2 -->
