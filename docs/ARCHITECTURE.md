# Architecture

- `core/`: user-space paths, atomic JSON settings and project/scene persistence.
- `mathtext/`: expression tokenization and speech expansion; no evaluation of code.
- `pronunciation/`: whole-token/phrase rules; higher numeric priority is applied first; optional context regex and language/engine scoping.
- `tts/`: `TTSAdapter` contract and Piper CLI implementation.
- `models/`: live Hugging Face file catalogue and explicit paired model downloads.
- `audio/`: PCM WAV validation, audio concatenation, silence insertion, FFmpeg post-processing and analysis.
- `graphs/`: AST validator/evaluator with allow-listed arithmetic/functions and Matplotlib export.
- `media/`: WAV discovery, safe copy/move/rename and confirmation-required deletion API.
- `vocal/`: note sequence persistence and a simple tone preview (not vocal synthesis).
- `i18n/`: RU and en-GB UI text dictionary.
- `ui/`: PySide6 UI, with long catalogue searches/downloads/synthesis sent to a worker pool.

Projects store `project.json` and independent `scenes/<id>/text.txt`, `normalized.txt`, `metadata.json`, and `audio.wav`, with project-owned `media/` and `exports/` directories. Paths are resolved and scene IDs are generated internally. Audio deletion is never a side effect of removing a project scene: the project manager only removes that scene's own directory, not the external path referenced by its metadata.
