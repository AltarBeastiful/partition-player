"""Render each benchmark MusicXML to MIDI, WAV and OGG so the engines can be compared by ear.

Usage: .venv-oemer/bin/python bench/make_audio.py   (needs timidity, FluidR3_GM.sf2 and ffmpeg)
"""
import subprocess, pathlib
from music21 import converter, tempo, instrument, harmony
SRCS = {
    'ground_truth': 'bench/samples/anton_yvan_boris_ground_truth.musicxml',
    'homr': 'bench/out/homr/anton.musicxml',
    'audiveris': 'bench/out/audiveris_ocr/result.musicxml',
    'oemer': 'bench/out/oemer_cv4/anton_yvan_boris_photo.musicxml',
}
OUT = pathlib.Path('bench/out/audio'); OUT.mkdir(parents=True, exist_ok=True)
for name, path in SRCS.items():
    if not pathlib.Path(path).exists():
        print('skip', name, '(missing)'); continue
    s = converter.parse(path)
    for cs in list(s.recurse().getElementsByClass(harmony.ChordSymbol)):
        cs.activeSite.remove(cs)  # chord symbols would otherwise be realised as block chords
    p = s.parts[0]; p.insert(0, instrument.Piano()); p.insert(0, tempo.MetronomeMark(number=96))
    mid = OUT / f'{name}.mid'; wav = OUT / f'{name}.wav'; ogg = OUT / f'{name}.ogg'
    s.write('midi', fp=str(mid))
    subprocess.run(['timidity', '-x', 'soundfont /usr/share/sounds/sf2/FluidR3_GM.sf2', '-Ow', '-o', str(wav), str(mid)], check=True, capture_output=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-c:a', 'libvorbis', '-q:a', '3', str(ogg)], check=True)
    print(name, '->', ogg)
