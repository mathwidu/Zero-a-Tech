# Repository Guidelines

## Project Structure & Module Organization
- scripts/: Pipeline steps (news_fetcher.py, script_generator.py, tts.py, generate_subtitles.py, video_maker.py, etc.).
- services/talking_head/: FastAPI service (Wav2Lip) with Dockerfile and app.py.
- assets/: Source media (images, backgrounds). Not committed.
- output/ or outputs/: Generated artifacts (audio, subtitles, logs, final videos).
- pipeline.py: Orchestrates the full end‑to‑end flow and logging.
- .env: Local secrets and defaults. Never commit real keys.

## Build, Test, and Development Commands
- Create venv: `python3 -m venv .venv && source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run pipeline: `python pipeline.py --auto` or `python pipeline.py --pick 2 --skip-post`
- Start service: `docker compose up -d` (service: talking_head)
- Rebuild service: `docker compose build talking_head`
- Service health: `curl localhost:8000/health`
- Service test: `curl -X POST http://localhost:8000/talking-head -F "image=@assets/ze_bot_frente.png" -F "audio=@output/fala_01.wav" -o output/clip_test.mp4`

## Coding Style & Naming Conventions
- Python, PEP 8, 4‑space indent; file/function names in snake_case.
- Scripts live in `scripts/`; keep single‑purpose CLIs with `if __name__ == "__main__":`.
- Outputs follow existing patterns: `fala_NN.mp3`, `fala_*_words.json`, `legendas.srt`, `video_final.mp4`.
- No enforced linter; prefer clean, typed functions where helpful. Avoid committing large binaries.

## Testing Guidelines
- No formal test suite yet. Validate steps via `output/log_pipeline.txt` and artifact presence.
- For new code, add lightweight unit tests with pytest under `tests/` (`test_*.py`) and aim to cover pure helpers.
- Manual checks: run individual scripts (e.g., `python scripts/video_maker.py`) and the FastAPI endpoint.

## Commit & Pull Request Guidelines
- Use Conventional Commits where possible: `feat:`, `fix:`, `docs:`, `chore:`.
- Commits in English or Portuguese are fine; keep imperative, scoped messages.
- PRs should include: concise description, linked issues, steps to reproduce, relevant flags used, and sample outputs (e.g., `output/clip_test.mp4`). Include logs path `output/log_pipeline.txt` for failures.

## Security & Configuration Tips
- Configure `.env` with `OPENAI_API_KEY`, `ELEVEN_API_KEY`, `REPLICATE_API_TOKEN`, and output defaults. Never commit secrets.
- Wav2Lip weights mount under `services/talking_head/models` and checkpoints in container `/app/checkpoints`.
