# Voice model installation and licensing

GoMD does not bundle voice models. Open the Voice catalogue page, choose a language and click Search. Search results originate from the live Hugging Face `rhasspy/piper-voices` repository. Select a model and inspect its source/model card, including its license, source recording information, and redistribution/commercial-use conditions. Then explicitly confirm Download.

Piper models normally require a paired ONNX file and configuration file named `<model>.onnx` and `<model>.onnx.json`. Keep the pair together. The app checks the configuration JSON and basic model size; that is a sanity check, not a cryptographic verification or a substitute for checking the source.

If searching fails, check internet access and retry. Do not treat a failed/empty search as a successful catalogue response. If the model card is unavailable or ambiguous, do not assume the model can be used commercially; contact the model publisher or choose a clearly licensed alternative.

The Piper CLI executable is a separate install. In Settings, point to the actual executable. Run `piper --help` in a terminal if its CLI options differ from those expected by GoMD. GoMD does not auto-execute a program downloaded from the model catalogue.
