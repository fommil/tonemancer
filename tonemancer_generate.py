# Generate a WAV test signal for characterising
# nonlinear audio devices (distortion pedals, amp stages, etc.)
#
# Sections:
#
#   1. Frequency sweeps (log) at multiple amplitudes
#      reveals frequency response at different drive levels
#
#   2. Amplitude sweeps at fixed frequencies
#      reveals the static waveshaping / transfer curve
#
#   3. Two-tone intermodulation tests
#      a) Fixed musical intervals at a reference frequency
#      b) One tone sweeps against a fixed tone
#      -> reveals intermodulation distortion behaviour
#
# All sections separated by short silence gaps.
# Markers are printed to stdout with timestamps for easy navigation.

import numpy as np
import wave
import struct
import sys

# ── Parameters ──────────────────────────────────────────────────────
SAMPLE_RATE = 44100
BIT_DEPTH = 16
SWEEP_DURATION = 10.0        # seconds per sweep/test section
SILENCE_GAP = 1.0            # seconds between sections
FREQ_LO = 40.0               # Hz
FREQ_HI = 10000.0            # Hz

# Amplitude levels for frequency sweeps (as fraction of full scale)
# -6 dB steps: 1.0, 0.5, 0.25, 0.125
FREQ_SWEEP_AMPLITUDES = [1.0, 0.5, 0.25, 0.125]

# Frequencies for amplitude sweeps (Hz)
# Low E, A, mid guitar range, upper harmonics
AMP_SWEEP_FREQS = [82.4, 220.0, 440.0, 1000.0, 3000.0]

# Two-tone sweep: fixed tone + swept tone
IMD_SWEEP_FIXED_FREQ = 220.0
IMD_SWEEP_AMPLITUDE = 0.5

def log_sweep(duration, f_lo, f_hi, amplitude, sr):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    phase = 2 * np.pi * f_lo * duration / np.log(f_hi / f_lo) * (
        np.exp(t / duration * np.log(f_hi / f_lo)) - 1
    )
    return amplitude * np.sin(phase)

def sine(duration, freq, amplitude, sr):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)

def amplitude_sweep(duration, freq, sr):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    envelope = t / duration
    return envelope * np.sin(2 * np.pi * freq * t)

def two_tone(duration, f1, f2, amp1, amp2, sr):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return amp1 * np.sin(2 * np.pi * f1 * t) + amp2 * np.sin(2 * np.pi * f2 * t)

def two_tone_sweep(duration, f_fixed, f_lo, f_hi, amplitude, sr):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    fixed = amplitude * np.sin(2 * np.pi * f_fixed * t)
    phase = 2 * np.pi * f_lo * duration / np.log(f_hi / f_lo) * (
        np.exp(t / duration * np.log(f_hi / f_lo)) - 1
    )
    swept = amplitude * np.sin(phase)
    return fixed + swept

def silence(duration, sr):
    return np.zeros(int(sr * duration))

def fade_edges(signal, fade_ms=10, sr=44100):
    fade_samples = int(sr * fade_ms / 1000)
    fade_samples = min(fade_samples, len(signal) // 2)
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    signal[:fade_samples] *= fade_in
    signal[-fade_samples:] *= fade_out
    return signal


def write_wav(filename, data, sr, bit_depth=16):
    # Clip to [-1, 1] then scale
    data = np.clip(data, -1.0, 1.0)
    if bit_depth == 16:
        max_val = 32767
        fmt = "<h"
        sampwidth = 2
    elif bit_depth == 24:
        max_val = 8388607
        fmt = None  # handled separately
        sampwidth = 3
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")

    int_data = (data * max_val).astype(np.int32)

    with wave.open(filename, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sr)
        if bit_depth == 16:
            frames = struct.pack(f"<{len(int_data)}h", *int_data)
        else:
            # 24-bit: pack each sample as 3 bytes, little-endian
            frames = b""
            for s in int_data:
                frames += struct.pack("<i", s)[:3]
        wf.writeframes(frames)

def db_str(amplitude):
    if amplitude <= 0:
        return "-inf dB"
    return f"{20 * np.log10(amplitude):+.1f} dB"

def main():
    sections = []
    markers = []
    current_time = 0.0

    def add_section(signal, label):
        nonlocal current_time
        signal = fade_edges(signal.copy(), fade_ms=10, sr=SAMPLE_RATE)
        markers.append((current_time, label))
        sections.append(signal)
        current_time += len(signal) / SAMPLE_RATE
        # add silence gap
        gap = silence(SILENCE_GAP, SAMPLE_RATE)
        sections.append(gap)
        current_time += SILENCE_GAP

    # ── Section 1: Frequency sweeps at multiple amplitudes ──────────
    for amp in FREQ_SWEEP_AMPLITUDES:
        label = f"Freq sweep {FREQ_LO:.0f}-{FREQ_HI:.0f} Hz @ {db_str(amp)}"
        sig = log_sweep(SWEEP_DURATION, FREQ_LO, FREQ_HI, amp, SAMPLE_RATE)
        add_section(sig, label)

    # ── Section 2: Amplitude sweeps at fixed frequencies ────────────
    for freq in AMP_SWEEP_FREQS:
        label = f"Amplitude sweep 0->full @ {freq:.1f} Hz"
        sig = amplitude_sweep(SWEEP_DURATION, freq, SAMPLE_RATE)
        add_section(sig, label)

    # ── Section 3: Two-tone sweep (swept tone vs fixed tone) ───────
    label = (
        f"Two-tone sweep: fixed {IMD_SWEEP_FIXED_FREQ:.0f} Hz + "
        f"sweep {FREQ_HI:.0f}->{FREQ_LO:.0f} Hz @ {db_str(IMD_SWEEP_AMPLITUDE)} each"
    )
    # Sweep high to low as requested
    sig = two_tone_sweep(
        SWEEP_DURATION, IMD_SWEEP_FIXED_FREQ,
        FREQ_HI, FREQ_LO,  # reversed: high to low
        IMD_SWEEP_AMPLITUDE, SAMPLE_RATE,
    )
    add_section(sig, label)

    # Also do the reverse: low to high
    label = (
        f"Two-tone sweep: fixed {IMD_SWEEP_FIXED_FREQ:.0f} Hz + "
        f"sweep {FREQ_LO:.0f}->{FREQ_HI:.0f} Hz @ {db_str(IMD_SWEEP_AMPLITUDE)} each"
    )
    sig = two_tone_sweep(
        SWEEP_DURATION, IMD_SWEEP_FIXED_FREQ,
        FREQ_LO, FREQ_HI,
        IMD_SWEEP_AMPLITUDE, SAMPLE_RATE,
    )
    add_section(sig, label)

    # ── Concatenate and write ───────────────────────────────────────
    full_signal = np.concatenate(sections)
    total_duration = len(full_signal) / SAMPLE_RATE

    filename = "full_sweep.wav"
    write_wav(filename, full_signal, SAMPLE_RATE, BIT_DEPTH)

    # ── Print marker table ──────────────────────────────────────────
    print(f"Written: {filename}")
    print(f"Duration: {total_duration:.1f}s ({total_duration/60:.1f} min)")
    print(f"Sample rate: {SAMPLE_RATE} Hz, {BIT_DEPTH}-bit mono")
    print()
    print("Section markers:")
    print(f"{'Time':>10}  Description")
    print(f"{'----':>10}  -----------")
    for t, label in markers:
        mins = int(t // 60)
        secs = t % 60
        print(f"  {mins:02d}:{secs:05.2f}  {label}")

    # ── Write Audacity label file ───────────────────────────────────
    label_filename = "full_sweep_labels.txt"
    with open(label_filename, "w") as f:
        for i, (t, label) in enumerate(markers):
            # Region label: start to start of next section (or end)
            if i + 1 < len(markers):
                end_t = markers[i + 1][0]
            else:
                end_t = total_duration
            f.write(f"{t:.6f}\t{end_t:.6f}\t{label}\n")
    print(f"\nAudacity labels: {label_filename}")
    print("  Import via: File -> Import -> Labels")


if __name__ == "__main__":
    main()

# Local Variables:
# compile-command: "python3 tonemancer_generate.py"
# End:
