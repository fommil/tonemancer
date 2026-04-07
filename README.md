ToneMancer is an app for guitar players that lets them tone match their favourite artists with their existing gear. It is designed specifically for tone matching (or just exploring) overdrive and (para or graphic) eq pedals.

An [Audio Splitter](https://www.amazon.co.uk/dp/B07PX1ZNCL), [Passive volume controller](https://www.amazon.co.uk/dp/B0DPKHNVMY) and a pair of [Male 1/8 inch to Female 1/4 adapters](https://www.amazon.co.uk/dp/B0D8FPSQ13) may be needed. The headphone socket is the SEND (goes into the start of the effects loop) and the mic is the RECEIVE.

Initially available as a desktop python app, this might have a webapp one day.

Tones for artists must be created separately, see the `tonemancer_generate.py` file for some tips on that.

# Installation

Requires a python environment with `matplotlib`, `numpy`, `librosa`, `sounddevice`, `tk` and `scipy`.

Start with `python3 tonemancer.py`.

The interface is a bit clunky, but the general idea is to use "Notes" to send/receive individual frequencies for distortion harmonic analysis. Make sure to check your outbound volume levels first (use the slider) so that you're not overpowering your pedals and clipping. Similarly, return volumes may need to be reduced because computer headphone sockets are used to receiving low power signals, hence why I use a passive volume controller (but if you have a high end DAC you might not need that). I wrote an article detailing how I used this to chart the [distortion responses](https://medium.com/@fommil/guitar-distortion-response-753a2f0ab938) of my own pedals.

The "EQ" mode is a white noise that can be used for EQ balancing.

# Creating Data Packs

To create data packs ("modes" are for your playing, "targets" are the artist you want to sound like) requires using an external tool like Audacity to create wav files (ideally mono at 44100Hz). Prefix them `mode_` to show up as a Mode or `target_` to show up as a Target.

I recommend making at least two samples per artist: one for a constant note with their characteristic overdrive. Another up to 10 seconds for a main riff or verse. Make sure to use [demucs](https://github.com/adefossez/demucs) to isolate the guitar tracks if you don't have a single channel already. Then record yourself playing the exact same things, direct.

You can also consider using MIDI inputs, e.g. by getting songsterr midi then manually removing all the other instruments and converting the distorted guitar to a clean or muted channel. But I found the synthetic instruments are so bad that it's not really worth it.
