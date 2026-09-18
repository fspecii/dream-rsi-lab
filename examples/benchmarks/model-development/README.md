# Separate model development

The Qwen2.5Coder7B runs repeatedly failed to act on tool observations even when
the correct file, match count, and line positions were supplied. We are preparing
a separate local-model experiment with Qwen3.5 9B using the same repair workflow.
This changes the model, not its weights through training, and is not evidence of
controller self-improvement. Exposed development cases remain exposed.

The [official Ollama package](https://ollama.com/library/qwen3.5:9b) lists a 6.6 GB
Q4_K_M model and Apache 2.0 license. Family-level performance tables on that page
must not be attributed to this 9B package. Its suitability for this project remains
unproven until measured locally. Download and compatibility checks precede any
registered benchmark inference; results are not available yet.
