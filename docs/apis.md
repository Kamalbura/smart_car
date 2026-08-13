# API Surface

## STT
- `SpeechRecognizer.bootstrap()` – validates paths/backends before ingestion.
- `SpeechRecognizer.transcribe(audio_frames)` – accepts iterable of PCM chunks and returns a transcript string.

## TTS
- `SpeechSynthesizer.bootstrap()` – ensures Piper voice exists.
- `SpeechSynthesizer.speak(prompt, output_path=None)` – synthesizes to file and returns the `Path`.

## LLM
- `LlamaRunner.ensure_ready()` – verifies llama.cpp binary + checkpoint.
- `LlamaRunner.generate(prompt, max_tokens=256)` – returns response text.

## Vision
- `YOLODetector.load()` – loads weights into memory.
- `YOLODetector.detect(frame)` – returns list of `Detection` dataclasses.
- `VisionPipeline.run(stream)` – yields batched detections over an iterator of frames.

## UI
- `WaveshareDisplay.initialize()` – configures SPI pins.
- `WaveshareDisplay.draw_frame(buffer)` – paints bytes to the screen (placeholder today).

## Core
- `ConfigLoader.load()` – builds `OrchestratorConfig` from YAML/JSON.
- `OfflineAssistant.bootstrap()` – prepares every subsystem.
- `OfflineAssistant.run_once(audio_frames, video_frames)` – executes one request/response iteration for prototyping.
