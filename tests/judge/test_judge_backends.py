import json

import httpx
import pytest

from Kodiac_robotics.judge import backends as B
from Kodiac_robotics.judge.client import (
    GLIMMER_SAMPLING,
    OpenAICompatClient,
    parse_answer,
)

ENV_VARS = (
    "Kodiac_JUDGE_BACKEND", "KODIAC_JUDGE_BACKEND", "Kodiac_JUDGE_BASE_URL", "Kodiac_JUDGE_MODEL",
    "Kodiac_JUDGE_KEY", "Kodiac_JUDGE_WONDER_BASE_URL", "MODEL_API_KEY", "KODIAC_MODEL_API_KEY",
    "BASETEN_API_KEY", "Kodiac_JUDGE_FIXTURE_DIR",
)
SECRET = "sk-test-SECRET-1234567890"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)


def _reply(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


def _mock(handler):
    return httpx.MockTransport(handler)


# ---- no-key path ----------------------------------------------------------

def test_no_key_returns_labelled_fixture_backend(caplog):
    with caplog.at_level("WARNING"):
        b = B.get_backend()
    assert isinstance(b, B.FixtureBackend) and b.is_fixture is True
    assert "FIXTURE" in b.model_id and b.fallback_reason
    assert any("FIXTURE" in r.message for r in caplog.records)


@pytest.mark.parametrize("name", ["meta", "baseten-spark-open", "modal-glimmer-vllm"])
def test_keyless_real_backends_fall_back_labelled(name):
    b = B.get_backend(name)
    assert b.is_fixture is True and name in (b.fallback_reason or "")


def test_no_key_answer_carries_fixture_marker():
    ans = B.get_backend().ask(b"anything", "Is the drawer flush?", B.SYSTEM_PROMPT)
    assert ans.reason.startswith("[FIXTURE]")


def test_explicit_fixture_backend():
    assert B.get_backend("fixture").is_fixture is True


def test_unknown_backend_name_rejected():
    with pytest.raises(ValueError):
        B.get_backend("gpt-whatever")


def test_env_selects_backend(monkeypatch):
    monkeypatch.setenv("Kodiac_JUDGE_BACKEND", "fixture")
    assert B.get_backend().name == "fixture"


# ---- keyed backends -------------------------------------------------------

def test_meta_backend_with_key(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", SECRET)
    b = B.get_backend()
    assert b.is_fixture is False and b.name == "meta" and b.model_id == "muse-spark-1.3"
    assert SECRET not in repr(b) and SECRET not in repr(b._client)


def test_baseten_backend(monkeypatch):
    monkeypatch.setenv("BASETEN_API_KEY", SECRET)
    b = B.get_backend("baseten-spark-open")
    assert b.is_fixture is False and b.name == "baseten-spark-open"


def test_modal_and_llamacpp_use_glimmer_sampling(monkeypatch):
    monkeypatch.setenv("Kodiac_JUDGE_BASE_URL", "http://modal.example/v1")
    for name in ("modal-glimmer-vllm", "llamacpp-glimmer"):
        b = B.get_backend(name)
        assert b.is_fixture is False
        assert b._client.sampling == GLIMMER_SAMPLING == {"temperature": 1.0, "top_p": 0.95, "top_k": 64}
        assert b._client.base_url == "http://modal.example/v1"


def test_llamacpp_needs_no_key():
    b = B.get_backend("llamacpp-glimmer")
    assert b.is_fixture is False and b._client.base_url.startswith("http://127.0.0.1")


# ---- escalator ------------------------------------------------------------

def test_escalator_for_fixture_primary_is_labelled_fixture_wonder():
    e = B.get_escalator(B.get_backend())
    assert e.is_fixture and "muse-wonder-1.0" in e.model_id


def test_escalator_with_key_is_real_wonder(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", SECRET)
    e = B.get_escalator(B.get_backend())
    assert e.is_fixture is False and e.model_id == "muse-wonder-1.0"


def test_no_escalator_when_open_weights_primary_and_no_meta_key(monkeypatch):
    monkeypatch.setenv("Kodiac_JUDGE_BASE_URL", "http://x/v1")
    assert B.get_escalator(B.get_backend("llamacpp-glimmer")) is None


# ---- HTTP request shape (mock transport: no network) ----------------------

def test_request_shape_and_auth_header():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return _reply('{"answer": "yes", "reason": "outlined drawer is level"}')

    c = OpenAICompatClient("https://api.example/v1/", "muse-spark-1.3", SECRET, transport=_mock(handler))
    ans = c.complete(b"\x89PNGfake", "Is the drawer flush?")
    assert ans.answer == "yes"
    assert seen["url"] == "https://api.example/v1/chat/completions"
    assert seen["auth"] == f"Bearer {SECRET}"
    body = seen["body"]
    assert body["model"] == "muse-spark-1.3" and body["temperature"] == 0.0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0] == {"role": "system", "content": "Answer only from the outlined region."}
    parts = body["messages"][1]["content"]
    assert parts[0]["type"] == "text" and "Is the drawer flush?" in parts[0]["text"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_glimmer_sampling_sent_in_body():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _reply('{"answer": "no", "reason": "r"}')

    c = OpenAICompatClient("http://h/v1", "glimmer", sampling=GLIMMER_SAMPLING, transport=_mock(handler))
    c.complete(b"x", "q")
    assert (seen["body"]["temperature"], seen["body"]["top_p"], seen["body"]["top_k"]) == (1.0, 0.95, 64)


def test_http_error_raises_without_leaking_key():
    c = OpenAICompatClient("http://h/v1", "m", SECRET, transport=_mock(lambda r: httpx.Response(401, json={})))
    with pytest.raises(httpx.HTTPStatusError) as ei:
        c.complete(b"x", "q")
    assert SECRET not in str(ei.value)


def test_http_backend_end_to_end_with_two_way_and_mock(monkeypatch, tmp_path):
    from Kodiac_robotics.contracts.core import Tri
    from Kodiac_robotics.judge.two_way import TwoWayJudge

    def handler(request):
        q = json.loads(request.content)["messages"][1]["content"][0]["text"]
        return _reply(json.dumps({"answer": "yes" if "flush" in q else "no", "reason": "mock transport"}))

    monkeypatch.setenv("MODEL_API_KEY", SECRET)
    b = B.get_backend(transport=_mock(handler))
    j = TwoWayJudge(b, cache=tmp_path)
    tri, reason = j.ask_two_way(b"crop", "Is the drawer flush?", "Is the drawer ajar?")
    assert tri is Tri.T and "[FIXTURE]" not in reason and SECRET not in reason


# ---- parsing --------------------------------------------------------------

@pytest.mark.parametrize(
    "text,answer",
    [
        ('{"answer": "yes", "reason": "r"}', "yes"),
        ('{"answer": "No.", "reason": "r"}', "no"),
        ('```json\n{"answer": "cant_tell", "reason": "r"}\n```', "cant_tell"),
        ('Sure! {"answer": "yes", "reason": "r"} done', "yes"),
        ("I think it is yes", "cant_tell"),
        ("", "cant_tell"),
        ('{"answer": "maybe"}', "cant_tell"),
        ('{"answer": "unknown", "reason": "blurry"}', "cant_tell"),
        ("[1, 2]", "cant_tell"),
    ],
)
def test_parse_answer_never_guesses(text, answer):
    assert parse_answer(text).answer == answer


def test_malformed_body_is_cant_tell():
    c = OpenAICompatClient("http://h/v1", "m", transport=_mock(lambda r: httpx.Response(200, json={"oops": 1})))
    assert c.complete(b"x", "q").answer == "cant_tell"


# ---- synthetic recorder ---------------------------------------------------

def test_synthetic_entries_are_labelled_and_deterministic():
    a = B.synthetic_entries(b"crop", "Qp?", "Qn?", "pos")
    assert a == B.synthetic_entries(b"crop", "Qp?", "Qn?", "pos")
    assert [e["answer"] for e in a] == ["yes", "no"]
    assert all(e["provenance"] == "synthetic" and "NOT model output" in e["reason"] for e in a)
    assert [e["answer"] for e in B.synthetic_entries(b"c", "p?", "n?", "neg")] == ["no", "yes"]
    assert [e["answer"] for e in B.synthetic_entries(b"c", "p?", "n?", "ambiguous")] == ["cant_tell"] * 2
    with pytest.raises(ValueError):
        B.synthetic_entries(b"c", "p?", "n?", "maybe")


def test_fixture_file_roundtrip(tmp_path):
    entries = B.synthetic_entries(b"crop", "Qp?", "Qn?", "pos")
    B.write_fixture_file(tmp_path / "f.json", entries)
    doc = json.loads((tmp_path / "f.json").read_text(encoding="utf-8"))
    assert doc["is_fixture"] is True and doc["schema"] == B.FIXTURE_SCHEMA
    fb = B.FixtureBackend(tmp_path)
    ans = fb.ask(b"crop", "Qp?", B.SYSTEM_PROMPT)
    assert ans.answer == "yes" and ans.reason.startswith("[FIXTURE]")


def test_committed_fixture_file_is_labelled_synthetic():
    path = B._default_fixture_dir() / "drawer_synthetic.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["is_fixture"] is True
    assert doc["entries"] and all(e["provenance"] == "synthetic" for e in doc["entries"])
