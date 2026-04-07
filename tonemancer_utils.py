import numpy as np
import librosa


note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

NOTE_FREQS = {}
for i in range(109):
    # 32.7Hz = C1
    freq = 32.70 * 2 ** (i / 12)
    name = note_names[i % 12]
    octave = (i // 12) + 1
    NOTE_FREQS[f"{name}{octave}"] = freq

XLIM = (100, 17000)
notes_in_range = [(n, f) for n, f in sorted(NOTE_FREQS.items(), key=lambda x: x[1]) if XLIM[0] <= f <= XLIM[1]]

def is_c_natural(name):
    return name.startswith('C') and '#' not in name

def fmt_freq(f):
    return f"{f/1000:.1f}kHz" if f >= 1000 else f"{f:.0f}Hz"

def setup_freq_axis(ax, ylim=(-60, 0), minors=True):
    ax.set_ylim(*ylim)
    ax.set_xscale('log', base=2)
    ax.set_xlim(*XLIM)

    majors = [(n, f) for n, f in notes_in_range if is_c_natural(n)]
    ax.set_xticks([f for _, f in majors])
    if minors:
        ax.set_xticklabels([f"{n}\n{fmt_freq(f)}" for n, f in majors])
        minor_ticks = [(n, f) for n, f in notes_in_range if not is_c_natural(n)]
        ax.set_xticks([f for _, f in minor_ticks], minor=True)
        ax.set_xticklabels([n.rstrip('0123456789') for n, _ in minor_ticks], minor=True, fontsize=6)
    else:
        ax.set_xticklabels([n for n, _ in majors])

def chunk_spectrum(data, sr=44100, chunk_size=22050):
    # Welch-style: 50% overlapping segments for stable averaging
    hop = chunk_size // 2
    window = np.hanning(chunk_size)
    norm = 2 / window.sum()
    spectra = []
    start = 0
    while start + chunk_size <= len(data):
        chunk = data[start : start + chunk_size]
        spectra.append(np.abs(np.fft.rfft(chunk * window)) * norm)
        start += hop
    if not spectra:
        window = np.hanning(len(data))
        spec = np.abs(np.fft.rfft(data * window)) * 2 / window.sum()
        freqs = np.fft.rfftfreq(len(data), d=1/sr)
        return freqs, spec
    spec = np.mean(spectra, axis=0)
    freqs = np.fft.rfftfreq(chunk_size, d=1/sr)
    return freqs, spec

# librosa is an external dependency but will handle different precisions
# and sample rates.
def load_wav(filename):
    y, _ = librosa.load(filename, sr=44100)
    return y
