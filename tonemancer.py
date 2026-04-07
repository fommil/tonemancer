#!/usr/bin/env python3

# this is the desktop app, it will have a webapp equivalent one day

from collections import deque

import glob
import json
from pathlib import Path
import re
import threading
import wave

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import ttk
from scipy.ndimage import maximum_filter1d
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

fixed_modes = ["Notes", "EQ", "Manual"]
modes = fixed_modes.copy()

for name in glob.glob("mode_*.wav"):
    modes.append(name)

# there's loads of potential for race conditions here but worst case it should
# fix itself within a few seconds.
def on_mode_change(event):
    global ref_signal, ref_kurtosis, ref_spectrum, phase, input_buffer

    if mode_combo.get() == "Notes":
        notes_entry.pack(side="left", padx=(5, 0))
    else:
        notes_entry.pack_forget()

    if mode_combo.get() in fixed_modes:
        wav_check.pack_forget()
    else:
        wav_check.pack(side="left", padx=(10, 0))

    match mode_combo.get():
        case "Manual":
            # special case
            with buf_lock:
                ref_signal = None
                ref_kurtosis = None
                ref_spectrum = None
                phase = None
                input_buffer = deque(maxlen=buffer_size)
                return
        case "Notes":
            # TODO validate the notes
            notes = notes_entry.get().strip().split()
            ref_signal, ref_kurtosis  = generate_overdrive_signal(notes)
        case "EQ":
            ref_signal, ref_kurtosis = generate_ref_signal()
        case f:
            ref_signal, ref_kurtosis = load_ref_signal(f)

    with buf_lock:
        input_buffer = deque(maxlen=len(ref_signal))
        phase = 0

    # calculates a normalisation factor where the peak in the frequency space
    # hits 0db.
    _, spectrum = chunk_spectrum(ref_signal)
    peak_spectrum = np.max(spectrum)
    if peak_spectrum > 0:
        ref_signal = ref_signal / peak_spectrum

    # compute display spectrum at current send volume
    scaled = ref_signal * 10 ** (send_volume / 20)
    freqs, spectrum = chunk_spectrum(scaled)
    if ref_kurtosis < 10:
        spectrum = maximum_filter1d(spectrum, size=256)

    ref_spectrum = freqs, spectrum

    print(f"{mode_combo.get()} has kurtosis {ref_kurtosis}")
    update_ref_plot()

ref_signal = None
phase = 0

ref_kurtosis = None
ref_spectrum = None

# TODO play the target audibly
targets = ["None"]
for name in glob.glob("target_*.wav"):
    targets.append(name)

# TODO it might be an idea to have automatic mode selection
# when changing the target, based on filename conventions

def on_target_change(e):
    global target
    match target_combo.get():
        case "None":
            target = None
        case f:
            signal = load_wav(f)
            target = chunk_spectrum(signal)
    update_plot()

target = None

def callback(indata, outdata, frames, time, status):
    # indata: captured from mic (numpy array)
    # outdata: fill this with your signal to send
    global phase, input_buffer, ref_signal

    with buf_lock:
        buf = input_buffer
        sig = ref_signal
        p = phase

    if sig is None:
        # could be random noise in there, mute it
        outdata[:] = 0
    else:
        start = int(p % len(sig))
        idx = np.arange(frames) + start
        scale = 10 ** (send_volume / 20)
        outdata[:] = (sig[idx % len(sig)] * scale).reshape(-1, 1)

    if buf is None:
        return

    # hack to use the loopback to debug
    #buf.extend(outdata[:, 0])
    buf.extend(indata[:, 0])

    # cover off a potential race condition here if the ref_signal and phase
    # changed since we last looked. This wouldn't recover naturally unless the
    # signals were the same length up to modulo the indata size.
    if sig is not None:
        with buf_lock:
            if p == phase:
                phase = (phase + frames) % len(sig)

stream = None
sample_seconds = 2
input_buffer = None

# used for instanteous response signals
buffer_size = 44100 * sample_seconds

buf_lock = threading.Lock()

# start with a bit of head room to grow into
# really we should have a calibration step for a given setup
send_volume = -40.0

# TODO receive volume slider
# (this is just to visually line up with the target)
recv_volume = 0.0 #10.0

# TODO target volume slider
target_volume = 0.0

def start():
    global stream

    input_combo.config(state="disabled")
    output_combo.config(state="disabled")
    stream = sd.Stream(
        device=(input_combo.get(), output_combo.get()),
        samplerate=44100,
        channels=1,
        callback=callback
    )
    stream.start()
    start_stop.config(text="Stop", command=stop)
    save_btn.config(state="readonly")

def stop():
    global stream

    #stream.stop() # super flakey and blocks like crazy
    stream.abort()
    stream.close()

    stream = None
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

    with buf_lock:
        buf = input_buffer

    #print(f"buffer is {len(buf)} bytes")
    if buf is not None and len(buf) >= 22050:
        data = np.array(buf)
        freqs, spectrum = chunk_spectrum(data)

        if ref_kurtosis is not None and ref_kurtosis < 10:
            spectrum = maximum_filter1d(spectrum, size=256)
            #spectrum = median_filter(spectrum, size=256)

        db = 20 * np.log10(np.maximum(spectrum, 1e-10)) + recv_volume

        ax.plot(freqs, db)

        update_ref_plot()

        # don't plot this if it's not an instanteous signal
        if mode_combo.get() in fixed_modes or fast_hack.get():
            ax_wave.set_visible(True)
            ax_wave.clear()
            n_show = int(44100 * 0.03)  # 30ms window
            start = len(data) - n_show * 10
            for j in range(start, len(data) - n_show):
                if data[j] <= 0 and data[j + 1] > 0:
                    start = j
                    break
            snippet = data[start:start + n_show]
            t_ms = np.arange(len(snippet)) / 44.1
            ax_wave.plot(t_ms, snippet, color='tab:blue', linewidth=0.8)
            ax_wave.tick_params(labelsize=5)
        else:
            ax_wave.set_visible(False)

    canvas.draw()
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
    freqs = []
    for n in notes:
        # could handle flats and missing octaves here
        if note := NOTE_FREQS.get(n.upper()):
            freqs.append(note)
    if not freqs:
        return None, None

    # wraparound to the nearest full loop so we don't get a discontinuity
    lowest = min(freqs)
    period_samples = 44100 / lowest
    n_periods = round(buffer_size / period_samples)
    sig_len = int(n_periods * period_samples)
    t = np.arange(sig_len) / 44100

    signal = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    signal = (signal / len(freqs)).astype(np.float32)
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
    k = kurtosis(np.abs(spectrum))
    return signal.astype(np.float32), k

def load_ref_signal(f):
    data = load_wav(f)

    freqs, spectrum = chunk_spectrum(data, 44100)

    if fast_hack.get():
        rng = np.random.default_rng(42)
        # adding random phase so that our signal doesn't pulse
        p = np.exp(2j * np.pi * rng.uniform(size=len(spectrum)))
        signal = np.fft.irfft(spectrum * p)
    else:
        signal = data

    k = kurtosis(np.abs(spectrum))
    return signal, k

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
target_combo = ttk.Combobox(root, state="readonly", values=targets, width=48)
target_combo.grid(row=2, column=1, padx=5, pady=5, sticky="w")
target_combo.bind("<<ComboboxSelected>>", on_target_change)
target_combo.current(0)

ttk.Label(root, text="Mode:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
mode_frame = ttk.Frame(root)
mode_frame.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
mode_combo = ttk.Combobox(mode_frame, state="readonly", values=modes, width=48)
mode_combo.pack(side="left")
mode_combo.bind("<<ComboboxSelected>>", on_mode_change)
mode_combo.current(0)

notes_entry = ttk.Entry(mode_frame, width=20)
notes_entry.insert(0, "B2")
notes_entry.bind("<Return>", on_mode_change)
notes_entry.bind("<FocusOut>", on_mode_change)

fast_hack = tk.BooleanVar(value=False)
wav_check = ttk.Checkbutton(mode_frame, text="Fast Hack", variable=fast_hack, command=lambda: on_mode_change(None))

# ttk.Button(root, text="Refresh", command=refresh).grid(row=2, column=1, padx=5, pady=5, sticky="e")

start_stop = ttk.Button(root, text="Start", command=start)
start_stop.grid(row=2, column=1, padx=5, pady=5, sticky="e")

ttk.Label(root, text="Save:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
save_frame = ttk.Frame(root)
save_frame.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
save_entry = ttk.Entry(save_frame, width=30)
save_entry.pack(side="left", fill="x", expand=True)
save_entry.insert(0, "response_")

def save_response():
    with buf_lock:
        buf = input_buffer

    if buf is None:
        print("No data to save")
        return

    name = save_entry.get().strip()
    name = name.replace(".wav", "")
    data = np.array(buf)

    peak = np.max(np.abs(data))
    if peak > 1.0:
        data = data / peak
    wav_data = (data * 32767).astype(np.int16)

    with wave.open(name + ".wav", 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(wav_data.tobytes())
    print(f"Saved {name}.wav")

    # convenient feature, if the filename ends in a number, increment it
    m = re.search(r'(\d+)$', name)
    if m:
        num = int(m.group(1)) + 1
        new_name = name[:m.start(1)] + str(num)
        save_entry.delete(0, tk.END)
        save_entry.insert(0, new_name)

save_btn = ttk.Button(save_frame, text="Save", command=save_response)
save_btn.pack(side="left", padx=(5, 0))
save_btn.config(state="disabled")

def update_send_volume(v):
    global send_volume
    #print(f"send volume set to {v}")
    send_volume = float(v)

ttk.Label(root, text="Send Vol:").grid(row=5, column=0, padx=5, pady=5, sticky="w")
send_slider = ttk.Scale(root, from_=-60, to=0, orient="horizontal", command=update_send_volume)
send_slider.set(send_volume)
send_slider.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

fig = Figure()
ax = fig.add_subplot(111)
ax_ref = fig.add_axes([0.75, 0.75, 0.15, 0.13])

ax_wave = fig.add_axes([0.75, 0.60, 0.15, 0.13])

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
