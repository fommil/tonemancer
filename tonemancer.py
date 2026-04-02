#!/usr/bin/env python3

# this is the desktop app, it will have a webapp equivalent one day

from collections import deque

import csv
import glob
import json
from pathlib import Path
import re
import threading

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import ttk
from scipy.ndimage import maximum_filter1d, median_filter
from scipy.stats import kurtosis

from tonemancer_utils import *

CONFIG_PATH = Path("tonemancer.json")

def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}

def save_config():
    CONFIG_PATH.write_text(json.dumps(config, indent=2))

def get_devices(kind):
    devices = []
    for d in sd.query_devices():
        #print(d)
        if kind == "input" and d["max_input_channels"] == 0:
            continue
        if kind == "output" and d["max_output_channels"] == 0:
            continue
        name = d["name"]
        #print(f"{name} ({d["default_samplerate"]:.0f}Hz)")
        if name != "default" and ('hw:' not in name or "HDMI" in name):
            continue
        if d["default_samplerate"] != 44100:
            continue
        devices.append(name)
    return devices

config = load_config()

def refresh():
    sd._terminate()
    sd._initialize()
    inputs = get_devices("input")
    outputs = get_devices("output")
    input_combo["values"] = inputs
    output_combo["values"] = outputs

    saved_in = config.get("input_device")
    saved_out = config.get("output_device")

    if saved_in in inputs:
        input_combo.set(saved_in)
    elif inputs:
        input_combo.current(0)

    if saved_out in outputs:
        output_combo.set(saved_out)
    elif outputs:
        output_combo.current(0)

    on_input_change(None)
    on_output_change(None)

def on_input_change(event):
    config["input_device"] = input_combo.get()
    save_config()

def on_output_change(event):
    config["output_device"] = output_combo.get()
    save_config()

# TODO this should be auto set by the target which should really have
#      a corresponding input file if the packs are created well
modes = ["Notes", "EQ", "Guitar"]

for name in glob.glob("input_*.csv"):
    modes.append(name)

def on_mode_change(event):
    global ref_signal, ref_kurtosis, ref_spectrum

    if mode_combo.get() == "Notes":
        notes_entry.pack(side="left", padx=(5, 0))
    else:
        notes_entry.pack_forget()

    match mode_combo.get():
        case "Notes":
            # TODO validate the notes
            notes = notes_entry.get().strip().split()
            ref_signal, ref_kurtosis  = generate_overdrive_signal(notes)
        case "Guitar":
            ref_signal, ref_kurtosis  = generate_guitar_notes_signal()
        case "EQ":
            ref_signal, ref_kurtosis = generate_ref_signal()
        case f:
            ref_signal, ref_kurtosis = load_ref_signal(f)

    # we already had this in a lot of cases, so it's a bit wasteful
    window = np.hanning(len(ref_signal))
    spectrum = np.abs(np.fft.rfft(ref_signal * window)) * 2 / window.sum()
    freqs = np.fft.rfftfreq(len(ref_signal), d=1/44100)
    if ref_kurtosis < 10:
        spectrum = maximum_filter1d(spectrum, size=256)

    ref_spectrum = freqs, spectrum

    print(f"{mode_combo.get()} has kurtosis {ref_kurtosis}")
    update_ref_plot()

ref_signal = None
ref_kurtosis = None
ref_spectrum = None

# TODO play the target (requires a matching .mp3 or .wav)
targets = ["None"]
for name in glob.glob("target_*.csv"):
    targets.append(name)

def on_target_change(e):
    global target
    match target_combo.get():
        case "None":
            target = None
        case f:
            target = load_ref_spectrum(f, rescale=0)
    update_plot()

target = None

phase = 0
def callback(indata, outdata, frames, time, status):
    # indata: captured from mic (numpy array)
    # outdata: fill this with your signal to send
    global phase

    start = int(phase % len(ref_signal))
    idx = np.arange(frames) + start
    scale = 10 ** (send_volume / 20)
    outdata[:] = (ref_signal[idx % len(ref_signal)] * scale).reshape(-1, 1)

    # hack to use the loopback to debug
    #input_buffer.extend(outdata[:, 0])

    input_buffer.extend(indata[:, 0])

    phase = (phase + frames) % len(ref_signal)

stream = None
sample_seconds = 2
buffer_size = 44100 * sample_seconds
input_buffer = None

# start with a bit of head room to grow into
# really we should have a calibration step for a given setup
send_volume = -10.0

# TODO receive volume slider
# (this is just to visually line up with the target)
recv_volume = 0.0 #10.0

# TODO target volume slider
target_volume = 0.0

def start():
    global stream
    global input_buffer
    global phase
    input_combo.config(state="disabled")
    output_combo.config(state="disabled")
    stream = sd.Stream(
        device=(input_combo.get(), output_combo.get()),
        samplerate=44100,
        channels=1,
        callback=callback
    )
    input_buffer = deque(maxlen=buffer_size)
    phase = 0
    stream.start()
    start_stop.config(text="Stop", command=stop)
    save_btn.config(state="readonly")

def stop():
    global stream
    global input_buffer
    global phase

    #stream.stop() # super flakey and blocks like crazy
    stream.abort()
    stream.close()

    stream = None
    input_buffer = None
    phase = None
    start_stop.config(text="Start", command=start)
    input_combo.config(state="readonly")
    output_combo.config(state="readonly")
    save_btn.config(state="disabled")

def update_plot():
    ax.clear()
    setup_freq_axis(ax)
    ax.set_ylabel("dB")

    if target is not None:
        freqs, spectrum = target
        db = 20 * np.log10(np.maximum(spectrum, 1e-10)) + target_volume
        ax.plot(freqs, db, color='green')

    if input_buffer is not None and len(input_buffer) == buffer_size:
        data = np.array(input_buffer)
        window = np.hanning(len(data))
        spectrum = np.abs(np.fft.rfft(data * window)) * 2 / window.sum()
        freqs = np.fft.rfftfreq(len(data), d=1/44100)

        if ref_kurtosis < 10:
            spectrum = maximum_filter1d(spectrum, size=256)
            #spectrum = median_filter(spectrum, size=256)

        db = 20 * np.log10(np.maximum(spectrum, 1e-10)) + recv_volume

        # if ref_kurtosis < 10:
        #     ax.scatter(freqs, db, s=5)
        # else:
        ax.plot(freqs, db)

        update_ref_plot()
        canvas.draw()
    canvas.draw_idle()
    root.after(250, update_plot)  # refresh this many ms

def update_ref_plot():
    ax_ref.clear()
    if ref_signal is not None:
        setup_freq_axis(ax_ref, ylim=(-60, -20), minors=False)

        freqs, spectrum = ref_spectrum
        db = 20 * np.log10(np.maximum(spectrum, 1e-10))

        ax_ref.plot(freqs, db, color='red')

    canvas.draw_idle()

# a single frequency with no overtones
def generate_overdrive_signal(notes):
    # TODO save to config
    # TODO populated when loading a target file

    freqs = []
    for n in notes:
        # could handle flats and missing octaves here
        if note := NOTE_FREQS.get(n.upper()):
            freqs.append(note)
    if not freqs:
        return None, None

    t = np.arange(buffer_size) / 44100
    signal = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    signal = 0.0178 * (signal / len(freqs)).astype(np.float32)
    window = np.hanning(len(signal))
    spectrum = np.abs(np.fft.rfft(signal * window)) * 2 / window.sum()
    k = kurtosis(np.abs(spectrum))
    return signal, k

# "white noise" in the range of guitar frequencies (80-8000Hz)
def generate_ref_signal():
    freqs = np.fft.rfftfreq(buffer_size, d=1/44100)
    spectrum = np.zeros(len(freqs), dtype=complex)
    mask = (freqs >= 80) & (freqs <= 16000)
    rng = np.random.default_rng(42)
    spectrum[mask] = np.exp(2j * np.pi * rng.uniform(size=mask.sum()))
    signal = np.fft.irfft(spectrum)
    signal = signal / np.sqrt(np.mean(signal**2))
    k = kurtosis(np.abs(spectrum))
    return signal.astype(np.float32), k

def load_ref_signal(filename):
    freqs, spectrum = load_ref_spectrum(filename)
    rng = np.random.default_rng(42)
    # adding random phase so that our signal doesn't pulse
    phase = np.exp(2j * np.pi * rng.uniform(size=len(spectrum)))
    signal = np.fft.irfft(spectrum * phase)
    signal = signal / np.sqrt(np.mean(signal**2))
    signal = signal * 10 ** (-35 / 20)
    k = kurtosis(np.abs(spectrum))
    return signal, k

def load_ref_spectrum(filename, rescale=None):
    print(f"loading {filename}")
    with open(filename) as f:
        freqs = []
        spectrum = []
        for row in csv.DictReader(f):
            freqs.append(float(row["freq"]))
            spectrum.append(float(row["value"]))
        print(f"... done with {filename}")
        spectrum = np.array(spectrum)

        # in db
        if rescale is not None:
            target = 10 ** (rescale / 20)
            spectrum = spectrum * (target / np.max(np.abs(spectrum)))

        return freqs, spectrum

# weird idea that basically plays every note once and adds 4 octaves of
# overtones
def generate_guitar_notes_signal(harmonics=8):
    freqs = np.fft.rfftfreq(buffer_size, d=1/44100)
    spectrum = np.zeros(len(freqs), dtype=complex)
    rng = np.random.default_rng(42)

    # all semitones from E2 (82Hz) to E6 (1320Hz)
    for semitone in range(48):  # 4 octaves = 48 semitones
        fundamental = 82.41 * 2 ** (semitone / 12)
        for h in range(1, harmonics + 1):
            freq = fundamental * h
            if freq > 8000:
                break
            bin_idx = int(round(freq * buffer_size / 44100))
            if bin_idx < len(spectrum):
                spectrum[bin_idx] = (1.0 / h) * rng.uniform(0.8, 1.2) * np.exp(2j * np.pi * rng.uniform())

    signal = np.fft.irfft(spectrum)
    # scaled so it isn't too loud
    signal = 0.4 * signal / np.abs(signal).max()

    k = kurtosis(np.abs(signal))
    return signal.astype(np.float32), k

root = tk.Tk()
root.option_add('*Font', 'TkDefaultFont 18')
root.title("ToneMancer")

# in the webapp, this would all be behind a gear menu popup
ttk.Label(root, text="Input Device:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
input_combo = ttk.Combobox(root, state="readonly", width=50)
input_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
input_combo.bind("<<ComboboxSelected>>", on_input_change)

ttk.Label(root, text="Output Device:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
output_combo = ttk.Combobox(root, state="readonly", width=50)
output_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")
output_combo.bind("<<ComboboxSelected>>", on_output_change)

ttk.Label(root, text="Target:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
target_combo = ttk.Combobox(root, state="readonly", values=targets, width=64)
target_combo.grid(row=2, column=1, padx=5, pady=5, sticky="w")
target_combo.bind("<<ComboboxSelected>>", on_target_change)
target_combo.current(0)

ttk.Label(root, text="Mode:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
mode_frame = ttk.Frame(root)
mode_frame.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
mode_combo = ttk.Combobox(mode_frame, state="readonly", values=modes, width=20)
mode_combo.pack(side="left")
mode_combo.bind("<<ComboboxSelected>>", on_mode_change)
mode_combo.current(1)

notes_entry = ttk.Entry(mode_frame, width=20)
notes_entry.insert(0, "B4")
notes_entry.bind("<Return>", on_mode_change)
notes_entry.bind("<FocusOut>", on_mode_change)

# ttk.Button(root, text="Refresh", command=refresh).grid(row=2, column=1, padx=5, pady=5, sticky="e")

start_stop = ttk.Button(root, text="Start", command=start)
start_stop.grid(row=2, column=1, padx=5, pady=5, sticky="e")

# TODO save button (with a filename box) that dumps the current response to csv

# TODO record button to create a much better reference input than the midi

# TODO pink noise input

ttk.Label(root, text="Save:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
save_frame = ttk.Frame(root)
save_frame.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
save_entry = ttk.Entry(save_frame, width=30)
save_entry.pack(side="left", fill="x", expand=True)
save_entry.insert(0, "response_")

def save_response():
    if input_buffer is None or len(input_buffer) < buffer_size:
        print("No data to save")
        return
    data = np.array(input_buffer)
    window = np.hanning(len(data))
    spectrum = np.abs(np.fft.rfft(data * window)) * 2 / window.sum()
    freqs = np.fft.rfftfreq(len(data), d=1/44100)
    name = save_entry.get().strip()
    name = name.replace(".csv", "")
    m = re.search(r'(\d+)$', name)
    if m:
        num = int(m.group(1)) + 1
        new_name = name[:m.start(1)] + str(num)
    else:
        num = 0
        new_name = name + '_1'
        name += "_0"

    np.savetxt(name + ".csv", np.column_stack([freqs, spectrum]), delimiter=',', header='freq,value', comments='')
    print(f"Saved {name}.csv")

    save_entry.delete(0, tk.END)
    save_entry.insert(0, new_name)

save_btn = ttk.Button(save_frame, text="Save", command=save_response)
save_btn.pack(side="left", padx=(5, 0))
save_btn.config(state="disabled")

def update_send_volume(v):
    global send_volume
    print(f"send volume set to {v}")
    send_volume = float(v)

ttk.Label(root, text="Send Vol:").grid(row=5, column=0, padx=5, pady=5, sticky="w")
send_slider = ttk.Scale(root, from_=-40, to=0, orient="horizontal", command=update_send_volume)
send_slider.set(send_volume)
send_slider.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

fig = Figure()
ax = fig.add_subplot(111)
ax_ref = fig.add_axes([0.75, 0.75, 0.15, 0.13])
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
root.columnconfigure(0, weight=0)
root.columnconfigure(1, weight=1)
root.rowconfigure(6, weight=1)  # whichever row the canvas is in


refresh()
on_mode_change(None)
update_plot()
root.mainloop()

# mesa boogie
# 80 Hz
# 240 Hz
# 750 Hz
# 2200 Hz
# 6600 Hz

# Local Variables:
# compile-command: "python3 tonemancer.py"
# End:
