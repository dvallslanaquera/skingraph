- 1. src/verify.py works for debugging and CLI entrypoint, but not as a prod-ready tool. Change to the following:
     Add validation logic in state.py, add tests in tests/test_state.py and tests/test_pipeline.py and use README.md to explain how state flows.

- 2. README: add explanation about how state flows

Questions to cover:

- why graph workflow?
- why Gemini?
