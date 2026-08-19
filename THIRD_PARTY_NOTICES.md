# Third-party and separately obtained components

The Apache-2.0 licence in [LICENSE](LICENSE) covers the original Smart Car
source and documentation contributed to this repository. It does not change
the terms for dependencies, SDKs, services, models, or assets obtained from
other parties. This file records known boundaries; it is not a substitute for
reviewing the applicable upstream terms before distribution.

| Component | Repository status | Licensing / distribution note |
|---|---|---|
| Gradle wrapper (`mobile_app/gradlew*`, wrapper JAR) | Committed third-party build tooling | Preserve its existing Apache-2.0 notices. Gradle is Apache-2.0. |
| Android and Python dependencies | Resolved at build/install time; no vendored dependency source | Their licences and notices apply to a distributed APK, image, or binary. Generate a dependency notice/SBOM from the exact locked build before shipping. |
| Azure Speech SDK and Azure OpenAI service | Downloaded/remote service | Proprietary service and SDK terms apply separately. Do not imply that Apache-2.0 licenses them or redistribute them unless Microsoft’s terms permit it. |
| Picovoice Porcupine keyword files and AccessKeys | Not committed | Account-specific terms apply. `.ppn` files and keys must not be added to this repository. |
| Ultralytics YOLO11 code and weights | Not committed | Ultralytics states that YOLO models are AGPL-3.0 by default. Using its code or weights in a proprietary product requires an appropriate alternative licence or a replacement model with suitable terms. |
| Piper executable and voice models | Not committed; fetched separately | Piper code is MIT, but each voice model has its own model card and licence. Review the specific selected voice before redistribution. |
| whisper.cpp, llama.cpp, faster-whisper, TinyLlama and downloaded models | Not committed; expected under ignored model/third-party paths | Licences vary by component and model. Pin source, version, licence, and notices before a commercial distribution. |
| Book and image assets, including `book/images/college_logo.png` | Existing tracked material; provenance not documented in this repository | Do not assume these assets are covered by the project Apache licence. Confirm ownership or permissions before republishing them; the `book/` directory is now ignored for new files. |

The existing `book/` files remain tracked by Git. Adding `book/` to
`.gitignore` only prevents newly untracked book files from being added; it does
not remove or relicense tracked files.

For a future commercial release, keep proprietary hosted services, commercial
tools, hardware designs, and non-Apache models in separate repositories,
packages, deployment artifacts, or agreements. The Apache-2.0 Smart Car core
can remain public as long as those components are genuinely separable and all
applicable dependency obligations are met.
