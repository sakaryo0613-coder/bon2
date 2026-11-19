"""数値の設定。根拠は works/youtube-clipper/02-spec.md の「数値と根拠」を参照。"""

# クリップの長さ（秒、前後の余白込み）
CLIP_MIN = 20.0
CLIP_MAX = 60.0
CLIP_SWEET = (30.0, 50.0)

# 前後の余白（秒）。隣の文には食い込ませない
PAD_START = 0.3
PAD_END = 0.5

# 文の区切り
SENT_END_CHARS = "。！？!?"
SENT_GAP = 0.6          # これ以上の無音で文を区切る
SENT_MIN_DUR = 1.0      # これより短い文は前の文に結合

# 候補数 = 分数 ÷ 5（最小5・最大20）
CAND_PER_MIN = 1 / 5
CAND_MIN = 5
CAND_MAX = 20

# 出力
OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30
CRF = 20
LOUDNESS_I, LOUDNESS_TP, LOUDNESS_LRA = -14.0, -1.5, 11.0

# レイアウト（帯）
VIDEO_Y, VIDEO_H = 656, 608           # 16:9 動画の配置
SAFE_TOP, SAFE_BOTTOM = 240, 1520      # 文字はこの範囲内
SAFE_X = 60
BAND_Y, BAND_H = 228, 392              # タイトル帯（y=228〜620）
TITLE_SIZE, TITLE_LINE_CHARS, TITLE_LINES = 72, 13, 2
SUB_SIZE, SUB_LINE_CHARS, SUB_LINES, SUB_OUTLINE = 64, 15, 2, 6
SUB_Y = 1330
CREDIT_SIZE, CREDIT_Y = 32, 1276
BAND_COLOR = "E11D48"
BG_COLOR = "101010"

FONT_CANDIDATES = ["Hiragino Sans", "Yu Gothic UI", "Meiryo", "Noto Sans CJK JP", "IPAGothic"]

# LLM
LLM_MODEL = "claude-opus-5-5"
LLM_EFFORT = "high"
