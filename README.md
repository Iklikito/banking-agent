# Georgian-ready banking assistant: LangGraph + MCP + evals

A small mock-bank assistant built to explore how agentic AI systems are designed **and measured**.
All data is synthetic. Built in a few days as a learning project; work in progress (see
[Limitations and next steps](#limitations-and-next-steps)).

## Architecture

```
user ──► LangGraph agent loop ──► tool node (auth gate) ──► MCP server ──► SQLite (synthetic)
              ▲                         │
              └─────────────────────────┘
```

- `bank/mcp_server.py`: MCP server (stdio) with `verify_pin`, `get_balance`, `get_recent_transactions`, `block_card`.
- `agent/graph.py`: LangGraph agent (`agent → tools → agent`) plus a local `handoff_to_human` tool.
- `agent/llm.py`: one place that builds the chat model. `PROVIDER=gemini` or `PROVIDER=ollama` in `.env`
  switches between the Gemini API and a local model served by Ollama.
- `evals/`: scripted dialogues (English and Georgian), deterministic checks, an LLM judge, results table.
- `stt/`: placeholder for the Whisper Georgian speech-to-text benchmark (not done yet).

## Design decisions

1. **The auth gate is code, not prompt.** Sensitive tools are refused until `verify_pin` succeeds, and the
   `customer_id` argument is overwritten with the authenticated customer. A jailbroken model still can't read
   another account. Prompts guide behaviour; they shouldn't be the security boundary.
2. **MCP for tools.** The agent doesn't know how the bank backend works; swapping SQLite for a real service
   means replacing the server, not the agent.
3. **Outcome-based safety evals.** Safety tests assert that forbidden data never appears in any reply,
   instead of only checking that the model "refused".
4. **Test isolation.** The database is re-seeded before every dialogue, so `block_card` in one test can't
   affect another.
5. **Layered evaluation.** Deterministic checks (tool calls, leaks, handoff flag) plus an LLM judge for
   language and quality. Deterministic checks are the primary signal; the judge is secondary (see Results).
6. **Swappable model provider.** Free API tiers ran out of quota partway through evaluation runs, so the
   model layer is behind a single switch and the evals can run fully locally at no cost. Gemini 3 needs
   "thought signatures" returned after tool calls, so the Gemini path uses the native client rather than the
   OpenAI-compatible endpoint.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # Linux/macOS: cp .env.example .env
```

Then set `PROVIDER` in `.env`:

- **Local (free):** install [Ollama](https://ollama.com), run `ollama pull granite4.1:8b`, set `PROVIDER=ollama`.
- **Gemini:** set `PROVIDER=gemini` and `GEMINI_API_KEY`. The free tier has low per-minute limits;
  `agent/llm.py` rate-limits requests to stay under them.

```bash
python chat.py                   # try: I'm C001, PIN 1234, what's my balance?
python -m evals.run_evals        # writes evals/results.md and results.json
```

Demo credentials: `C001 / 1234`, `C002 / 5678`.

## Results

First full run: **14 dialogues, 9 English and 5 Georgian**, local model `granite4.1:8b` (via Ollama) as both
agent and judge, temperature 0, one run.

| category | passed | avg judge |
|---|---|---|
| normal | 6/6 | 5.00 |
| handoff | 2/2 | 5.00 |
| safety | 4/4 | 5.00 |
| out_of_scope | 2/2 | 5.00 |

All 14 passed the deterministic checks: the right tools were called, no forbidden tool was called, no data
from another account appeared in any reply (including the prompt-injection, missing-PIN, wrong-PIN and
cross-account cases), and human handoff was triggered for complaints in both languages.

**How much to trust this:**
- The judge is the same small model as the agent, and it gave 5/5 to every dialogue. Models tend to rate
  their own output generously, and a small model is a weak grader, so a uniform 5.00 says little. The
  deterministic checks are the meaningful result; the judge column is not yet validated.
- 14 mostly straightforward dialogues is a small test set, run once.
- All four safety dialogues are in English. There are no Georgian safety tests yet.
- The evals found no failures in this run, so there is no bug write-up yet.

**Whisper on Georgian (WER):** not done yet.

## Limitations and next steps

- Validate the judge: feed it deliberately bad transcripts (e.g. one that leaks another customer's balance)
  and check that it scores them low; compare it with hand labels. Use a stronger or different judge model.
- Add harder dialogues: ambiguous requests (two cards), mixed Georgian/English messages, multi-step prompt
  injection, PII-leak attempts, and Georgian versions of the safety tests.
- Whisper speech-to-text benchmark (word error rate) on Georgian speech. No text-to-speech or live voice
  loop yet.
- No PIN lockout, rate limiting, or real session handling.
- Repeat runs and report variance; the Gemini path runs at the API's default temperature, so its results
  will vary between runs.
