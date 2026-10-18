# Third-party component and model notices

This document is a starting inventory, not a legal opinion. Check current package metadata before making a redistribution.

| Component | Role in GoMD | Distribution status | License / action |
|---|---|---|---|
| Python | Runtime | Not bundled | Python license; use a supported 64-bit Windows distribution |
| PySide6 / Qt for Python | Desktop UI | Dependency, not vendored in source ZIP | Qt for Python has LGPLv3/GPLv3/commercial licensing options depending on edition/component; review the exact package and Qt terms |
| NumPy | Numerical utilities | Dependency, not vendored | BSD-style license; inspect the installed package's license file |
| Matplotlib | Graphs and analysis previews | Dependency, not vendored | Matplotlib license; inspect the installed package's license file |
| pytest | Tests | Development-only dependency | MIT license; not needed to run the app |
| Piper | Optional external local TTS CLI | Not bundled | Different Piper distributions/forks may have different terms; review the exact engine build, its version and license before redistribution |
| Piper voice models | Downloaded on explicit user action | Not bundled in release ZIP | Model-specific licenses vary. Open the model's `MODEL_CARD`/source page before use, especially commercial use and redistribution |
| FFmpeg | Optional audio post-processing | External executable, not bundled | FFmpeg build licensing depends on configuration; review the exact binary/build license and enabled codecs |

Live voice catalogue: https://huggingface.co/rhasspy/piper-voices
Piper example/project background: https://github.com/rhasspy/piper
Qt for Python licensing: https://doc.qt.io/qtforpython-6/licenses.html
NumPy licensing: https://numpy.org/doc/stable/license.html
Matplotlib licensing: https://matplotlib.org/stable/project/license.html
FFmpeg legal information: https://ffmpeg.org/legal.html

GoMD does not claim that a given voice is commercially usable solely because it appears in the online catalogue. Use the source/model card as the authoritative starting point, keep a copy of any required notice, and verify the license terms yourself.
