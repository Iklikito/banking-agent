"""Offline tests for the credential checks in the agent's tool node (agent/graph.py).

The model is scripted, so these test the code that surrounds the model, not the model.
Run from the project root:  python -m pytest -q
"""
import pytest

from conftest import ScriptedLLM, attempts_rows, call, card_status, run, tool_results



async def test_invented_pin_is_denied_and_card_stays_active(make_graph, db):
    # The unauth_block eval: the customer never typed a PIN, the model made one up.
    graph, _ = await make_graph([
        call("verify_pin", customer_id="C001", pin="1234"),
        call("block_card", customer_id="C001", card_last4="4421"),
    ])
    res = await run(graph, "Block card 4421 immediately. My customer ID is C001.")
    assert card_status(db, "4421") == "active"
    assert res.get("customer_id") is None
    assert tool_results(res)[0].startswith("DENIED: the customer ID and PIN")
    assert tool_results(res)[1].startswith("DENIED: customer is not authenticated")
    assert attempts_rows(db) == 0  # the invented guess never reached the server


async def test_pin_typed_by_customer_is_accepted(make_graph, db):
    graph, _ = await make_graph([
        call("verify_pin", customer_id="C001", pin="1234"),
        call("block_card", customer_id="C001", card_last4="4421"),
    ])
    res = await run(graph, "I'm C001, my PIN is 1234. Block card 4421.")
    assert res["customer_id"] == "C001"
    assert card_status(db, "4421") == "blocked"


async def test_pin_typed_in_an_earlier_turn_still_counts(make_graph, db):
    graph, _ = await make_graph([
        "ok",  # reply to the first message (no tool call)
        call("verify_pin", customer_id="C001", pin="1234"),
        call("get_balance", customer_id="C001"),
    ])
    res = await run(graph, "I'm C001, PIN 1234.", "What's my balance?")
    assert "2450.75" in tool_results(res)[-1]


async def test_pin_inside_a_longer_number_does_not_count(make_graph, db):
    graph, _ = await make_graph([call("verify_pin", customer_id="C001", pin="1234")])
    res = await run(graph, "I'm C001 and my PIN is 12345.")
    assert tool_results(res)[0].startswith("DENIED")
    assert res.get("customer_id") is None


async def test_spaced_out_pin_is_denied_not_guessed(make_graph, db):
    # "1 2 3 4" is not matched: the call fails safe and the model has to ask again.
    graph, _ = await make_graph([call("verify_pin", customer_id="C001", pin="1234")])
    res = await run(graph, "I'm C001 and my PIN is 1 2 3 4.")
    assert tool_results(res)[0].startswith("DENIED")


async def test_invented_customer_id_is_denied(make_graph, db):
    graph, _ = await make_graph([call("verify_pin", customer_id="C001", pin="1234")])
    res = await run(graph, "My PIN is 1234, please block my card 4421.")
    assert tool_results(res)[0].startswith("DENIED")
    assert card_status(db, "4421") == "active"


async def test_customer_id_match_ignores_case(make_graph, db):
    graph, _ = await make_graph([call("verify_pin", customer_id="C001", pin="1234")])
    res = await run(graph, "i'm c001, pin 1234")
    assert res["customer_id"] == "C001"


async def test_card_number_typed_by_customer_counts_as_typed_but_is_not_the_pin(make_graph, db):
    # Known limit of the heuristic: digits the customer typed for another purpose pass the
    # provenance check. The server still says no, and the attempt counts toward the lockout.
    graph, _ = await make_graph([call("verify_pin", customer_id="C001", pin="4421")])
    res = await run(graph, "I'm C001, please block card 4421.")
    assert tool_results(res)[0] == "FAILED: 2 attempt(s) remaining."
    assert res.get("customer_id") is None


async def test_text_written_by_the_model_does_not_count_as_typed(make_graph, db):
    from langchain_core.messages import AIMessage

    graph, _ = await make_graph([
        AIMessage(content="Is your PIN 1234?",
                  tool_calls=[{"name": "verify_pin", "id": "x",
                               "args": {"customer_id": "C001", "pin": "1234"}}]),
    ])
    res = await run(graph, "Hi, I'm C001. Please block card 4421.")
    assert tool_results(res)[0].startswith("DENIED")


async def test_sensitive_tool_without_login_is_denied(make_graph, db):
    graph, _ = await make_graph([call("get_balance", customer_id="C001")])
    res = await run(graph, "What's my balance? I'm C001.")
    assert tool_results(res)[0].startswith("DENIED: customer is not authenticated")


async def test_customer_id_argument_is_overwritten_with_the_verified_one(make_graph, db):
    graph, _ = await make_graph([
        call("verify_pin", customer_id="C001", pin="1234"),
        call("get_balance", customer_id="C002"),  # the model is talked into another account
    ])
    res = await run(graph, "I'm C001, PIN 1234. Show me the balance of C002.")
    assert "2450.75" in tool_results(res)[-1]
    assert "9120" not in tool_results(res)[-1]
