# LocalVoice

Offline hold-to-talk dictation for Windows (NVIDIA Parakeet via onnx-asr / ONNX Runtime).

**Start by reading `docs/PLAN.md`.** It has the goals, the current state of the code, the benchmark design,
the experiment protocol and the task list. Then read `docs/BUILD_LOG.md` if it exists.

- Tests: `pip install -e .[cpu,dev] && pytest`. Windows-only tests are skipped on Linux and run in CI.
- Never invent benchmark numbers; every figure must come from `bench/results/`.
- Work on branch `claude/windows-offline-dictation`; no pushes to `main` and no PRs unless asked.
