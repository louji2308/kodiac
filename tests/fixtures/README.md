# tests/fixtures/

Offline fixtures and recorded responses enabling 100% deterministic, zero-network unit testing and CI.

- `clips/`: Small test clips (<= 2MB each) representing baseline correct runs and failure modes (B1, B2, B9, occluded).
- `sam/`: Recorded SAM 3.1 streaming responses keyed by `(model, prompt, direction, clip_sha)`.
- `spark/`: Recorded Muse Spark 1.3 structured outputs.
- `voice/`: Recorded Muse Voice transcripts for `stack_blocks` instructions.
