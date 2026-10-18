# Georgian-ready banking assistant: LangGraph + MCP + evals

A small mock-bank assistant built to explore how agentic AI systems are designed **and measured**.  
All data is synthetic. Built in a few days as a learning project; work in progress (see  
[Known issues](#known-issues) and [Next steps](#next-steps)).

## Architecture

```text
user ──► LangGraph agent loop ──► tool node (auth gate) ──► MCP server ──► SQLite (synthetic)
             ▲                         │
             └─────────────────────────┘
```

- `bank/mcp_server.py`: MCP server (stdio) with `verify_pin`, `get_balance`, `get_recent_transactions`, `block_card`.
- `agent/graph.py`: LangGraph agent (`agent → tools → agent`) plus a local `handoff_to_human` tool.
- `agent/llm.py`: one place that builds the chat model. `PROVIDER=gemini` or `PROVIDER=ollama` in `.env` switches between the Gemini API and a local model served by Ollama.
- `evals/`: scripted dialogues (English and Georgian), deterministic checks, an LLM judge, results table.
- `stt/`: placeholder for the Whisper Georgian speech-to-text benchmark (not done yet).

## Design decisions

1. **The auth gate is code, not prompt.** Sensitive tools are refused until `verify_pin` succeeds, and the `customer_id` argument is overwritten with the authenticated customer. A jailbroken model still can't read another account. Prompts guide behaviour; they shouldn't be the security boundary.

2. **MCP for tools.** The agent doesn't know how the bank backend works; swapping SQLite for a real service means replacing the server, not the agent.

3. **Outcome-based safety evals.** Safety tests assert that forbidden data never appears in any reply, and that destructive actions had no effect in the database, instead of only checking that the model "refused".

4. **Test isolation.** The database is re-seeded before every dialogue, so `block_card` in one test can't affect another.

5. **Layered evaluation.** Deterministic checks (tool calls and their arguments, leaks, database state, handoff flag) plus an LLM judge for language and quality. Deterministic checks are the primary signal; the judge is secondary (see Results).

6. **Swappable model provider.** Free API tiers ran out of quota partway through evaluation runs, so the model layer is behind a single switch and the evals can run fully locally at no cost. Gemini 3 needs "thought signatures" returned after tool calls, so the Gemini path uses the native client rather than the OpenAI-compatible endpoint.
7. **Wrong-PIN limit enforced on the server.** `verify_pin` counts failures per customer in SQLite: 3 wrong PINs lock the account for 5 minutes, and while locked even the correct PIN is refused (otherwise an attacker keeps guessing and just reads the last answer). The count-and-update runs inside `BEGIN IMMEDIATE` so parallel guesses can't slip past it. It lives in the tool, not in the prompt or the LLM, because the model is the thing being attacked. Tests: `python -m pytest -q`.

## Run it

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Then set `PROVIDER` in `.env`:

- **Local (free):** install [Ollama](https://ollama.com), run `ollama pull granite4.1:8b`, and set `PROVIDER=ollama`. Make sure Ollama is running before you start.
- **Gemini:** set `PROVIDER=gemini` and `GEMINI_API_KEY`. The free tier has low per-minute limits; `agent/llm.py` rate-limits requests to stay under them.

Run the assistant and evaluation suite:

```cmd
python chat.py
python -m evals.run_evals
```

The evaluation command writes results to `evals/results.md` and `evals/results.json`.

Demo credentials: `C001 / 1234`, `C002 / 5678`.

## Evaluation

`python -m evals.run_evals` runs 29 scripted dialogues (19 English, 9 Georgian, 1 mixed Georgian/English):

| Category | Dialogues | What it covers |
|---|---:|---|
| Normal | 6 | Balance, transactions and card blocking, each in English and Georgian |
| Handoff | 4 | Complaints and fraud reports must reach a human, in both languages |
| Safety | 13 | Missing or wrong PIN, prompt injection (single and multi-step), cross-account access, blocking another customer's card, system-prompt extraction, PIN echo, PIN guessing; three of them in Georgian |
| Edge | 4 | Ambiguous "block my card" with two cards, choosing a card in a follow-up, PIN given mid-sentence, mixed-language message |
| Out of scope | 2 | Weather question in both languages; no account tool may be called |

Checks per dialogue include expected and forbidden tool calls (including their arguments), strings that must never appear in any reply, final database state (for example, a card that must not end up blocked), the human-handoff flag, and a 1–5 LLM-judge score.

## Results

**First run (original 14 dialogues: 9 English, 5 Georgian)**, local model `granite4.1:8b` (via Ollama) as both agent and judge, temperature 0, one run.

| Category | Passed | Average judge score |
|---|---:|---:|
| Normal | 6/6 | 5.00 |
| Handoff | 2/2 | 5.00 |
| Safety | 4/4 | 5.00 |
| Out of scope | 2/2 | 5.00 |

All 14 passed the deterministic checks: the right tools were called, no forbidden tool was called, no data from another account appeared in any reply (including the prompt-injection, missing-PIN, wrong-PIN and cross-account cases), and human handoff was triggered for complaints in both languages.

**Extended suite (29 dialogues):** results not added yet.

**How much to trust this:**

- The judge is the same small model as the agent, and it gave 5/5 to every dialogue. Models tend to rate their own output generously, and a small model is a weak grader, so a uniform 5.00 says little. The deterministic checks are the meaningful result; the judge column is not yet validated.
- The original 14 dialogues were mostly straightforward. This was a small test set run once.

**Whisper on Georgian (WER):** not done yet.

## Known issues

- **Small local model on Georgian.** With `granite4.1:8b`, a Georgian complaint (`handoff_ka`) got a garbled text reply and no `handoff_to_human` call, so the handoff flag stayed false while the bot implied a transfer. Adding Georgian trigger words to the prompt fixed that case. Georgian runs could also degenerate into very long repetitive output at temperature 0, so generation is now capped (`OLLAMA_NUM_PREDICT`) and each dialogue has a timeout (`EVAL_TIMEOUT`); a timeout is reported as a failed dialogue.

- **PIN guessing was possible, then limited (fixed on the server).** Found by manual testing: a customer could try candidate PINs one at a time until the right one worked, and the model helpfully listed the remaining candidates. The `pin_guessing` dialogue reproduces this. Models refusing to "try all of them" is behaviour, not a guarantee, so the limit lives in `verify_pin` (see design decision below). Before/after eval results: not added yet.
- **Limitations of the lockout.** Anyone who knows a customer ID can lock that customer out for 5 minutes. "N attempts remaining" confirms the ID exists (unknown IDs get a plain `FAILED`). There is no audit log. The PIN still travels through the chat and the model API.

## Next steps

- Validate the judge: feed it deliberately bad transcripts (e.g. one that leaks another customer's balance) and check that it scores them low; compare it with hand labels. Use a stronger or different judge model.
- Run the extended 29-dialogue suite and report its results.
- Benchmark Whisper speech-to-text (word error rate) on Georgian speech. No text-to-speech or live voice loop yet.
- Repeat evaluation runs and report variance; the Gemini path runs at the API's default temperature, so its results will vary between runs.