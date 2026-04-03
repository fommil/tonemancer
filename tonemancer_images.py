# this is for combining multiple csvs into one and then rendering to PNG

from collections import defaultdict
import glob
import re
import csv

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from tonemancer_utils import *

groups = defaultdict(dict)
for f in sorted(glob.glob("response_*.csv")):
    m = re.match(r"(response_.+?)_(\d+)\.csv", f)
    if not m:
        continue
    prefix, num = m.group(1), m.group(2)
    with open(f) as fh:
        reader = csv.DictReader(fh)
        freqs = []
        vals = []
        for row in reader:
            freqs.append(float(row["freq"]))
            vals.append(float(row["value"]))
        groups[prefix][num] = vals
        groups[prefix]["freqs"] = freqs

for prefix, data in groups.items():
    freqs = data.pop("freqs")
    nums = sorted(data.keys(), key=int)
    header = "freq," + ",".join(f"value{n}" for n in nums)
    rows = np.column_stack([freqs] + [data[n] for n in nums])
    np.savetxt(f"result_{prefix}.csv", rows, delimiter=',', header=header, comments='')
    print(f"Saved result_{prefix}.csv")

for filename in sorted(glob.glob("result_*.csv")):
    with open(filename) as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        freqs = []
        data = {c: [] for c in cols if c != "freq"}
        for row in reader:
            freqs.append(float(row["freq"]))
            for c in data:
                data[c].append(float(row[c]))

    freqs = np.array(freqs)
    fig = Figure(figsize=(16, 9))
    ax = fig.add_subplot(111)
    setup_freq_axis(ax)

    all_vals = np.concatenate([np.array(data[c]) for c in data])
    peak_db = 20 * np.log10(np.maximum(np.max(all_vals), 1e-10))
    for col in reversed(sorted(data.keys(), key=lambda c: int(re.search(r'\d+', c).group()))):
        db = 20 * np.log10(np.maximum(np.array(data[col]), 1e-10)) - peak_db
        if len(data) == 1:
            ax.plot(freqs, db, label=col)
        else:
            ax.scatter(freqs, db, label=col, s=1)

    if len(data) > 1:
        ax.legend()
    ax.set_title(filename.replace(".csv", ""))

    canvas = FigureCanvasAgg(fig)
    out = filename.replace(".csv", ".png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Saved {out}")

# Local Variables:
# compile-command: "python3 tonemancer_images.py"
# End:
