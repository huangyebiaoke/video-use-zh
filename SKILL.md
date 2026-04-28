---
name: video-use
description: Edit any video by conversation. Transcribe, cut, color grade, generate overlay animations, burn subtitles — for talking heads, montages, tutorials, travel, interviews. No presets, no menus. Ask questions, confirm the plan, execute, iterate, persist. Production-correctness rules are hard; everything else is artistic freedom.
---

# Video Use

## Principle

1. **LLM reasons from raw transcript + on-demand visuals.** The only derived artifact that earns its keep is a packed phrase-level transcript (`takes_packed.md`). Everything else — filler tagging, retake detection, shot classification, emphasis scoring — you derive at decision time.
2. **Audio is primary, visuals follow.** Cut candidates come from speech boundaries and silence gaps. Drill into visuals only at decision points.
3. **Ask → confirm → execute → iterate → persist.** Never touch the cut until the user has confirmed the strategy in plain English.
4. **Generalize.** Do not assume what kind of video this is. Look at the material, ask the user, then edit.
5. **Artistic freedom is the default.** Every specific value, preset, font, color, duration, pitch structure, and technique in this document is a *worked example* from one proven video — not a mandate. Read them to understand what's possible and why each worked. Then make your own taste calls based on what the material actually is and what the user actually wants. **The only things you MUST do are in the Hard Rules section below.** Everything else is yours.
6. **Invent freely.** If the material calls for a technique not described here — split-screen, picture-in-picture, lower-third identity cards, reaction cuts, speed ramps, freeze frames, crossfades, match cuts, L-cuts, J-cuts, speed ramps over breath, whatever — build it. The helpers are ffmpeg and PIL. They can do anything the format supports. Do not wait for permission.
7. **Verify your own output before showing it to the user.** If you wouldn't ship it, don't present it.

## Hard Rules (production correctness — non-negotiable)

These are the things where deviation produces silent failures or broken output. They are not taste, they are correctness. Memorize them.

1. **Subtitles are applied LAST in the filter chain**, after every overlay. Otherwise overlays hide captions. Silent failure.
2. **Per-segment extract → lossless `-c copy` concat**, not single-pass filtergraph. Otherwise you double-encode every segment when overlays are added.
3. **30ms audio fades at every segment boundary** (`afade=t=in:st=0:d=0.03,afade=t=out:st={dur-0.03}:d=0.03`). Otherwise audible pops at every cut.
4. **Overlays use `setpts=PTS-STARTPTS+T/TB`** to shift the overlay's frame 0 to its window start. Otherwise you see the middle of the animation during the overlay window.
5. **Master SRT uses output-timeline offsets**: `output_time = word.start - segment_start + segment_offset`. Otherwise captions misalign after segment concat.
6. **Never cut inside a word.** Snap every cut edge to a word boundary from the transcript.
7. **Pad every cut edge.** Working window: 30–200ms. FunASR timestamps are precise — padding still recommended for safety. Tighter for fast-paced, looser for cinematic.
8. **Word-level verbatim ASR only.** Never SRT/phrase mode (loses sub-second gap data). Never normalized fillers (loses editorial signal).
9. **Cache transcripts per source.** Never re-transcribe unless the source file itself changed.
10. **Parallel sub-agents for multiple animations.** Never sequential. Spawn N at once via the `Agent` tool; total wall time ≈ slowest one.
11. **Strategy confirmation before execution.** Never touch the cut until the user has approved the plain-English plan.
12. **All session outputs in `<videos_dir>/edit/`.** Never write inside the `video-use/` project directory.
13. **Subtitle timeline must match the EDL.** Generate subtitles AFTER the EDL is locked, using the final segment offsets. If the EDL changes after subtitle generation, regenerate the SRT — never reuse stale subtitles.
14. **Self-eval before delivery.** Extract and inspect frame screenshots at cut boundaries, mid-points, start/end. Check for visual glitches, subtitle desync, aspect ratio issues. Never show the user a preview without passing self-eval.
15. **Catalog all project assets.** Inventory videos, audio, photos, and text files in the project folder. Photos are first-class assets — integrate them with Ken Burns motion, slideshows, or as visual anchors.

Everything else in this document is a worked example. Deviate whenever the material calls for it.

## Directory layout

The skill lives in `video-use/`. User footage lives wherever they put it. All session outputs go into `<videos_dir>/edit/`.

```
<videos_dir>/
├── <source files, untouched>
└── edit/
    ├── project.md               ← memory; appended every session
    ├── takes_packed.md          ← phrase-level transcripts, the LLM's primary reading view
    ├── edl.json                 ← cut decisions
    ├── transcripts/<name>.json  ← cached FunASR JSON
    ├── animations/slot_<id>/    ← per-animation source + render + reasoning
    ├── clips_graded/            ← per-segment extracts with grade + fades
    ├── master.srt               ← output-timeline subtitles
    ├── downloads/               ← yt-dlp outputs
    ├── verify/                  ← debug frames / timeline PNGs
    ├── preview.mp4
    └── final.mp4
```

## Setup

First-time install lives in `install.md` (clone, deps, ffmpeg, skill registration). Don't re-run it every session; on cold start just verify:

- `ffmpeg` + `ffprobe` on PATH.
- Python deps installed (`uv sync` or `pip install -e .` inside the repo). This includes `funasr`, `torch`, `torchaudio` for local transcription — no API key needed.
- `yt-dlp`, `manim`, Remotion installed only on first use.
- This skill vendors `skills/manim-video/`. Read its SKILL.md when building a Manim slot.

Helpers (`helpers/transcribe.py`, `helpers/render.py`, etc.) live alongside this SKILL.md. Resolve their paths relative to the directory containing this file — the skill is typically symlinked at `~/.hermes/skills/video-use/`.

## Helpers

- **`transcribe.py <video>`** — single-file Scribe call. `--num-speakers N` optional. Cached.
- **`transcribe_batch.py <videos_dir>`** — 4-worker parallel transcription. Use for multi-take.
- **`pack_transcripts.py --edit-dir <dir>`** — `transcripts/*.json` → `takes_packed.md` (phrase-level, break on silence ≥ 0.5s).
- **`timeline_view.py <video> <start> <end>`** — filmstrip + waveform PNG. On-demand visual drill-down. **Not a scan tool** — use it at decision points, not constantly.
- **`render.py <edl.json> -o <out>`** — per-segment extract → concat → overlays (PTS-shifted) → subtitles LAST. `--preview` for 720p fast. `--build-subtitles` to generate master.srt inline.
- **`grade.py <in> -o <out>`** — ffmpeg filter chain grade. Presets + `--filter '<raw>'` for custom.

For animations, create `<edit>/animations/slot_<id>/` with `Bash` and spawn a sub-agent via the `Agent` tool.

## The process

1. **Inventory.** `ffprobe` every source file. `transcribe_batch.py` on videos/audio. `pack_transcripts.py` to produce `takes_packed.md`. Sample one or two `timeline_view`s for a visual first impression. Catalog **all asset types** in the project folder:
   - **Video** (`.mp4`, `.mov`, `.mkv`): primary clips, transcribe for speech
   - **Audio** (`.mp3`, `.wav`, `.m4a`): BGM, voiceover, sound effects
   - **Photos** (`.jpg`, `.png`, `.heic`): insert as stills, Ken Burns zoom/pan, slideshow sequences
   - **Text** (`.txt`, `.md`, `.docx`): narration scripts, reference material for transcript proofreading
   
   Note resolution, orientation (portrait/landscape), and duration for each asset. Pre-compress 4K video to 1080p if final output is 1080p.
   
   **Supplemental asset detection (during Inventory):**
   - **Missing BGM?** If the project folder has no audio files and the video would benefit from music (narrative, travel, montage, documentary), recommend 2–4 BGM options to the user. Describe each: mood, tempo, genre, duration. Sources: Suno API (generate original), free music libraries (YouTube Audio Library, Pixabay Music), or ask the user to provide. Once the user picks one, download or generate it into `<edit>/audio/`.
   - **Missing location photos?** When the transcript mentions specific places (scenic spots, landmarks, cities), search the web for reference photos of those locations. Present 3–5 options to the user (with source URL and preview description). Once confirmed, download them into the project folder for use as B-roll or establishing shots.
   - **Memes/reaction images (表情包)?** When the transcript contains humorous moments, sarcastic remarks, emotional peaks, or internet-style commentary, suggest relevant memes or reaction images. Search for Chinese memes (表情包), GIFs, or reaction images that match the tone. Present 2–3 options with descriptions. Download approved ones as transparent PNGs or short GIFs→MP4 for overlay use.
   - **Movie/TV clips by quote (影视片段):** When the transcript references a well-known movie quote, cultural meme, or a sentiment that matches a famous scene, search quote-based clip databases (Yarn.co / getyarn.io, PlayPhrase.me) for matching video clips. These are short (1–5s) cuts from movies/TV shows — perfect as reaction inserts, punchline enhancers, or cultural callbacks. Search by exact phrase or keyword in English/Chinese. Present 2–3 options. Download the .mp4 clip into the project folder for overlay or cutaway use.
   - **Web reference images:** for objects, animals, products, concepts mentioned in the transcript that don't have footage — search and present options. Examples: a specific food, a gadget, an animal species, a landmark the speaker references.
   - **What to supplement:** BGM/SFX, landmark photos, memes/表情包, movie/TV clips (影视片段), GIF reaction images, contextual imagery, text reference material. **Never download or add assets without explicit user approval.**
2. **Propose editing plan (MANDATORY — wait for confirmation).** Present a clear plain-English plan covering:
   - **Structure**: narrative beats, target runtime, pacing
   - **Cut strategy**: which clips go where, what gets trimmed, what gets dropped
   - **Photo integration**: where photos appear, Ken Burns motion (zoom in/out, pan), duration per photo
   - **Transitions**: crossfade (1s default), dissolve, zoom cut, whip pan, fade-to-black — specify per cut point
   - **Audio plan**: BGM track(s), voiceover placement, volume mixing levels
   - **Subtitle plan**: chunking style, font, placement
   - **Color grade**: mood direction
   
   **DO NOT start cutting until the user explicitly approves the plan.** If the user says "go ahead" / "ok" / "开始吧", proceed. Otherwise refine.
3. **Transcript proofreading (MANDATORY for Chinese/非English).** Read every `transcripts/*.json` file's `text` field carefully. Identify and fix:
   - **Place names** (地名): search the web to confirm correct characters (e.g., "末六宫山" → "莫六公山")
   - **Names/nicknames** (人名/网名): cross-reference with context
   - **Homophone errors** (同音字): "左别抖" → "手别抖", "一个地度" → "一个地方"
   - **Garbled ASR** (乱码): "水风灯/神针水分钟水分动" → "手电筒"
   - **Contextually wrong words**: "墓穴" → "洞穴" (exploring a cave, not a tomb)
   
   Fix both the `text` field AND individual `words[].text` entries in each JSON, since `build_master_srt` reconstructs subtitles from word-level data. For heavily garbled sections where word-by-word fixes are impractical, overwrite the word entries in that timestamp range to produce correct text.
   
   **Web search strategy**: when you see a suspicious place name, search it immediately. If the top results show a different character combination, that's likely the correct one. Example: search "清远 末六宫山" → results show "莫六公山" → fix it.
4. **Pre-scan for problems.** One pass over `takes_packed.md` to note verbal slips, obvious mis-speaks, or phrasings to avoid. Plain list, feed into the editor brief.
5. **Execute.** Produce `edl.json` via the editor sub-agent brief. Drill into `timeline_view` at ambiguous moments. Build animations in parallel sub-agents. Apply grade per-segment.
6. **Subtitle alignment (CRITICAL — before compositing).** 
   - Generate `master.srt` from the transcript JSON files **using the EDL's final timeline offsets**, NOT the original source timestamps.
   - The formula is: `output_time = word.start - segment_start + segment_offset` where `segment_offset` is the cumulative duration of all preceding segments in the EDL.
   - **If you cut/trim/reorder clips AFTER generating subtitles, you MUST regenerate `master.srt` to match the new timeline.** Subtitle-video desync is the most common silent failure.
   - Safer workflow: **build subtitles as the LAST step before final compositing**, after the EDL is locked. Never burn subtitles into an intermediate clip that will be re-cut.
   - Verify: pick 3 random points in the video, check that the subtitle text matches the spoken content at that timestamp.
7. **Preview.** `render.py --preview`.
8. **Self-eval (MANDATORY — before showing the user).**
   - **Frame sampling**: extract screenshots at key points — first 2s, last 2s, every cut boundary (±1.5s), and 2–3 evenly spaced mid-points. Use `ffmpeg -ss <time> -i <file> -vframes 1 <output.jpg>` for each checkpoint.
   - **Visual check**: examine each screenshot for:
     - Visual discontinuity / flash / jump at cuts
     - Photo aspect ratio mismatches (letterboxing, stretching)
     - Subtitle hidden behind overlays or cut off at edges
     - Subtitle text misaligned with expected audio content
     - Color grade inconsistencies between segments
   - **Subtitle desync check**: at 3 random sampled timestamps, verify the burned-in subtitle text matches what the transcript says should be spoken at that point.
   - **Audio check**: run `ffprobe` to verify duration matches EDL expectation, check for audio pop at boundaries.
   - If anything fails: fix → re-render → re-eval. **Cap at 3 self-eval passes** — if issues remain after 3, flag them explicitly to the user rather than looping forever. Only present the preview once self-eval passes.
9. **Iterate + persist.** Natural-language feedback, re-plan, re-render. Never re-transcribe. Final render on confirmation. Append to `project.md`.

## Photo integration

Photos are first-class assets alongside video clips. Treat them as visual anchors for narration, transitions between beats, or B-roll stand-ins when no video footage exists.

**Static insertion:** place a photo as a `render.mp4` segment. Duration: 2–5s depending on context. For voiceover accompaniment, photo duration ≥ narration length covering that beat.

**Ken Burns motion (zoom + pan):** use ffmpeg `zoompan` filter or PIL to generate a video from a still:
```bash
# Slow zoom in (center), 4s at 30fps
ffmpeg -loop 1 -i photo.jpg -vf "zoompan=z='min(zoom+0.002,1.5)':d=120:s=1920x1080:fps=30" -t 4 -c:v libx264 -pix_fmt yuv420p photo_zoom.mp4

# Pan left to right, 3s
ffmpeg -loop 1 -i photo.jpg -vf "zoompan=z='1.3':x='min(x+8,480)':y='ih/2-ih/2':d=90:s=1920x1080:fps=30" -t 3 -c:v libx264 -pix_fmt yuv420p photo_pan.mp4
```

**Slideshow sequences:** multiple photos in rapid succession (0.5–1.5s each) create montage energy. Crossfade between them:
```bash
# Crossfade 1s between two photos
ffmpeg -loop 1 -t 3 -i p1.jpg -loop 1 -t 3 -i p2.jpg -filter_complex \
  "[0]fade=t=out:st=2:d=1[a];[1]fade=t=in:st=0:d=1[b];[a][b]overlay" slideshow.mp4
```

**Aspect ratio handling:** 
- Landscape photos in 16:9 video: fit naturally, no letterboxing
- Portrait photos in 16:9 video: blur-fill background (duplicate, scale up, Gaussian blur behind) or letterbox with colored bars
- Mixed orientation in same sequence: normalize to 16:9 canvas first

**When to use photos:**
- Establish context before/after a location reveal
- Replace missing footage for a specific moment
- Create visual variety in long monologue sections
- Show before/after comparisons side-by-side

**Memes and reaction images (表情包):**
- Download as PNG with transparency when possible; convert GIF→MP4 for animated overlays
- Overlay on top of video at emotional beats using ffmpeg overlay filter with proper positioning
- Typical placement: center-bottom or corner, 2–3s duration
- Scale to ~25–35% of frame width — noticeable but not blocking the main content
- Use `colorchannelmixer` or `format=yuva444p` for transparency support
- If the meme has a solid background, use `colorkey` or `chromakey` to remove it

## Transitions

Specify transitions per cut point in the EDL. Use ffmpeg filters:

**Crossfade (default, 1s):** smooth dissolve between two video segments.
```bash
xfade=transition=fade:duration=1:offset=<seg1_duration - 1>
```

**Dissolve variants:** `fadeblack` (fade through black, dramatic), `fadewhite` (flash transition), `wipeleft`/`wiperight` (directional wipe).

**Zoom cut:** quick zoom into the next clip's first frame for energy.

**Cut on motion:** hide the cut within camera movement or subject motion — no explicit filter needed, just time the cut to coincide with peak motion.

**Hard cut:** no transition. Best for fast-paced sequences, comedy timing, or rhythm cuts.

**Transition placement rules:**
- Only add transitions at major beat boundaries, not every cut
- Fast-paced content: hard cuts + occasional crossfade
- Documentary/narrative: dissolve or fade between beats
- Photo → video or video → photo: always crossfade (≥0.5s)
- Photo → photo: crossfade or dissolve (0.3–1s)

## Cut craft (techniques)

- **Audio-first.** Candidate cuts from word boundaries and silence gaps.
- **Preserve peaks.** Laughs, punchlines, emphasis beats. Extend past punchlines to include reactions — the laugh IS the beat.
- **Speaker handoffs** benefit from air between utterances. Common values: 400–600ms. Less for fast-paced, more for cinematic. Taste call.
- **Audio events as signals.** `(laughs)`, `(sighs)`, `(applause)` mark beats. Extend past them.
- **Silence gaps are cut candidates.** Silences ≥400ms are usually the cleanest. 150–400ms phrase boundaries are usable with a visual check. <150ms is unsafe (mid-phrase).
- **Example cut padding** (the launch video shipped with this): 50ms before the first kept word, 80ms after the last. Tighter for montage energy, looser for documentary. Stay in the 30–200ms working window (Hard Rule 7).
- **Never reason audio and video independently.** Every cut must work on both tracks.

## The packed transcript (primary reading view)

`pack_transcripts.py` reads all `transcripts/*.json` and produces one markdown file where each take is a list of phrase-level lines, each prefixed with its `[start-end]` time range. Phrases break on any silence ≥ 0.5s OR speaker change. This is the artifact the editor sub-agent reads to pick cuts — it gives word-boundary precision from text alone at 1/10 the tokens of raw JSON.

Example line:
```
## C0103  (duration: 43.0s, 8 phrases)
  [002.52-005.36] S0 Ninety percent of what a web agent does is completely wasted.
  [006.08-006.74] S0 We fixed this.
```

## Editor sub-agent brief (for multi-take selection)

When the task is "pick the best take of each beat across many clips," spawn a dedicated sub-agent with a brief shaped like this. The structure is load-bearing; the pitch-shape example is not.

```
You are editing a <type> video. Pick the best take of each beat and 
assemble them chronologically by beat, not by source clip order.

INPUTS:
  - takes_packed.md (time-annotated phrase-level transcripts of all takes)
  - Product/narrative context: <2 sentences from the user>
  - Speaker(s): <name, role, delivery style note>
  - Expected structure: <pick an archetype or invent one>
  - Verbal slips to avoid: <list from the pre-scan pass>
  - Target runtime: <seconds>

Common structural archetypes (pick, adapt, or invent):
  - Tech launch / demo:   HOOK → PROBLEM → SOLUTION → BENEFIT → EXAMPLE → CTA
  - Tutorial:             INTRO → SETUP → STEPS → GOTCHAS → RECAP
  - Interview:            (QUESTION → ANSWER → FOLLOWUP) repeat
  - Travel / event:       ARRIVAL → HIGHLIGHTS → QUIET MOMENTS → DEPARTURE
  - Documentary:          THESIS → EVIDENCE → COUNTERPOINT → CONCLUSION
  - Music / performance:  INTRO → VERSE → CHORUS → BRIDGE → OUTRO
  - Or invent your own.

RULES:
  - Start/end times must fall on word boundaries from the transcript.
  - Pad cut boundaries (working window 30–200ms).
  - Prefer silences ≥ 400ms as cut targets.
  - Unavoidable slips are kept if no better take exists. Note them in "reason".
  - If over budget, revise: drop a beat or trim tails. Report total and self-correct.

OUTPUT (JSON array, no prose):
  [{"source": "C0103", "start": 2.42, "end": 6.85, "beat": "HOOK",
    "quote": "...", "reason": "..."}, ...]

Return the final EDL and a one-line total runtime check.
```

## Color grade (when requested)

Your job is to **reason about the image**, not apply a preset. Look at a frame (via `timeline_view`), decide what's wrong, adjust one thing, look again.

Mental model is ASC CDL. Per channel: `out = (in * slope + offset) ** power`, then global saturation. `slope` → highlights, `offset` → shadows, `power` → midtones.

**Example filter chains** (`grade.py` has `--list-presets`; use them as starting points or mix your own):

- **`warm_cinematic`** — retro/technical, subtle teal/orange split, desaturated. Shipped in a real launch video. Safe for talking heads.
- **`neutral_punch`** — minimal corrective: contrast bump + gentle S-curve. No hue shifts.
- **`none`** — straight copy. Default when the user hasn't asked.

For anything else — portraiture, nature, product, music video, documentary — invent your own chain. `grade.py --filter '<raw ffmpeg>'` accepts any filter string.

Hard rules: apply **per-segment during extraction** (not post-concat, which re-encodes twice). Never go aggressive without testing skin tones.

## Subtitles (when requested)

Subtitles have three dimensions worth reasoning about: **chunking** (1/2/3/sentence per line), **case** (UPPER/Title/Natural), and **placement** (margin from bottom). The right combo depends on content.

**Worked styles** — pick, adapt, or invent:

**`bold-overlay`** — short-form tech launch, fast-paced social. 2-word chunks, UPPERCASE, break on punctuation, Helvetica 18 Bold, white-on-outline, `MarginV=35`. `render.py` ships with this as `SUB_FORCE_STYLE`.

```
FontName=Helvetica,FontSize=18,Bold=1,
PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H00000000,
BorderStyle=1,Outline=2,Shadow=0,
Alignment=2,MarginV=35
```

**`natural-sentence`** (if you invent this mode) — narrative, documentary, education. 4–7 word chunks, sentence case, break on natural pauses, `MarginV=60–80`, larger font for readability, slightly wider max-width. No shipped force_style — design one if you need it.

Invent a third style if neither fits. Hard rules: subtitles LAST (Rule 1), output-timeline offsets (Rule 5).

## Animations (when requested)

Animations match the content and the brand. **Get the palette, font, and visual language from the conversation** — never assume a default. If the user hasn't told you, propose a palette in the strategy phase and wait for confirmation before building anything.

**Tool options:**

- **PIL + PNG sequence + ffmpeg** — simple overlay cards: counters, typewriter text, single bar reveals, progressive draws. Fast to iterate, any aesthetic you want. The launch video used this.
- **Manim** — formal diagrams, state machines, equation derivations, graph morphs. Read `skills/manim-video/SKILL.md` and its references for depth.
- **Remotion** — typography-heavy, brand-aligned, web-adjacent layouts. React/CSS-based.

None is mandatory. Invent hybrids if useful (e.g., PIL background with a Remotion layer on top).

**Duration rules of thumb, context-dependent:**

- **Sync-to-narration explanations.** A viewer needs to parse the content at 1×. Rough floor 3s, typical 5–7s for simple cards, 8–14s for complex diagrams. The launch video shipped at 5–7s per simple card.
- **Beat-synced accents** (music video, fast montage). 0.5–2s is fine — they're visual accents, not information. The "readable at 1×" rule becomes *"recognizable at 1×"*, not *"fully parseable."*
- **Hold the final frame ≥ 1s** before the cut (universal).
- **Over voiceover:** total duration ≥ `narration_length + 1s` (universal).
- **Never parallel-reveal independent elements** — the eye can't track two new things at once. One thing, pause, next thing.

**Animation payoff timing (rule for sync-to-narration):** get the payoff word's timestamp. Start the overlay `reveal_duration` seconds earlier so the landing frame coincides with the spoken payoff word. Without this sync the animation feels disconnected.

**Easing** (universal — never `linear`, it looks robotic):

```python
def ease_out_cubic(t):    return 1 - (1 - t) ** 3
def ease_in_out_cubic(t):
    if t < 0.5: return 4 * t ** 3
    return 1 - (-2 * t + 2) ** 3 / 2
```

`ease_out_cubic` for single reveals (slow landing). `ease_in_out_cubic` for continuous draws.

**Typing text anchor trick:** center on the FULL string's width, not the partial-string width — otherwise text slides left during reveal.

**Example palette** (the launch video — one aesthetic among infinite):
- Background `(10, 10, 10)` near-black
- Accent `#FF5A00` / `(255, 90, 0)` orange
- Labels `(110, 110, 110)` dim gray
- Font: Menlo Bold at `/System/Library/Fonts/Menlo.ttc` (index 1)
- ≤ 2 accent colors, ~40% empty space, minimal chrome
- Result: terminal / retro tech feel

This is one style. If the brand is warm and serif, use that. If it's colorful and playful, use that. If the user handed you a style guide, follow it. If they didn't, propose one and confirm.

**Parallel sub-agent brief** — each animation is one sub-agent spawned via the `Agent` tool. Each prompt is self-contained (sub-agents have no parent context). Include:

1. One-sentence goal: *"Build ONE animation: [spec]. Nothing else."*
2. Absolute output path (`<edit>/animations/slot_<id>/render.mp4`)
3. Exact technical spec: resolution, fps, codec, pix_fmt, CRF, duration
4. Style palette as concrete values (RGB tuples, hex, or reference to a design system)
5. Font path with index
6. Frame-by-frame timeline (what happens when, with easing)
7. Anti-list ("no chrome, no extras, no titles unless specified")
8. Code pattern reference (copy helpers inline, don't import across slots)
9. Deliverable checklist (script, render, verify duration via ffprobe, report)
10. **"Do not ask questions. If anything is ambiguous, pick the most obvious interpretation and proceed."**

One sub-agent = one file (unique filenames, parallel agents don't overwrite each other).

## Output spec

Match the source unless the user asked for something specific. Common targets: `1920×1080@24` cinematic, `1920×1080@30` screen content, `1080×1920@30` vertical social, `3840×2160@24` 4K cinema, `1080×1080@30` square. `render.py` defaults the scale to 1080p from any source; pass `--filter` or edit the extract command for other targets. Worth asking the user which delivery format matters.

## EDL format

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4", "C0108": "/abs/path/C0108.MP4"},
  "ranges": [
    {"source": "C0103", "start": 2.42, "end": 6.85,
     "beat": "HOOK", "quote": "...", "reason": "Cleanest delivery, stops before slip at 38.46."},
    {"source": "C0108", "start": 14.30, "end": 28.90,
     "beat": "SOLUTION", "quote": "...", "reason": "Only take without the false start."}
  ],
  "grade": "warm_cinematic",
  "overlays": [
    {"file": "edit/animations/slot_1/render.mp4", "start_in_output": 0.0, "duration": 5.0}
  ],
  "subtitles": "edit/master.srt",
  "total_duration_s": 87.4
}
```

`grade` is a preset name or raw ffmpeg filter. `overlays` are rendered animation clips. `subtitles` is optional and applied LAST.

## Memory — `project.md`

Append one section per session at `<edit>/project.md`:

```markdown
## Session N — YYYY-MM-DD

**Strategy:** one paragraph describing the approach
**Decisions:** take choices, cuts, grades, animations + why
**Reasoning log:** one-line rationale for non-obvious decisions
**Outstanding:** deferred items
```

On startup, read `project.md` if it exists and summarize the last session in one sentence before asking whether to continue.

## Anti-patterns

Things that consistently fail regardless of style:

- **Hierarchical pre-computed codec formats** with USABILITY / tone tags / shot layers. Over-engineering. Derive from the transcript at decision time.
- **Hand-tuned moment-scoring functions.** The LLM picks better than any heuristic you'll write.
- **Whisper SRT / phrase-level output.** Loses sub-second gap data. Always word-level verbatim.
- **FunASR paraformer-zh timestamp format.** Returns 2-element arrays `[start_ms, end_ms]` without embedded word text. The `text` field contains space-separated characters/words, and timestamps map one-to-one to characters. Code must index into `text.replace(" ", "")` to get the word for each timestamp entry. Earlier FunASR versions and other models may return 3-element `[start, end, word]` — check before assuming.
- **Homebrew ffmpeg lacks `zscale` and `subtitles` filters.** Homebrew's ffmpeg is compiled without `--enable-libzimg` (zscale) and `--enable-libass` (subtitles). Workarounds: (1) Replace `zscale` with `colorspace`+`tonemap` for HDR-to-SDR; (2) For subtitle burning, compile ffmpeg 7.x from source with `--enable-libass --enable-libfreetype --enable-fontconfig --enable-libfribidi`, install to `/usr/local/ffmpeg/bin/ffmpeg`, and use it for the compositing step; (3) In draft mode use `-hwaccel videotoolbox -c:v h264_videotoolbox` for hardware encoding (3x+ speed on Apple Silicon) and skip CPU-intensive tonemapping.
- **4K HDR iPhone videos encode extremely slowly with libx264 software encoder.** Even `ultrafast` preset takes ~0.5x speed on Apple Silicon due to CPU-bound HDR tonemapping. For draft/preview mode, always use `h264_videotoolbox` hardware encoder and skip tonemapping.
- **Pre-compress 4K sources to 1080p before rendering.** When source clips are 4K (3840x2160) from iPhone and the final output is 1080p, pre-compressing sources cuts segment extraction time from minutes to seconds. Workflow: (1) `ffprobe` each source — if 4K, compress: `ffmpeg -y -i input.MOV -vf scale=1920:-2 -c:v h264_videotoolbox -profile:v high -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart input_1080p.mp4`; (2) Update EDL `"sources"` to point to `*_1080p.mp4` files; (3) Run render. Skip tonemapping in `extract_segment` since the pre-compressed MP4 is already SDR.
- **Dirty fonts directory slows subtitle rendering.** libass scans the entire fontsdir and tries to load every file. Debug files (test PNGs, `.zip` archives, subdirectories) cause "Error opening memory font" warnings and slow down subtitle compositing. Keep only `.otf`/`.ttf` font files in `static/fonts/`. Run: `find static/fonts/ -type f ! -name '*.otf' ! -name '*.ttf' -delete && find static/fonts/ -type d ! -name fonts -exec rm -rf {} +` before compositing.
- **FunASR transcript proofreading (Chinese).** After transcription, always read each `transcripts/*.json` and fix: place names (web search to confirm), homophone errors (同音字), garbled ASR, contextually wrong words. Fix both the `text` field AND `words[].text` since `build_master_srt` reconstructs from word-level data.
- **Using Whisper SRT / phrase-level output.** Loses sub-second gap data. Always word-level verbatim.
- **Burning subtitles into base before compositing overlays.** Overlays hide them. (Hard Rule 1.)
- **Single-pass filtergraph when you have overlays.** Double re-encodes. Use per-segment extract → concat.
- **Linear animation easing.** Looks robotic. Always cubic.
- **Hard audio cuts at segment boundaries.** Audible pops. (Hard Rule 3.)
- **Typing text centered on the partial string.** Text slides left as it grows.
- **Sequential sub-agents for multiple animations.** Always parallel.
- **Editing before confirming the strategy.** Never.
- **Re-transcribing cached sources.** Immutable outputs of immutable inputs.
- **Assuming what kind of video it is.** Look first, ask second, edit last.
- **Font directory resolution when source is outside video-use/.** `render.py` looks for fonts at `<videos_dir>/static/fonts/`. When running on footage in `~/Downloads/` or other locations, copy the Noto Sans CJK `.otf` files there: `mkdir -p <videos_dir>/static/fonts && cp ~/.hermes/skills/video-use/static/fonts/NotoSansCJKsc-*.otf <videos_dir>/static/fonts/`.
- **Homebrew ffmpeg lacks `zscale` and `subtitles` filters.** Homebrew's ffmpeg is compiled without `--enable-libzimg` (zscale) and `--enable-libass` (subtitles). Workarounds: (1) Replace `zscale` with `colorspace`+`tonemap` for HDR-to-SDR in `render.py`; (2) For subtitle burning, compile ffmpeg 7.x from source with `--enable-libass --enable-libfreetype --enable-fontconfig --enable-libfribidi`, install to `/usr/local/ffmpeg/bin/ffmpeg`; (3) In draft mode use `-hwaccel videotoolbox -c:v h264_videotoolbox` for 3x+ hardware encoding on Apple Silicon and skip CPU-intensive tonemapping.
- **iPhone vertical videos have -90° rotation metadata.** `ffprobe` shows "Display Matrix: rotation of -90.00 degrees" on portrait iPhone footage. The `scale` filter respects this automatically — vertical sources (3840x2160 rotated) become tall outputs (e.g., 1280x2276) for social/vertical format. Do NOT add `transpose` filters.
- **ffmpeg `subtitles` filter comma escaping in `filter_complex`.** Commas in `force_style` must be escaped as `\\,` when used inside `-filter_complex`, otherwise ffmpeg parses them as filter chain separators.
- **ffmpeg `overlay` filter with PNG alpha requires `-loop 1` on the PNG input.** Without `-loop 1`, the PNG overlay is read as a single frame and silently drops from the output on macOS ffmpeg builds, even with `format=auto`, `format=rgb`, `shortest=1`. **Working pattern:** Use `-loop 1 -i overlay.png` with `trim` + `setpts` to match the segment duration:
```bash
ffmpeg -y -i base.mp4 -loop 1 -i overlay.png \
  -filter_complex "[1:v]trim=0:DUR,setpts=PTS-STARTPTS,fade=t=in:st=0:d=2:alpha=1[ov];[0:v][ov]overlay=X:Y:format=auto" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -an output.mp4
```
Key: `-loop 1` makes ffmpeg loop the PNG as a video stream, `trim=0:DUR` limits it to the segment duration, `setpts=PTS-STARTPTS` resets timestamps, and `fade=t=in:st=0:d=2:alpha=1` adds the fade-in effect. For fade-out: add `,fade=t=out:st=DUR-2:d=2:alpha=1` after the first fade.
- **Chinese font path on macOS:** `PingFang.ttc` is NOT at `/System/Library/Fonts/PingFang.ttc` (it's buried in `/System/Library/AssetsV2/...`). Use `/System/Library/Fonts/Hiragino Sans GB.ttc` instead — it's directly in `/System/Library/Fonts/` and supports simplified Chinese reliably for Pillow text rendering.
- **Apple Music BGM download:** Use gamdl with a valid Apple Music session cookie to download tracks. Search Apple Music CN with `site:music.apple.com/cn/album` + mood keywords (cinematic, adventure, electronic, ambient, uplifting, epic). Download to the project's `audio/` directory.
- **ffmpeg `zoompan` filter does NOT support `t` (time in seconds) variable.** Using `t` in zoompan expressions causes silent failure: `[Eval] Undefined constant or missing '(' in 't/5.0'` and the entire render fails with exit code -22. **Must use `on` (frame number) instead.** Example: for a 5-second clip at 30fps, use `on/150.0` instead of `t/5.0`. The `d` parameter must be total frames (5s × 30fps = 150), and `fps=30` must match output frame rate. Pan compensation with zoom: `x='iw/2-(iw/zoom/2)+delta*on/total_frames'`.
- **Portrait video scaling — no stretching, no black bars.** User explicitly rejects both aspect ratio distortion and pillarboxing. Use `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920` — scale up until the frame fills 1080×1920, then crop the excess. This works for all source types: portrait videos (544×960, 720×1280), landscape videos (1280×720, rotate first with `transpose=1`), and photos of any ratio. For super-tall images (1206×2622), scale to a height that preserves detail then zoompan within the frame.
