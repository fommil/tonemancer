
note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

NOTE_FREQS = {}
NOTE_FREQS = {}
for i in range(88):
    # 32.7Hz = C1
    freq = 32.70 * 2 ** (i / 12)
    name = note_names[i % 12]
    octave = (i // 12) + 1
    NOTE_FREQS[f"{name}{octave}"] = freq

#print(NOTE_FREQS)

all_notes = [65.41 * 2 ** (i / 12) for i in range(85)]
note_labels = [note_names[i % 12] for i in range(85)]
note_labels = ['' if i % 12 == 0 else note_labels[i % 12] for i in range(85)]

def setup_freq_axis(ax, ylim=(-50, 10), minors=True):
    ax.set_ylim(*ylim)
    ax.set_xscale('log', base=2)
    ax.set_xlim(100, 15000)
    c_ticks = [32.70 * 2**i for i in range(1, 9)]  # C2 through C9
    ax.set_xticks(c_ticks)

    def fmt_freq(f):
        return f"{f/1000:.1f}kHz" if f >= 1000 else f"{f:.0f}Hz"

    labels = [f"C{i+1}\n{fmt_freq(32.70 * 2**i)}" for i in range(1, 9)]
    if not minors:
        labels = [s.split("\n")[0] for s in labels]

    ax.set_xticklabels(labels)
    if minors:
        ax.set_xticks(all_notes, minor=True)
        ax.set_xticklabels(note_labels, minor=True, fontsize=6)
