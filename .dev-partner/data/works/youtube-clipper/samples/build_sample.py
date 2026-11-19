#!/usr/bin/env python3
"""合格基準用のサンプルを生成する（約6分のトーク配信を想定した字幕）。

出力:
  talk_sample.srt   … YouTube の自動字幕に近い形（[笑] を含む・1つの字幕に2文、1文が2つの字幕にまたがる、を混ぜる）
  expected.json     … 仕込んだ見どころ(H1〜H5)と、入ってはいけない区間(greeting/announce/ending)の時間範囲

使い方: python3 build_sample.py   （このファイルと同じフォルダに出力）
"""
import json
from pathlib import Path

CPS = 5.0          # 1秒あたりの文字数（間を含む雑談の速さ。漢字かな混じりで5〜6字/秒）
GAP_IN = 0.25      # 同じ話題の文と文の間（秒）
GAP_BLOCK = 0.9    # 話題の切り替わり（秒）

# (ラベル, 種類, 文のリスト)。種類: highlight / bad / filler
SCRIPT = [
    ("greeting", "bad", [
        "はい、こんばんは。", "始まりました、週末の雑談配信です。", "今日も来てくれてありがとうございます。",
        "コメントもどんどん書いてください。", "いつも通りゆるくやっていきます。", "よろしくお願いします。",
        "こんにちはって書いてくれてる人もいますね、ありがとうございます。",
    ]),
    ("filler1", "filler", [
        "で、今週はちょっと雨が多かったですよね。", "洗濯物がなかなか乾かなくて困りました。",
        "部屋干し用のハンガーを買い足そうか迷ってます。", "あと、週の半ばは仕事がばたばたしていて。",
        "配信の準備もぎりぎりになっちゃいました。", "それで今日は話す内容をメモしてきたので、順番に話していきます。",
        "最初は最近あったちょっとした出来事からです。",
    ]),
    ("H1", "highlight", [
        "先週、駅のホームで電車を待ってたんですよ。", "そしたら後ろから「先生！」って大きい声で呼ばれて。",
        "振り返ったら知らないおじさんが満面の笑みで手を振ってて。", "いや、私先生じゃないんですけど。[笑]",
        "でもあまりに嬉しそうだったから、つい手を振り返しちゃったんです。[笑]",
        "そしたらおじさん、隣の人に「ほら、あの先生だよ」って紹介し始めて。", "最後まで誰の先生なのか分かりませんでした。[笑]",
    ]),
    ("filler2", "filler", [
        "で、話は変わるんですけど。", "最近、通勤のときにポッドキャストを聞くようにしてます。",
        "歴史の話とか、ビジネスの話とか、いろいろ聞いてます。", "移動時間がちょっと楽しみになりました。",
        "おすすめがあればコメントで教えてください。", "次は、コメントでも多かった買い物の話をします。",
    ]),
    ("H2", "highlight", [
        "今年買ってよかったものランキング、ついに第1位の発表です。", "第1位は、電動の歯ブラシです。",
        "結論から言うと、これは本当に人生が変わりました。", "歯医者さんで毎回言われてた磨き残しが、ゼロになったんです。",
        "値段は一万円ちょっとなんですけど、正直もっと早く買えばよかったです。", "これはマジでおすすめです。",
    ]),
    ("filler3", "filler", [
        "で、ほかにもいくつか候補はあったんですけど。", "細かいものは概要欄にまとめておきます。",
        "キッチン用品とか、デスク周りのものとかですね。", "このあたりはまた別の回で詳しく話そうと思います。",
        "あ、そうだ、その前にお知らせがあります。",
    ]),
    ("announce", "bad", [
        "ここでちょっと告知です。", "チャンネル登録と高評価、まだの人はぜひお願いします。",
        "来週の土曜日にオンラインのイベントをやります。", "詳細は概要欄のリンクから見られます。",
        "メンバーシップの人には先行で案内を送っています。", "告知は以上です。",
    ]),
    ("H3", "highlight", [
        "コメントで質問をもらってます。", "朝起きるコツってありますか？",
        "これはね、ひとつだけ答えるなら、起きたらすぐカーテンを開けることです。",
        "光を浴びると体が勝手に目を覚ますんですよ。", "前は目覚ましを五個かけてたんですけど、今は一個で起きられます。",
        "だまされたと思って三日だけやってみてください。",
    ]),
    ("filler4", "filler", [
        "それで、朝の話のついでなんですけど。", "最近は朝ごはんもちゃんと食べるようにしてます。",
        "パンとヨーグルトくらいの簡単なものですけど。", "前は何も食べずに出かけてたので、少しは進歩しました。",
        "コーヒーも家で淹れるようになりました。", "ここからはその流れで、朝型の生活の話です。",
    ]),
    ("H4", "highlight", [
        "朝五時起きを一か月続けた結果を発表します。", "正直に言うと、最初の一週間は地獄でした。",
        "夜九時には眠くなるし、友達の誘いも断るしかなくて。", "でも結果的に、読んだ本が一か月で八冊になりました。",
        "去年一年で読んだのが五冊だったので、すごい変化です。", "時間って作れるんだなって、本当に思いました。",
    ]),
    ("filler5", "filler", [
        "で、本の話をし始めると長くなるので。", "読んだ本の感想はまた今度まとめて話します。",
        "ジャンルはけっこうばらばらでした。", "小説もあれば、料理の本もありました。",
        "最後に、今日いちばん話したかったことを話します。",
    ]),
    ("H5", "highlight", [
        "去年の自分に言いたいことがあるんです。", "去年の今ごろ、本当に何もうまくいってなくて。",
        "毎日、自分はだめだなって思ってました。", "でも、小さいことを続けてたら、ちゃんと変わりました。",
        "だから今つらい人がいたら、マジで、小さいことからでいいって伝えたいです。",
        "一年後のあなたは、きっと今の自分に感謝してます。",
    ]),
    ("ending", "bad", [
        "というわけで、今日はこのへんで終わりにします。", "おつかれさまでした。",
        "チャンネル登録よろしくお願いします。", "また来週の配信で会いましょう。", "おやすみなさい。",
    ]),
]


def fmt(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"


def build(outdir: Path) -> None:
    t = 2.0
    sentences = []   # (label, start, end, text)
    blocks = {}
    for label, kind, lines in SCRIPT:
        b0 = t
        for i, line in enumerate(lines):
            chars = len(line.replace("[笑]", ""))
            dur = max(1.4, chars / CPS) + (0.8 if "[笑]" in line else 0)
            sentences.append((label, t, t + dur, line))
            t += dur + GAP_IN
        blocks[label] = {"kind": kind, "start": round(b0, 2), "end": round(t - GAP_IN, 2)}
        t += GAP_BLOCK - GAP_IN

    # 自動字幕らしく崩す: 短い文は2つを1つの字幕にまとめる／長い文は句点なしで2つに分ける
    cues = []
    i = 0
    while i < len(sentences):
        label, s, e, text = sentences[i]
        nxt = sentences[i + 1] if i + 1 < len(sentences) else None
        if nxt and nxt[0] == label and len(text) + len(nxt[3]) <= 24:
            cues.append((s, nxt[2], text + nxt[3]))
            i += 2
            continue
        if len(text) >= 30 and "、" in text:
            k = text.index("、") + 1
            mid = s + (e - s) * k / len(text)
            cues.append((s, mid - 0.05, text[:k]))     # 句点なし・無音0.05秒 → 同じ文として結合されるべき
            cues.append((mid, e, text[k:]))
        else:
            cues.append((s, e, text))
        i += 1

    srt = "\n".join(f"{n}\n{fmt(s)} --> {fmt(e)}\n{text}\n" for n, (s, e, text) in enumerate(cues, 1))
    (outdir / "talk_sample.srt").write_text(srt, encoding="utf-8")
    exp = {
        "duration": round(t + 2.0, 2),
        "n_candidates": 5,
        "highlights": {k: v for k, v in blocks.items() if v["kind"] == "highlight"},
        "bad": {k: v for k, v in blocks.items() if v["kind"] == "bad"},
        "min_highlight_hits": 4,
        "hit_rule": "候補が見どころの時間の60%以上を含めばヒット",
        "bad_rule": "候補の時間の50%以上が bad 区間なら違反",
        "sentence_count": len(sentences),
    }
    (outdir / "expected.json").write_text(json.dumps(exp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"talk_sample.srt: {len(cues)} cues / {len(sentences)} sentences / {t:.0f}s")


if __name__ == "__main__":
    build(Path(__file__).resolve().parent)
