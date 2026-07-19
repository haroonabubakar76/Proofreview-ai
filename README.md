# ProofReview

**Evidence-backed AI code reviews for pull requests.** Instead of filling a diff with speculative comments, ProofReview traces each finding to a concrete risk signal, generates a focused reproduction, and publishes only findings that pass verification.

## Hackathon MVP

- Paste a pull-request diff or use the included seeded payment-service PR.
- Review a public GitHub pull request by entering `owner/repository` and its PR number. Set `GITHUB_TOKEN` to review private repositories or avoid unauthenticated rate limits.
- Upload one or more local code files when a GitHub token is unavailable.
- Detect high-impact security and stability risks.
- Show the exact file and line, severity, suggested patch, and an evidence trace.
- Produce a PR risk score that is explainable rather than opaque.
- Optionally call GPT-5.6 for a second-pass analysis when `OPENAI_API_KEY` is set.
- Export GitHub-compatible inline comment payloads (posting is deliberately opt-in).

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The demo mode works without credentials. To enable the model pass, set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in your environment.

## Custom PR demo

Click **Run custom PR**. Enter a GitHub repository and PR number, then optionally select **Use GPT-5.6 investigation pass**. Public PRs work without a token subject to GitHub's rate limits; private PRs need `GITHUB_TOKEN`. Alternatively, upload local code files in the same panel.

For a repeatable verification demo, upload `examples/local_pr_fixture.py`. It produces two candidates: one verified dynamic-code-execution finding and one suppressed SQL-looking string that never reaches a database execution sink.

## Demo story

1. Click **Run seeded PR**.
2. The changed payment service concatenates user input into SQL and removes an authorization guard.
3. ProofReview shows only the verified critical findings, their reproduction evidence, and safe replacements.
4. Click an inline finding to inspect the agent trace, then export review comments ready for GitHub.

## Architecture

`PR input → Context/rule scan → GPT investigation (optional) → verifier → evidence-backed inline report`

The verifier is intentionally a hard gate: an LLM proposal is not displayed unless a deterministic check or generated reproduction supports it. In production, run generated tests in a sandboxed worker and use GitHub App webhooks plus the Pull Request Review API.

## Codex collaboration

Codex was used to create the product scope, implement the FastAPI service and dashboard, craft the seeded demo scenario, and add the deterministic verification gate. Product decisions were kept focused on reviewer trust: a small number of evidence-backed comments beats broad, noisy feedback.
