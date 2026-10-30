"""Re-time the demo video to a new emotive.py render.

  python retime.py ../voice-swap.wav            (needs numpy + soundfile, e.g. the Chatterbox venv)

Reads <wav> and its <wav>.timeline.json, then rewrites:
  assets/audio/voice-swap.wav + voice.js   (loudness envelope, segments, scene timing)
  index.html                               (scene hosts, voice and sound effects)
  compositions/trailer.html                (subtitles, emotion chips, banners)
Everything between the GENERATED markers is replaced; edit the rest freely.

Segment conventions (from the script .json): "voice": "system" is the glitch alert,
the first non-English line triggers the language banner, "caption" is the subtitle in
the other language, and [chuckle]/[sigh]/[laugh] tags become chips and *stage directions*.
"""
import html
import json
import os
import re
import shutil
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE_START = 1.0
TITLE_LEN, HOWTO_LEN, END_LEN = 4.1, 11.0, 3.8
TAGS = {"chuckle": "chuckles", "sigh": "sighs", "laugh": "laughs", "gasp": "gasps"}
TAG_RE = re.compile(r"\[(chuckle|sigh|laugh|gasp)\]")
FPS = 30

wav_path = os.path.abspath(sys.argv[1])
segs = json.load(open(os.path.splitext(wav_path)[0] + ".timeline.json", encoding="utf-8"))
for s in segs:
    s["a"], s["b"] = round(s["start"] + VOICE_START, 3), round(s["end"] + VOICE_START, 3)

# Loudness envelope per video frame drives lip-sync, the HUD meter and the 3D ring.
w, sr = sf.read(wav_path)
w = w if w.ndim == 1 else w.mean(1)
hop = sr // FPS
rms = np.array([np.sqrt(np.mean(w[i:i + hop] ** 2)) for i in range(0, len(w), hop)])
env = np.minimum(1, rms / rms.max() * 1.4).round(3).tolist()
voice_len = len(w) / sr

system = next((s for s in segs if s["voice"] == "system"), None)
G0 = round(system["a"] - 0.25, 3) if system else None
SWAP = round(system["b"], 3) if system else None
G1 = round(SWAP + 0.3, 3) if system else None
lang_seg = next((s for s in segs if s["lang"] != "en"), None)
TRAILER = round(VOICE_START + voice_len + 0.5, 2)
TITLE = round(TRAILER - 0.3, 2)
SLAM = round(TITLE + 0.4, 2)
HOWTO = round(TITLE + TITLE_LEN, 2)
END = round(HOWTO + HOWTO_LEN, 2)
DURATION = round(END + END_LEN, 2)
timing = dict(VOICE_START=VOICE_START, G0=G0, G1=G1, SWAP=SWAP, SLAM=SLAM, HOWTO=HOWTO,
              END=END, TRAILER=TRAILER, DURATION=DURATION, LANG=lang_seg["a"] if lang_seg else None)

os.makedirs(os.path.join(HERE, "assets/audio"), exist_ok=True)
shutil.copy(wav_path, os.path.join(HERE, "assets/audio/voice-swap.wav"))
with open(os.path.join(HERE, "assets/audio/voice.js"), "w", encoding="utf-8") as f:
    f.write("window.VOICE = " + json.dumps({"fps": FPS, "env": env, "segments": segs}, ensure_ascii=False) + ";\n")
    f.write("window.TIMING = " + json.dumps(timing) + ";\n")


def tag_time(s):
    """Rough moment a mid-sentence tag is heard: its share of the line's length."""
    m = TAG_RE.search(s["text"])
    share = m.start() / max(1, len(s["text"]))
    return round(s["a"] + (0.05 if share < 0.05 else share * (s["b"] - s["a"])), 2)


def stage(text):
    return TAG_RE.sub(lambda m: f'<span class="tag">*{TAGS[m.group(1)]}*</span>', html.escape(text))


def split(s):
    """Long English lines become two subtitle cards, cut at a sentence end."""
    en, ar = s["text"], s.get("caption", "")
    m = re.search(r"[.!?]\s", en[10:])
    if s["lang"] != "en" or len(en) <= 55 or not m:
        return [(s["a"], s["b"], en, ar)]
    cut = 10 + m.end()
    k = re.search(r"[.!؟]\s", ar)
    ar1, ar2 = (ar[:k.end()].strip(), ar[k.end():].strip()) if k else (ar, "")
    mid = round(s["a"] + (s["b"] - s["a"]) * cut / len(en), 2)
    return [(s["a"], mid, en[:cut].strip(), ar1), (mid, s["b"], en[cut:].strip(), ar2)]


# Trailer overlays: chips, banners, subtitles.
parts, n = [], 0
for s in segs:
    if s["kind"] == "speech" and TAG_RE.search(s["text"]):
        cls = " holo" if SWAP and s["a"] >= SWAP else ""
        tag = TAG_RE.search(s["text"]).group(0)
        parts.append(f'    <div id="chip-{n}" class="chip{cls} clip" data-start="{tag_time(s)}" data-duration="1.5">'
                     f'<span class="chip-in">{tag}</span></div>')
        n += 1
if system:
    parts.append(f'    <div id="swap" class="banner clip" data-start="{G0 + 0.15:.2f}" data-duration="{SWAP - G0 + 0.9:.2f}">'
                 '<span class="banner-in" id="swap-in">VOICE SWAP DETECTED<span class="ar">تم تبديل الصوت</span></span></div>')
if lang_seg:
    parts.append(f'    <div id="lang" class="banner clip" data-start="{lang_seg["a"] - 0.1:.2f}" data-duration="1.9">'
                 '<span class="banner-in" id="lang-in">LANGUAGE →<span class="ar">العربية</span></span></div>')
c = 0
for s in segs:
    if s["kind"] != "speech":
        continue
    cls = "system" if s["voice"] == "system" else "holo" if SWAP and s["a"] >= SWAP else ""
    for a, b, en, ar in split(s):
        dur = round(b - a + 0.25, 2)
        if s["lang"] != "en":
            body = f'<span class="ar main">{html.escape(en)}</span><span class="en">{html.escape(ar)}</span>'
        else:
            body = f'<span class="en">{stage(en)}</span><span class="ar">{html.escape(ar)}</span>'
        parts.append(f'    <div id="cap-{c}" class="cap {cls} clip" data-start="{a:.2f}" data-duration="{dur}">'
                     f'<span class="cap-in">{body}</span></div>')
        c += 1

trailer_path = os.path.join(HERE, "compositions/trailer.html")
t = open(trailer_path, encoding="utf-8").read()
t = re.sub(r"(<!-- GENERATED:BEGIN -->).*?(\s*<!-- GENERATED:END -->)", lambda m: m.group(1) + "\n" + "\n".join(parts) + m.group(2), t, flags=re.S)
t = re.sub(r'(data-trailer-span[^>]*data-duration=")[0-9.]+', rf"\g<1>{TRAILER}", t)
open(trailer_path, "w", encoding="utf-8").write(t)

# Root: scene hosts, voice and sound on visible actions.
def host(id_, start, dur, z):
    return (f'      <div id="{id_}" data-composition-id="{id_}" data-composition-src="compositions/{id_}.html" '
            f'data-start="{start}" data-duration="{dur}" data-track-index="{z - 1}" data-track-kind="graphics" '
            f'data-width="1920" data-height="1080" style="z-index: {z}"></div>')


sfx_len = {"whoosh": 0.57, "pop": 0.72, "glitch-1": 2.64, "glitch-3": 3.1, "ping": 1.32, "riser": 10.03,
           "impact-bass-1": 2.12, "whoosh-short": 0.57, "typing": 1.5, "sparkle": 1.8}
cues = [("whoosh", 0.15, 0.35)]
cues += [("pop", tag_time(s), 0.3) for s in segs if s["kind"] == "speech" and TAG_RE.search(s["text"])]
if system:
    cues += [("glitch-1", G0, 0.5), ("glitch-3", G0 + 0.5, 0.3)]
if lang_seg:
    cues.append(("ping", lang_seg["a"] - 0.1, 0.3))
cues += [("riser", max(0, SLAM - 10.03), 0.22), ("impact-bass-1", SLAM, 0.6), ("whoosh-short", HOWTO - 0.05, 0.35),
         ("typing", HOWTO + 0.7, 0.25), ("typing", HOWTO + 4.3, 0.25), ("typing", HOWTO + 7.9, 0.25), ("sparkle", END + 0.1, 0.35)]

root = [host("bg", 0, DURATION, 1), host("trailer", 0, TRAILER, 2), host("title", TITLE, TITLE_LEN, 3),
        host("howto", HOWTO, HOWTO_LEN, 4), host("endcard", END, END_LEN, 5), "",
        f'      <audio id="voice" class="clip" src="assets/audio/voice-swap.wav" data-start="{VOICE_START}" '
        f'data-duration="{voice_len:.2f}" data-track-index="10" data-volume="1"></audio>']
for i, (name, at, vol) in enumerate(cues):
    root.append(f'      <audio id="sfx-{i}" class="clip" src="assets/sfx/{name}.mp3" data-start="{at:.2f}" '
                f'data-duration="{sfx_len[name]}" data-track-index="{11 + i}" data-volume="{vol}"></audio>')

index_path = os.path.join(HERE, "index.html")
x = open(index_path, encoding="utf-8").read()
x = re.sub(r"(<!-- GENERATED:BEGIN -->).*?(\s*<!-- GENERATED:END -->)", lambda m: m.group(1) + "\n" + "\n".join(root) + m.group(2), x, flags=re.S)
x = re.sub(r'(data-composition-id="main" data-start="0" data-duration=")[0-9.]+', rf"\g<1>{DURATION}", x)
open(index_path, "w", encoding="utf-8").write(x)
print(f"voice {voice_len:.1f}s, video {DURATION}s, swap at {SWAP}, title {TITLE}, {c} subtitle cards, {n} chips")
