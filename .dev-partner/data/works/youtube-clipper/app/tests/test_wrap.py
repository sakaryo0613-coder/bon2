"""日本語の改行位置（目視で直した例をすべて固定し、規則を足したときの後退を防ぐ）。"""
import pytest

from clipper.candidates import fit_title
from clipper.render import wrap

CASES = [
    ("いや、私先生じゃないんですけど", 13, [["いや、", "私先生じゃないんですけど"]]),
    ("朝五時起きを一か月続けた結果を発表します", 13, [["朝五時起きを一か月続けた", "結果を発表します"]]),
    ("結論から言うと、これは本当に人生が変わりました", 13, [["結論から言うと、これは", "本当に人生が変わりました"]]),
    ("スマホを別の部屋に置いたら1週間で人生変わった", 13, [["スマホを別の部屋に置いたら", "1週間で人生変わった"]]),
    ("「どうやって続けてる？」に本気で答える", 13, [["「どうやって続けてる？」に", "本気で答える"]]),
    ("今年買ってよかったものランキング", 13, [["今年買ってよかったもの", "ランキング"]]),
    ("振り返ったら知らないおじさんが満面の笑みで手を振ってて。", 15, [["振り返ったら知らないおじさんが", "満面の笑みで手を振ってて。"]]),
    ("一か月後の自分に感謝される", 13, [["一か月後の自分に感謝される"]]),
]


@pytest.mark.parametrize("text,width,want", CASES)
def test_wrap_examples(text, width, want):
    assert wrap(text, width, 2) == want


def test_wrap_never_breaks_rules():
    texts = ["だから今つらい人がいたら、マジで、小さいことからでいいって伝えたいです。",
             "値段は一万円ちょっとなんですけど、正直もっと早く買えばよかったです。",
             "そしたらおじさん、隣の人に「ほら、あの先生だよ」って紹介し始めて。"]
    for t in texts:
        pages = wrap(t, 15, 2)
        assert "".join("".join(p) for p in pages) == t           # 文字を失わない
        for p in pages:
            assert len(p) <= 2 and all(len(l) <= 16 for l in p)  # 禁則で1字はみ出すのは許容
            assert all(l[0] not in "、。」』）ーっゃゅょ" for l in p)


def test_fit_title_cuts_at_comma():
    assert fit_title("今年買ってよかったものランキング、ついに第1位の発表です。") == "今年買ってよかったものランキング"
    assert len(fit_title("あ" * 40)) == 26
