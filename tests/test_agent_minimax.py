"""单元测试：MiniMax agent helper（不走网络）。"""

from app.agent.minimax_client import extract_json_object


def test_extract_json_object_plain():
    d = extract_json_object('{"keep_ids":["a","b"]}')
    assert d["keep_ids"] == ["a", "b"]


def test_extract_json_object_markdown_block():
    txt = "```json\n{\"scored\":[{\"id\":\"a\",\"score\":0.8}]}\n```"
    d = extract_json_object(txt)
    assert d["scored"][0]["id"] == "a"

