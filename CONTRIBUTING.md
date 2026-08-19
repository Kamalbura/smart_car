# Contributing to Smart Car

Thanks for helping make Smart Car safer, clearer, and more useful. Bug fixes,
documentation improvements, tests, and new features are welcome.

## Before you contribute

1. Open an issue first for substantial changes so the approach can be discussed.
2. Fork the repository, create a focused branch, and keep each pull request
   limited to one coherent change.
3. Do not commit secrets, generated build output, downloaded models, account
   credentials, proprietary SDKs, or third-party material unless its licence
   and redistribution terms have been reviewed.

## Pull requests

Explain the problem, the approach, any hardware used, and the tests run. Keep
the existing public interfaces and safety boundaries intact unless the pull
request explicitly documents a reviewed change to them. Update relevant
documentation and configuration examples with code changes.

Use clear, readable Python, C, Kotlin, shell, and configuration files;
preserve the project’s existing formatting and naming conventions. New original
source files should include:

```
Copyright 2026 Your Name
SPDX-License-Identifier: Apache-2.0
```

Use the comment syntax appropriate for the language. Do not replace or remove
existing copyright, licence, trademark, or attribution notices. If a change
contains third-party code or assets, retain its notices and explain its origin
and licence in the pull request.

## Testing and hardware

Run the relevant automated tests before submitting:

```
docker compose -f docker/compose.yaml run --rm dev
```

For native development, run `pytest` and the firmware CMake test suite as
described in the README. Hardware-affecting changes require bench validation
with the robot secured safely (wheels off the ground) and a description of the
test conditions, firmware version, wiring assumptions, and observed results.
Never rely solely on software tests for motor or safety behaviour.

## Attribution and licence

Contributors retain copyright in their contributions. Git history and retained
file notices provide attribution; add your own notice to substantial new files
where appropriate. By intentionally submitting a contribution for inclusion,
you license that contribution under the Apache License, Version 2.0, as set
out in Section 5 of [LICENSE](LICENSE). No copyright assignment is required.
That licence includes Apache 2.0’s normal patent grant and patent-termination
terms.
