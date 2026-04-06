#!/usr/bin/env python3
import glob
import sys
import os
import subprocess

import numpy as np

import librosa

from tonemancer_utils import *

# this file is for generating input_ and target_ files from .wavs which are
# manually created from guitar isolated tracks. It is a good idea to find two
# sections in any song that you want to replicate: a single note played
# repeatedly with distortion, and a longer section playing a verse or chorus
# riff for EQ balancing.
#
# further on in this file are some experiments to create .wav files from .mid
# input which I was planning on using to generate input signals automatically
# but it was pretty disappointing so I think it's best that the user records
# their own input.

# importantly resamples to 44100Hz
def load_wav(filename):
    y, _ = librosa.load(filename, sr=44100)
    return y

def save_csv(data, filename):
    freqs, vals = data
    np.savetxt(filename, np.column_stack([freqs, vals]), delimiter=',', header='freq,value', comments='')

def process(f):
    print(f)
    wav = load_wav(f)
    res = chunk_spectrum(wav, chunk_size=44100)
    save_csv(res, f.replace(".wav", ".csv"))

# ffmpeg -ss 61.0 -t 4 -i input.mp3 target_verse.wav
#process("target_verse.wav")

# repeated B single note, maybe too short
# ffmpeg -ss 86.5 -t 0.6 -i input.mp3 target_note_b.wav
#process("target_note_b.wav")

# csvmidi note_b.csv input_midi_note_b.mid
# fluidsynth input_midi_note_b.mid -F input_midi_note_b.wav -r 44100

# process("input_midi_note_b.wav")

# manually created with
# arecord -l
# gives (card,device) then convert to
# arecord -D hw:2,0 -f S16_LE -r 44100 -c 2 output.wav
# sox output.wav -c 1 output_mono.wav
# and then chopped up in audacity

for f in glob.glob("input_*.wav"):
    process(f)

exit(0)

import mido

if len(sys.argv) < 2:
    print("Usage: input_midi.py <midi_file> [track_number]")
    sys.exit(1)

mid = mido.MidiFile(sys.argv[1])

if len(sys.argv) < 3:
    for i, track in enumerate(mid.tracks):
        names = [msg.name for msg in track if msg.type == 'track_name']
        insts = [msg.name for msg in track if msg.type == 'instrument_name']
        name = names[0] if names else None
        inst = insts[0] if insts else None
        if name is None or inst is None or ("Guitar" not in name and "Guitar" not in inst):
            continue

        print(f"  Track {i + 1}: {name} ({inst})")
    sys.exit(0)

track_num = int(sys.argv[2]) - 1

new_mid = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)

track = mid.tracks[track_num].copy()
names = [msg.name for msg in track if msg.type == 'track_name']
name = names[0] if names else None
print(f"Extracting Track {track_num + 1}: {name}")

for msg in track:
    if msg.type == 'program_change':
        # replace overdriven / distortion guitars with a clean guitar
        if msg.program in [29, 30]:
            # TODO using 28 would use a muted guitar instead
            #      and maybe works better for some songs
            msg.program = 27
new_mid.tracks.append(track)

tmp_mid = "tmp.mid"
tmp_wav = "tmp.wav"
new_mid.save(tmp_mid)

subprocess.run(["fluidsynth", tmp_mid, "-F", tmp_wav, "-r", "44100"])
os.remove(tmp_mid)

data = load_wav(tmp_wav)

# if stereo, take left channel
if data.ndim > 1:
    data = data[:, 0]

data = data.astype(np.float32) / np.iinfo(data.dtype).max

freqs, db = spectrum(data)

np.savetxt('tmp.csv', np.column_stack([freqs, db]), delimiter=',', header='frequency,db', comments='')

import matplotlib.pyplot as plt

gain = -max(db)

plt.plot(freqs, db + gain)
plt.xlabel('Hz')
plt.ylabel('dB')
plt.xlim(80, 8000)
plt.ylim(-100, 0)
plt.title('Reference Spectrum')
plt.show()

# Local Variables:
# compile-command: "python3 tonemancer_generate.py"
# End:
