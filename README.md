# Georgian-ready banking assistant: LangGraph + MCP + evals

A small mock-bank assistant built to explore how agentic AI systems are designed **and measured**.
All data is synthetic. Built in one day as a learning project.

## Architecture

```
user ──► LangGraph agent loop ──► tool node (auth gate) ──► MCP server ──► SQLite (synthetic)
              ▲                         │
              └─────────────────────────┘
```

- `bank/mcp_server.py`: MCP server (stdio) with `verify_pin`, `get_balance`, `get_recent_transactions`, `block_card`.
- `agent/graph.py`: LangGraph agent (`agent → tools → agent`) plus a local `handoff_to_human` tool.
- `evals/`: scripted dialogues (English + Georgian), checks, LLM judge, results table.
- `stt/`: Whisper WER benchmark on Georgian speech (TODO, see Results).

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
   language and quality. The judge is spot-checked against hand labels because judges are imperfect.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your OPENAI_API_KEY
python bank/seed.py
python chat.py              # try: I'm C001, PIN 1234, what's my balance?
python -m evals.run_evals   # writes evals/results.md and results.json
```

Demo credentials: `C001 / 1234`, `C002 / 5678`.

## Results

_Fill in after running the evals._

| category | passed | avg judge |
|---|---|---|
| | | |

**A bug the evals caught:** _describe one failure, its cause, and the fix._

**Judge vs. human labels:** _agreement on N hand-labelled dialogues._

**Whisper on Georgian (WER):** _model, dataset, number of clips, WER._

## Limitations and future work

- No TTS or live voice loop yet; STT is benchmarked offline only.
- Only ~20 dialogues; results are indicative, not statistically strong.
- No PIN lockout, rate limiting, or real session handling.
- Judge is a single LLM; a panel or calibrated rubric would be more reliable.
