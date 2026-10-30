---
name: arabic-voice-studio
description: Emotive Arabic speech in a cloned voice, offline with Chatterbox - each line gets its own emotion (calm, warm, sad, hype, surprised) and real laughs, chuckles, gasps and sighs are spliced in the same voice. Use for "/arabic-voice-studio", Arabic voiceovers with feeling, "make him laugh in Arabic", تعليق صوتي بمشاعر, ضحكة, or any Arabic narration that needs more than one tone. For a single flat line use the voiceover or my-voice skill instead.
argument-hint: "[script text or .json] [voice name]"
---

# /arabic-voice-studio: Arabic with emotions

Chatterbox Multilingual speaks Arabic well but has no sound tags, and one exaggeration setting for a whole clip sounds flat. This skill splits the script into **segments**, gives each its own emotion, and borrows laughs and other non-verbal sounds from Chatterbox Turbo **in the same cloned voice**, then joins everything into one wav plus a timeline for video sync.

Paths (adjust if the drive letter changes):
- Chatterbox: `E:\PC NOW\Claude Skills\tts\chatterbox\` (venv in `.venv`)
- Voices: `E:\PC NOW\Claude Skills\tts\voices\` (`my-voice.wav`, `dr-mehdi.wav`, ...)
- Generator: `scripts/emotive.py` next to this file

## 1. Write the segment script

Save a `.json` next to the output:

```json
{
  "voice": "E:/PC NOW/Claude Skills/tts/voices/dr-mehdi.wav",
  "lang": "ar",
  "seed": 7,
  "segments": [
    {"text": "مَرْحَبًا بِكُم!", "emotion": "calm"},
    {"text": "وَالأَجْمَلُ؟ أَنَّهُ يَضْحَكُ أَيْضًا!", "emotion": "hype", "pause": 0.15},
    {"sfx": "[laugh]", "prompt": "[laugh] Ha ha!"},
    {"text": "نَعَم.", "emotion": "warm"}
  ]
}
```

| Emotion | exaggeration / cfg | Use for |
|---|---|---|
| calm | 0.40 / 0.50 | intros, explanations |
| normal | 0.55 / 0.50 | default |
| warm | 0.60 / 0.45 | closings, thanks |
| sad | 0.30 / 0.35 | soft, regretful lines |
| hype | 0.80 / 0.30 | excitement, reveals |
| surprised | 0.90 / 0.30 | "ماذا؟!" moments |

### Several voices and languages in one clip

Name the voices once and switch per segment; each segment may also set `"lang"`:

```json
"voices": {"mehdi": ".../dr-mehdi.wav", "me": ".../my-voice.wav"},
"voice": "mehdi", "lang": "en",
"segments": [
  {"text": "Mine? Well... [chuckle] it starts with a joke."},
  {"text": "That's not his voice anymore.", "voice": "me", "emotion": "surprised"},
  {"text": "أَنَا صَوْتُهُ الجَدِيد.", "voice": "me", "lang": "ar", "caption": "I'm his new voice."}
]
```

Engine per segment: English without tags → classic (uses emotion), English with inline `[tags]` → Turbo (acts the tags, ignores emotion), other languages → multilingual. Force one with `"engine"`. `"caption"` is copied into the timeline for subtitles. See `examples/voice-swap-trailer.json`.

Rules that keep Arabic clean:
- One or two short sentences per segment (under ~120 characters). Long segments drift into repetition.
- Modern Standard Arabic with tashkeel on ambiguous words. Expression comes from `!`, `؟` and `...`, never from stretched letters (`آآآه`).
- Sound effects are separate segments: `{"sfx": "[laugh]"}`. Tags: `[laugh] [chuckle] [gasp] [sigh] [cough] [sniff] [groan] [shush] [clear throat]`. Add a tiny English `prompt` like `"[laugh] Ha ha!"` so Turbo has something to voice; `max_len` (seconds, default 1.6) cuts any words after the sound.
- Put `"pause": 0.1-0.2` before a laugh so it lands right on the joke.

## 2. Generate

```bash
cd "/e/PC NOW/Claude Skills/tts/chatterbox"
.venv/Scripts/python.exe "<skill>/scripts/emotive.py" script.json -o out.wav --keep-parts 2>&1 | grep -E "^\[|Saved|Error"
```

Run it in the background: both models load once (~40 s each) plus ~5 s per segment. Outputs:
- `out.wav` - the joined clip, normalised
- `out.timeline.json` - start/end/emotion per segment, for captions and avatar sync
- `out.partNN.wav` - each segment (with `--keep-parts`), so one bad line can be redone

## 3. Review, then fix single lines
Send the wav with SendUserFile and ask the user to listen for repeated or cut-off words. `forcing EOS token` in Arabic is normal. To redo one line, change its `"seed"` and rerun; everything else stays identical because seeds are fixed.

## 4. Use it in a video
The timeline drives captions and lip-sync: switch an avatar to its laugh frame during `kind: "sfx"` segments, and pick mouth frames from audio loudness during speech. See `demo/` in the repo for a HyperFrames example.

## Consent
Only clone voices whose owner agreed. Don't script a real person saying things they wouldn't say, and don't present the audio as a real recording of them. Chatterbox embeds an inaudible AI watermark; leave it in.
