"""Emotive multi-segment, multi-voice speech with Chatterbox.

Each segment picks its own voice, language and emotion, so one clip can go from calm
English to a laugh to another speaker to Arabic. Non-verbal sounds ([laugh], [sigh]...)
come from Chatterbox Turbo in the same cloned voice, which also gives Arabic lines a laugh.

Run with the Chatterbox venv Python:
  .venv/Scripts/python.exe emotive.py script.json -o out.wav

script.json:
{
  "voices": {"mehdi": "path/to/dr-mehdi.wav", "me": "path/to/my-voice.wav"},
  "voice": "mehdi",           default voice (a key of "voices" or a path)
  "lang": "en",               default language
  "seed": 7,
  "segments": [
    {"text": "Every voice tells a story.", "emotion": "calm"},
    {"text": "Mine? [chuckle] It starts with a joke."},        tags -> Turbo automatically
    {"sfx": "[laugh]", "prompt": "[laugh] Ha ha!"},           sound only, trimmed to max_len
    {"text": "مرحبًا بكم.", "lang": "ar", "voice": "me", "emotion": "warm"}
  ]
}

Engines: English without tags -> classic, English with [tags] or "sfx" -> turbo,
any other lang -> multilingual. Force one with "engine". Emotions map to
(exaggeration, cfg): calm, normal, warm, sad, hype, surprised (Turbo ignores them).
"""
import argparse
import json
import os
import re
import sys

import torch
import torchaudio as ta

EMOTIONS = {
    "calm": (0.4, 0.5),
    "normal": (0.55, 0.5),
    "warm": (0.6, 0.45),
    "sad": (0.3, 0.35),
    "hype": (0.8, 0.3),
    "surprised": (0.9, 0.3),
}
TAG = re.compile(r"\[(laugh|chuckle|gasp|sigh|cough|sniff|groan|shush|clear throat)\]")

parser = argparse.ArgumentParser()
parser.add_argument("script", help="segment script (.json)")
parser.add_argument("-o", "--out", default="emotive.wav")
parser.add_argument("--keep-parts", action="store_true", help="also save each segment as a wav")
args = parser.parse_args()
sys.stdout.reconfigure(encoding="utf-8")

with open(args.script, encoding="utf-8") as f:
    spec = json.load(f)
base = os.path.dirname(os.path.abspath(args.script))
voices = spec.get("voices", {})
seed = spec.get("seed", 7)
segments = spec["segments"]
device = "cuda" if torch.cuda.is_available() else "cpu"
SR = 24000


def voice_path(s):
    """Reference wav for a segment, or None for the model's built-in stock voice."""
    v = s.get("voice", spec["voice"])
    v = voices.get(v, v)
    if v == "stock":
        return None
    return v if os.path.isabs(v) else os.path.join(base, v)


def engine_of(s):
    if "engine" in s:
        return s["engine"]
    if "sfx" in s or TAG.search(s["text"]):
        return "turbo"
    return "classic" if s.get("lang", spec.get("lang", "en")) == "en" else "multilingual"


def load(engine):
    if engine == "turbo":
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        return ChatterboxTurboTTS.from_pretrained(device=device)
    if engine == "multilingual":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_pretrained(device=device)
    from chatterbox.tts import ChatterboxTTS
    return ChatterboxTTS.from_pretrained(device=device)


def trim_silence(wav, threshold=0.01, pad=0.04):
    """Cut leading/trailing near-silence so splices sound continuous."""
    loud = (wav.abs() > threshold).nonzero()
    if loud.numel() == 0:
        return wav
    start = max(0, loud[0, -1].item() - int(pad * SR))
    end = min(wav.shape[-1], loud[-1, -1].item() + int(pad * SR))
    return wav[..., start:end]


def fade(wav, ms=15):
    n = min(int(SR * ms / 1000), wav.shape[-1] // 2)
    ramp = torch.linspace(0, 1, n)
    wav = wav.clone()
    wav[..., :n] *= ramp
    wav[..., -n:] *= ramp.flip(0)
    return wav


audio = [None] * len(segments)

# One pass per engine, so each model loads once and they never share the GPU.
for engine in ("classic", "turbo", "multilingual"):
    todo = [i for i, s in enumerate(segments) if engine_of(s) == engine]
    if not todo:
        continue
    model = load(engine)
    SR = model.sr
    stock_conds = model.conds  # the built-in voice, before any cloning overwrites it
    for n, i in enumerate(todo):
        s = segments[i]
        text = s.get("prompt", s.get("sfx", s.get("text")))
        exa, cfg = EMOTIONS[s.get("emotion", "normal")]
        exa, cfg = s.get("exaggeration", exa), s.get("cfg", cfg)
        print(f"[{engine} {n + 1}/{len(todo)}] ({s.get('voice', spec['voice'])}, "
              f"{s.get('emotion', 'normal')}) {text}")
        torch.manual_seed(s.get("seed", seed))
        ref = voice_path(s)
        if ref is None:
            model.conds = stock_conds
        # Passing the reference every time re-primes the voice, since exaggeration is baked into it.
        if engine == "turbo":
            wav = model.generate(text, audio_prompt_path=ref)
        elif engine == "multilingual":
            wav = model.generate(text, language_id=s.get("lang", spec.get("lang")),
                                 audio_prompt_path=ref, exaggeration=exa, cfg_weight=cfg)
        else:
            wav = model.generate(text, audio_prompt_path=ref, exaggeration=exa, cfg_weight=cfg)
        wav = trim_silence(wav.cpu())
        # max_len cuts words after a sound effect, or the mumbled tail Arabic sometimes adds.
        max_len = s.get("max_len", 1.6 if "sfx" in s else None)
        audio[i] = wav[..., : int(SR * max_len)] if max_len else wav
    del model
    torch.cuda.empty_cache()

pieces, timeline, t = [], [], 0.0
for i, (s, wav) in enumerate(zip(segments, audio)):
    wav = fade(wav)
    dur = wav.shape[-1] / SR
    timeline.append({"index": i, "start": round(t, 3), "end": round(t + dur, 3),
                     "kind": "sfx" if "sfx" in s else "speech",
                     "voice": s.get("voice", spec["voice"]),
                     "lang": s.get("lang", spec.get("lang", "en")),
                     "emotion": s.get("emotion", "laugh" if "sfx" in s else "normal"),
                     "text": s.get("text", s.get("sfx")),
                     "caption": s.get("caption", "")})
    gap = s.get("pause", 0.12 if "sfx" in s else 0.3)
    pieces += [wav, torch.zeros(1, int(SR * gap))]
    t += dur + gap
    if args.keep_parts:
        ta.save(f"{os.path.splitext(args.out)[0]}.part{i:02d}.wav", wav, SR)

out = torch.cat(pieces, dim=-1)
out = out / max(out.abs().max().item(), 1e-6) * 0.89
ta.save(args.out, out, SR)
with open(os.path.splitext(args.out)[0] + ".timeline.json", "w", encoding="utf-8") as f:
    json.dump(timeline, f, ensure_ascii=False, indent=2)
print(f"Saved {out.shape[-1] / SR:.1f}s -> {os.path.abspath(args.out)}")
