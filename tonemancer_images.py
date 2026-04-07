# this is for loading response WAV files, grouping by prefix, and rendering
# combined spectrum + waveform plots to PNG

from collections import defaultdict
import glob
import re

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from tonemancer_utils import *


# group response_*.wav by prefix (everything before the trailing number)
groups = defaultdict(dict)
for f in sorted(glob.glob("response_*.wav")):
    #print(f)
    m = re.match(r"(response_.*\D)(\d+)\.wav", f)
    if m:
        prefix, num = m.group(1), m.group(2)
    else:
        prefix = f.replace(".wav", "")
        num = 0

    data = load_wav(f)
    freqs, spec = chunk_spectrum(data)
    groups[prefix][num] = {"spectrum": spec, "waveform": data}
    groups[prefix]["freqs"] = freqs

for prefix, data in groups.items():
    freqs = data.pop("freqs")
    nums = sorted(data.keys(), key=int)

    fig = Figure(figsize=(16, 9))

    # main spectrum plot
    ax = fig.add_subplot(111)
    setup_freq_axis(ax)

    all_peaks = [np.max(data[n]["spectrum"]) for n in nums]
    peak_db = 20 * np.log10(np.maximum(max(all_peaks), 1e-10))

    cycle = [f'C{i}' for i in range(len(nums))]
    color_map = {num: cycle[i] for i, num in enumerate(reversed(nums))}
    for num in reversed(nums):
        spec = data[num]["spectrum"]
        db = 20 * np.log10(np.maximum(spec, 1e-10)) - peak_db
        label = f"setting {num}"
        if len(nums) == 1:
            line = ax.plot(freqs, db, label=label, color=color_map[num])[0]
        else:
            line = ax.scatter(freqs, db, label=label, s=1, color=color_map[num])

    if len(nums) > 1:
        ax.legend(fontsize='small')
    ax.set_title(prefix.rstrip("_"))
    ax.set_ylabel("dB")

    # waveform inset (all captures overlaid, matching spectrum colours)
    ax_wave = fig.add_axes([0.66, 0.66, 0.15, 0.2])
    for num in nums:
        waveform = data[num]["waveform"]
        sr = 44100
        # hack because I have one signal at 440Hz
        if "440" in prefix:
            n_show = int(sr * 0.005)
            start = max(0, len(waveform) - n_show * 100)
        else:
            n_show = int(sr * 0.02)
            start = max(0, len(waveform) - n_show * 10)
        for j in range(start, len(waveform) - n_show):
            if waveform[j] < 0 and waveform[j + 1] >= 0:
                start = j
                break
        snippet = waveform[start:start + n_show]
        t_ms = np.arange(len(snippet)) / (sr / 1000)
        ax_wave.plot(t_ms, snippet, linewidth=0.8, color=color_map[num])
    ax_wave.tick_params(labelsize=5)
    ax_wave.set_xlabel("ms", fontsize=6)

    canvas = FigureCanvasAgg(fig)
    out = f"result_{prefix.rstrip('_')}.png"
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Saved {out}")

# Local Variables:
# compile-command: "python3 tonemancer_images.py"
# End:
