"""Offline tests for the keyword handoff triage in agent/graph.py. The model is scripted."""
from langchain_core.messages import AIMessage

from agent.graph import HANDOFF_KEYWORDS, HANDOFF_REPLY, wants_human
from conftest import call, run
from evals.dialogues import DIALOGUES

KA_FRAUD = "ჩემი ბარათი მოიპარეს და ანგარიშიდან უცნობი გადახდა ჩანს. დამეხმარეთ სასწრაფოდ."


async def test_georgian_fraud_goes_to_a_human_without_calling_the_model(make_graph):
    graph, llm = await make_graph([])
    res = await run(graph, KA_FRAUD)
    assert llm.calls == 0
    assert res["handoff"] is True
    names = [c["name"] for m in res["messages"] if isinstance(m, AIMessage) for c in m.tool_calls]
    assert names == ["handoff_to_human"]
    assert res["messages"][-1].content == HANDOFF_REPLY["ka"]


async def test_english_complaint_gets_the_english_reply(make_graph):
    graph, llm = await make_graph([])
    res = await run(graph, "I want to file a complaint about a double charge.")
    assert llm.calls == 0 and res["handoff"] is True
    assert res["messages"][-1].content == HANDOFF_REPLY["en"]


async def test_ordinary_message_still_goes_to_the_model(make_graph):
    graph, llm = await make_graph([AIMessage("Hello!")])
    res = await run(graph, "Hi there")
    assert llm.calls == 1 and not res.get("handoff")


async def test_conversation_continues_normally_after_a_handoff(make_graph):
    graph, llm = await make_graph([AIMessage("Sure.")])
    res = await run(graph, "My card was stolen!", "Thanks. What are your opening hours?")
    assert llm.calls == 1  # only the second message reached the model
    assert res["messages"][-1].content == "Sure."


async def test_model_path_handoff_still_works_for_unlisted_phrasing(make_graph):
    graph, _ = await make_graph([call("handoff_to_human", reason="wants a person")])
    res = await run(graph, "ვიღაცამ ჩემი ბარათით ისარგებლა და ფული ამომაცალა.")
    assert res["handoff"] is True


def _turns(d):
    return d["turns"]


def test_handoff_dialogues_are_caught_except_the_paraphrase():
    for d in DIALOGUES:
        if d["category"] != "handoff":
            continue
        caught = all(wants_human(t) for t in _turns(d))
        assert caught == (d["id"] != "handoff_ka_paraphrase"), d["id"]


def test_no_other_dialogue_triggers_the_triage():
    # Guards against keywords so broad that normal or safety dialogues get handed off.
    for d in DIALOGUES:
        if d["category"] == "handoff":
            continue
        for t in _turns(d):
            assert not wants_human(t), (d["id"], t)


def test_keywords_are_lower_case():
    assert all(k == k.lower() for k in HANDOFF_KEYWORDS)
