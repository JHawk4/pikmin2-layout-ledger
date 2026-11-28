"""The site's Japanese, keyed by the English as i18n.py templates it (see there).

Terms follow CaveGen3's Japanese page: 階 (sublevel), 洞窟 (cave), お宝, 原生生物, ポコ, 評価 (judge),
シード, ポッド, 借金返済 (Pay Off Debt), お宝全回収 (All Treasures), ご意見箱. Cave and treasure names
come from the game (names_ja.json); cave codes such as "SH 6" stay as they are, as runners write them.
A run is 記録, a runner 走者, the median 中央値, par パー.

Keys are exact: {0}, {1}, ... stand for the numbers, names, seeds and cave codes of the English in
order, and the Japanese may use them in any order. Tags have no attributes. When a page's English
changes, `python -m p2seeds i18n <site folder>` lists what is missing.
"""

from __future__ import annotations

T: dict[str, str] = {}
KEEP: list[str] = [          # left in English on purpose
    "Pikmin {0} Layout Ledger", "CaveGen3", "CaveGen", "Wii", "GameCube", "speedrun.com", "Dolphin", "Nintendont",
]


def put(en: str, ja: str) -> None:
    T[en] = ja


def many(pairs: dict[str, str]) -> None:
    T.update(pairs)


# ---- Header, footer, shared words ----
many({
    "All runs": "すべての記録",
    "Layouts": "レイアウト",
    "Detection": "シード検出",
    "Seed detection": "シード検出",
    "Time saved": "短縮タイム",
    "Pokos": "ポコ",
    "The judge": "評価のしくみ",
    "Judge accuracy": "評価の精度",
    "Seed check": "シード確認",
    "Gecko code": "Geckoコード",
    "Suggestion box": "ご意見箱",
    "Category": "部門",
    "Pay Off Debt": "借金返済",
    "Pay Off Debt (Wii)": "借金返済（Wii）",
    "All Treasures": "お宝全回収",
    "Wii U Virtual Console": "Wii U バーチャルコンソール",
    "Layouts, pictures, treasures and the judge from <a>CaveGen3</a>; runs from <a>speedrun.com</a>. "
    "Source: <a>github.com/{0}/pikmin2-layout-ledger</a>.":
        "レイアウト・画像・お宝・評価は<a>CaveGen3</a>、記録は<a>speedrun.com</a>から。"
        "ソース：<a>github.com/{0}/pikmin2-layout-ledger</a>",
    "Missing a run, or want one added? Share its video or speedrun.com link in the <a>suggestion box</a>.":
        "載っていない記録や追加してほしい記録があれば、動画か speedrun.com のリンクを<a>ご意見箱</a>で教えてください。",
    "Rank": "順位", "Runner": "走者", "Time": "タイム", "Date": "日付", "Pages": "ページ", "Video": "動画",
    "Run": "記録", "Runs": "記録数", "Total": "合計", "Show": "表示", "Sublevel": "階", "Sublevels": "階",
    "Judge": "評価", "Layout": "レイアウト", "layout": "レイアウト", "layouts": "レイアウト", "runner": "走者",
    "median": "中央値", "details": "詳細", "Table": "表", "Took": "所要", "Beats": "勝率", "Plays": "プレイ数",
    "Correlation": "相関", "Highlight": "強調", "How": "方法", "Note": "備考", "Letters": "文字数",
    "former WR": "元WR", "not on speedrun.com": "speedrun.com 未登録", "video": "動画", "detection": "検出", "{0} of {1}": "{0} / {1}", "{0} to {1}": "{0} 〜 {1}",
    "{0} pk": "{0}ポコ", "{0} s": "{0}秒", "{0} pokos": "{0}ポコ", "{0} poko": "{0}ポコ",
    "<a>detection</a> · <a>speedrun.com</a>": "<a>検出</a> · <a>speedrun.com</a>",
    "Seeds read": "読めたシード", "Layout luck": "レイアウト運", "Luck percentile": "運のパーセンタイル",
    "Runner beyond layouts": "走者（レイアウト以外）",
})

# Page titles: "Pikmin 2 Layout Ledger · ..." (the name stays; each part is looked up on its own)
many({
    "does the judge predict real times?": "評価は実際のタイムを予測できる？",
    "seed detection by run": "記録ごとのシード検出",
    "how the judge works": "評価のしくみ",
    "layouts by run": "記録ごとのレイアウト",
    "pokos by sublevel": "階ごとのポコ",
    "seed order check": "シードの順序の確認",
    "time saved by sublevel": "階ごとの短縮タイム",
    "seed detection": "シード検出",
})
for name, ja in (("Pay Off Debt", "借金返済"), ("All Treasures", "お宝全回収"), ("Pay Off Debt (Wii)", "借金返済（Wii）")):
    put(f"layout luck in Pikmin {{0}} {name} runs", f"ピクミン{{0}} {ja}の記録のレイアウト運")
    put(f"Every cave sublevel's layout is set by the game's random number generator. This site reads that seed from the "
        f"falling title letters in each {name} run's video, rebuilds the exact layout, and asks how lucky the layouts were "
        f"and how much time the runner saved beyond what the layouts gave.",
        f"洞窟の各階のレイアウトは、ゲームの乱数で決まります。このサイトは{ja}の記録動画で落ちてくる階層名の文字から"
        f"そのシードを読み取ってレイアウトを正確に再現し、レイアウトがどれだけ幸運だったか、走者がレイアウトの分を除いて"
        f"どれだけタイムを縮めたかを調べます。")

# ---- Landing page ----
_RUNNER_ALLOW = "after allowing for the layouts (so a bad layout is not counted against the runner)"
_RUNNER_ALLOW_JA = "レイアウトの分を差し引いた（悪いレイアウトが走者の不利にならないように）"
many({
    "How lucky were the layouts?": "レイアウトの運は？",
    f"<b>Runner beyond the layouts</b>: seconds the runner saved against the median run on the same sublevels, {_RUNNER_ALLOW}.":
        f"<b>走者（レイアウト以外）</b>：同じ階の中央値の記録に対して走者が縮めた秒数。{_RUNNER_ALLOW_JA}値です。",
    f"<b>Runner beyond the layouts</b>: seconds the runner saved against the median run on the same sublevels, {_RUNNER_ALLOW}, "
    "with pokos counted: {0} pokos = {1} second.":
        f"<b>走者（レイアウト以外）</b>：同じ階の中央値の記録に対して走者が縮めた秒数。{_RUNNER_ALLOW_JA}、"
        "ポコを含めた値です（{0}ポコ＝{1}秒）。",
    "<b>Layout luck</b>: seconds the run's layouts should save against the median layout of the same sublevels, by "
    "CaveGen's layout judge re-tuned on these runs' real times. <b>Luck percentile</b>: how many random runs it beats.":
        "<b>レイアウト運</b>：同じ階の中央値のレイアウトに比べて、その記録のレイアウトで短縮できるはずの秒数。"
        "これらの記録の実際のタイムで調整し直したCaveGenのレイアウト評価によります。<b>運のパーセンタイル</b>：ランダムな記録の何%に勝つか。",
    "<b>Layout luck</b>: seconds the run's layouts should save against the median layout of the same sublevels, by "
    "CaveGen's All Treasures judge with walking, carrying, enemy and gate times weighted as the re-tuned Pay Off Debt judge, "
    "which matches these runs' real times (a missing treasure or missing purple flowers cost extra). <b>Luck percentile</b>: "
    "how many random runs it beats.":
        "<b>レイアウト運</b>：同じ階の中央値のレイアウトに比べて、その記録のレイアウトで短縮できるはずの秒数。"
        "CaveGenのお宝全回収の評価に、調整し直した借金返済の評価と同じ歩き・運搬・原生生物・ゲートの重みをかけたもので、"
        "これらの記録の実際のタイムに合っています（お宝や紫のポンガシグサが欠けると追加のコスト）。"
        "<b>運のパーセンタイル</b>：ランダムな記録の何%に勝つか。",
    "Negative is faster, as on splits. <b>Seeds read</b> is how many sublevels' seeds were read with confidence; only those "
    "count. Click a column to sort; open a runner for their layouts.":
        "マイナスはスプリットと同じく速いことを表します。<b>読めたシード</b>はシードを確実に読めた階の数で、"
        "それらだけを数えます。列をクリックで並べ替え、走者を開くとそのレイアウトが見られます。",
    "Seconds the layouts should save vs median layouts": "中央値のレイアウトに比べてレイアウトで短縮できるはずの秒数",
    "Share of random runs over the same sublevels this run's layouts beat": "同じ階でのランダムな記録のうち、この記録のレイアウトが上回った割合",
    "Seconds saved vs the median run beyond what the layouts gave": "レイアウトの分を除いた、中央値の記録に対する短縮秒数",
    "Seconds saved vs the median run beyond what the layouts gave, pokos counted ({0} = {1} s)":
        "レイアウトの分を除いた、中央値の記録に対する短縮秒数（ポコを含む：{0}＝{1}秒）",
    "Sublevels whose seed was read with confidence": "シードを確実に読めた階",
    "The runs' luck": "各記録の運",
    "Each dot is a run's layout luck; the grey curve is how luck falls for random runs, so a dot far left of the curve's "
    "middle was a lucky run. Hover a dot for the run; click it for its layouts.":
        "点はそれぞれの記録のレイアウト運、灰色の曲線はランダムな記録での運の分布です。曲線の中央より左にある点ほど幸運な記録です。"
        "点にカーソルを合わせると記録が、クリックするとそのレイアウトが表示されます。",
    "How lucky was each run? Every run against {0} random runs": "各記録の運は？ ランダムな{0}回の記録との比較",
    "total seconds the layouts should save against median layouts (negative = luckier)":
        "中央値のレイアウトに比べてレイアウトで短縮できるはずの合計秒数（マイナス＝幸運）",
    "grey: random runs, one random layout of each of the {0} sublevels with layout luck":
        "灰色：ランダムな記録（運のある{0}階それぞれでランダムなレイアウトを1つ）",
    "dots: the runs on this site (hollow = some sublevels not read, or another route)":
        "点：このサイトの記録（白抜き＝読めなかった階がある、または別ルート）",
    "luckier than {0}% of random runs": "ランダムな記録の{0}%より幸運",
    "layouts {0} s over {1} sublevels": "レイアウト {0}秒（{1}階）",
    "(hollow: not the usual {0} sublevels, so its percentile compares it with random runs over its own {1})":
        "（白抜き：通常の{0}階ではないため、自身の{1}階でのランダムな記録と比べたパーセンタイル）",
    "5th pct": "5%点", "95th pct": "95%点",
    "Not here: their videos could not be downloaded (deleted, private, or not available).":
        "未掲載：動画をダウンロードできなかった記録（削除・非公開・利用不可）。",
    "<bdi></bdi> (rank {0})": "<bdi></bdi>（{0}位）",
    "<bdi></bdi> (former WR)": "<bdi></bdi>（元WR）",
})

# ---- Pickers (layouts, detection) and the layout spread ----
many({
    "Pick a run to see every layout it got: how lucky each one was against {0} random layouts of the same sublevel, what "
    "the runner did with it, and the pictures.":
        "記録を選ぶと、その記録のすべてのレイアウトが見られます：同じ階のランダムな{0}個のレイアウトと比べた運、走者の結果、そして画像。",
    "Pick a run to see how each sublevel's seed was read from the falling title letters, how sure the reading is, and the "
    "pictures behind it.":
        "記録を選ぶと、各階のシードを落ちてくる階層名の文字からどう読み取ったか、その確かさ、もとになった画像が見られます。",
    "Runner beyond layouts": "走者（レイアウト以外）",
    "Do these runs get typical layouts?": "これらの記録のレイアウトは典型的？",
    "No: they are personal bests, and a run with good layouts is more likely to become one. For each sublevel, how the "
    "layouts of the runs on this site compare with random layouts, in seconds against the median random layout by the "
    "judge (negative = faster). Over these sublevels the median run's layouts add up to <b>{0} s</b> against median "
    "layouts. That is why the runner numbers on this site take the layout out instead of comparing with the median run alone.":
        "いいえ。これらは自己ベストで、良いレイアウトに当たった走りほど自己ベストになりやすいからです。各階について、"
        "このサイトの記録のレイアウトをランダムなレイアウトと比べています（評価による、ランダムなレイアウトの中央値との差、秒、"
        "マイナス＝速い）。これらの階を合計すると、中央値の記録のレイアウトは中央値のレイアウトより<b>{0}秒</b>になります。"
        "そのため、このサイトの走者の数値は、中央値の記録と比べるだけでなくレイアウトの分を差し引いています。",
    "{0} {1}: random layouts above, these runs' layouts below": "{0} {1}：上はランダムなレイアウト、下はこれらの記録のレイアウト",
    "{0} {1}: random layouts above the line (median dashed), these runs' layouts below (median run dark, each run a dot)":
        "{0} {1}：線の上はランダムなレイアウト（破線は中央値）、下はこれらの記録のレイアウト（濃い線が中央値の記録、点が各記録）",
    "Random layouts<br><span>middle half</span>": "ランダムなレイアウト<br><span>中央の半分</span>",
    "These runs<br><span>middle half</span>": "これらの記録<br><span>中央の半分</span>",
    "Median run<br><span>vs median layout</span>": "中央値の記録<br><span>中央値のレイアウト比</span>",
    "Median run<br><span>beats</span>": "中央値の記録<br><span>勝率</span>",
    "25th to 75th percentile of {0} random layouts": "ランダムな{0}個のレイアウトの25〜75パーセンタイル",
    "25th to 75th percentile of the runs' layouts": "記録のレイアウトの25〜75パーセンタイル",
    "The median run's layout against the median random layout": "中央値の記録のレイアウトと、ランダムなレイアウトの中央値の比較",
    "Share of random layouts the median run's layout beats": "中央値の記録のレイアウトが勝つランダムなレイアウトの割合",
    "random ▲ · these runs ▼, seconds": "ランダム ▲ · これらの記録 ▼（秒）",
    "random ▲": "ランダム ▲", "these runs ▼, seconds": "これらの記録 ▼（秒）",
    "Layouts: above the line, how {0} random layouts spread (grey, dashed at their median); below it, the layouts of the "
    "runs here (blue, a dot per run, the dark tick at the median run's). Every row uses the same seconds scale (the labels "
    "at the top), so a wide shape is a sublevel where the layout matters a lot; each row's height is scaled to fit. The two "
    "shapes in a row have the same area, so a blue shape further left than the grey one means these runs got better layouts "
    "than chance. Fixed floors and sublevels with fewer than {1} confidently read layouts are left out.":
        "レイアウト：線の上はランダムな{0}個のレイアウトの分布（灰色、破線は中央値）、線の下はここの記録のレイアウト"
        "（青、点が各記録、濃い目盛りが中央値の記録）です。どの行も同じ秒数の目盛り（上のラベル）なので、幅の広い形はレイアウトの"
        "影響が大きい階です。行の高さは収まるように調整しています。1行の2つの形は面積が同じなので、青い形が灰色より左にあれば、"
        "これらの記録は偶然より良いレイアウトに当たっています。固定の階と、確実に読めたレイアウトが{1}個未満の階は除いています。",
})

# ---- Time saved ----
_PAR = "against a median runner on a median layout"
many({
    "Time saved by sublevel": "階ごとの短縮タイム",
    "Seconds each run gained or lost on each sublevel. Negative (green) is faster. Hover a cell for the details; click it "
    "to open the video there.":
        "各記録が各階で縮めた・失った秒数です。マイナス（緑）が速い。セルにカーソルを合わせると詳細、クリックでその場面の動画が開きます。",
    "Seconds each run gained or lost on each sublevel, with pokos counted ({0} pokos = {1} second, so a sublevel done {2} s "
    "slower for {3} more pokos is even). Negative (green) is faster. Hover a cell for the details; click it to open the "
    "video there.":
        "各記録が各階で縮めた・失った秒数です（ポコを含む：{0}ポコ＝{1}秒なので、{3}ポコ多く取って{2}秒遅い階は差し引きゼロ）。"
        "マイナス（緑）が速い。セルにカーソルを合わせると詳細、クリックでその場面の動画が開きます。",
    "<input> <b>The runner beyond the layout</b>: the judge's difference between this layout and the median run's is taken "
    "out, so it shows execution, not luck":
        "<input> <b>レイアウト以外の走者の力</b>：評価によるこのレイアウトと中央値の記録のレイアウトの差を除くので、運ではなく実行力が分かります",
    f"<input> <b>Against par</b>: {_PAR}, so a lucky layout counts in the runner's favour":
        "<input> <b>パー比</b>：中央値の走者が中央値のレイアウトで走った場合との比較。幸運なレイアウトは走者に有利に数えます",
    "<input> <b>Against the median run</b>: the plain difference from the median run here, whose layout was usually better "
    "than the median layout (these are personal bests)":
        "<input> <b>中央値の記録比</b>：ここの中央値の記録との単純な差。その記録のレイアウトはたいてい中央値のレイアウトより"
        "良いものでした（これらは自己ベストです）",
    "Runs are sorted by their total, fastest first. Only the usual route's sublevels are shown; – = not timed (an uncertain "
    "seed, or the last sublevel's results screen was not found).":
        "記録は合計の速い順です。通常のルートの階だけを表示しています。–＝計測なし（シードが不確か、または洞窟の最後の階の"
        "リザルト画面が見つからない）。",
    "not timed": "計測なし",
    "took {0} s (median run {1} s)": "所要 {0}秒（中央値の記録 {1}秒）",
    "{0} pokos (median run {1})": "{0}ポコ（中央値の記録 {1}）",
    "vs the median run: {0} s": "中央値の記録比：{0}秒",
    "vs the median run: {0} s, pokos counted": "中央値の記録比：{0}秒（ポコを含む）",
    "pokos counted": "ポコを含む",
    "layout vs the median run's: {0} s by the judge": "レイアウト（中央値の記録比）：評価で{0}秒",
    "beyond the layout: {0} s": "レイアウト以外：{0}秒",
    "vs par (median runner, median layout): {0} s": "パー比（中央値の走者・中央値のレイアウト）：{0}秒",
})

# ---- Pokos ----
many({
    "Pokos by sublevel": "階ごとのポコ",
    "Pokos per sublevel against the median run (the median is under each sublevel's name). Green = more, red = fewer, – = "
    "not read, ? = an unusually large difference worth checking. Hover a cell for the treasures; click it to open the video.":
        "中央値の記録に対する階ごとのポコです（中央値は各階の名前の下）。緑＝多い、赤＝少ない、–＝読めず、?＝確認したほうがよい"
        "大きな差。セルにカーソルを合わせるとお宝が、クリックすると動画が開きます。",
    "How the pokos are counted": "ポコの数え方",
    "Total vs median": "合計（中央値比）",
    "not read": "読めず",
    "no treasure": "お宝なし",
    "{0} pokos (the median)": "{0}ポコ（中央値）",
    "{0} pokos vs the median ({1} vs {2})": "中央値比 {0}ポコ（{1} 対 {2}）",
    "unusually large: check the video": "差が大きすぎます：動画を確認してください",
    "Unusually large: a skipped or extra treasure, or a misread; check the video.":
        "差が大きすぎます：お宝を取らなかった・余分に取った、または読み間違いです。動画を確認してください。",
})
_POKO_HOW = ("Each treasure collected shows a panel with its value; the panels are counted in the video and matched to the "
             "treasures CaveGen places on that layout. Each panel also shows the run's running Total, so pokos from "
             "creatures are whatever the Total rose by beyond the treasure; they are shared among the cave sublevels "
             "between the two panels by time spent in each (never the surface, and treasures picked up on the surface "
             "count toward no sublevel).")
_POKO_HOW_JA = ("お宝を回収するたびに価値のパネルが出るので、動画でパネルを数え、そのレイアウトでCaveGenが置くお宝と照合します。"
                "パネルには記録の累計（Total）も出るため、原生生物からのポコはお宝以外で累計が増えた分です。それを2つのパネルの間に"
                "ある洞窟の階に、それぞれの滞在時間で割り振ります（地上には割り振らず、地上で拾ったお宝はどの階にも数えません）。")
_POKO_HEAD = "Each row is a run, each column a sublevel where at least one run differs from the median."
_POKO_HEAD_JA = "各行が記録、各列が少なくとも1つの記録が中央値と異なる階です。"
put(f"{_POKO_HEAD} {_POKO_HOW}", _POKO_HEAD_JA + _POKO_HOW_JA)
put(f"{_POKO_HEAD} {{0}} other sublevels, where every run got the median, are left out. {_POKO_HOW}",
    _POKO_HEAD_JA + "すべての記録が中央値だった残りの{0}階は省いています。" + _POKO_HOW_JA)
put(f"{_POKO_HEAD} {{0}} other sublevel, where every run got the median, is left out. {_POKO_HOW}",
    _POKO_HEAD_JA + "すべての記録が中央値だった残りの{0}階は省いています。" + _POKO_HOW_JA)


# Treasure lists in tooltips: "Name (120), Other or Another (90)"; names are placeholders.
def _items(i: int, n: int, or_at: int | None) -> tuple[str, str, int]:
    en, ja = [], []
    for k in range(n):
        if k == or_at:
            en.append(f"{{{i}}} or {{{i + 1}}} ({{{i + 2}}})")
            ja.append(f"{{{i}}}または{{{i + 1}}}（{{{i + 2}}}）")
            i += 3
        else:
            en.append(f"{{{i}}} ({{{i + 1}}})")
            ja.append(f"{{{i}}}（{{{i + 1}}}）")
            i += 2
    return ", ".join(en), "、".join(ja), i


for n in range(1, 8):
    for or_at in (None, *range(n)):
        e, j, i = _items(1, n, or_at)
        put(f"{{0}} pokos: {e}", f"{{0}}ポコ：{j}")
        put(f"{{0}} pokos: {e} + about {{{i}}} from creatures (estimated)", f"{{0}}ポコ：{j} ＋原生生物から約{{{i}}}（推定）")
        e2, j2, _ = _items(2, n, or_at)
        put(f"{{0}} pokos ({{1}} vs median): {e2}", f"{{0}}ポコ（中央値比 {{1}}）：{j2}")
        if or_at is not None:
            e0, j0, _ = _items(0, n, or_at)
            put(e0, j0)
many({
    "{0} pokos (no treasure)": "{0}ポコ（お宝なし）",
    "{0} pokos (no treasure) + about {1} from creatures (estimated)": "{0}ポコ（お宝なし） ＋原生生物から約{1}（推定）",
    "{0} pokos ({1} vs median)": "{0}ポコ（中央値比 {1}）",
})

# ---- Seed order ----
many({
    "Seed order": "シードの順序",
    "A check on the seed reading: each seed's position in the game's random number sequence, counted from the run's first "
    "seed. The RNG only moves forward, so every line should climb steadily; a point off its line marks a doubtful seed.":
        "シードの読み取りの確認です。各シードの、記録の最初のシードから数えたゲームの乱数列での位置を示します。乱数は前にしか"
        "進まないので、どの線も着実に上がっていくはずです。線から外れた点は疑わしいシードです。",
    "Show the chart and the table": "グラフと表を表示",
    "RNG position of each detected seed": "検出した各シードの乱数での位置",
    "minutes into the video": "動画の経過時間（分）",
    "million RNG steps after the run's first seed": "記録の最初のシードからの乱数ステップ数（百万）",
    "Video time": "動画の時刻", "Letter seed": "文字シード", "Layout seed": "レイアウトシード", "RNG steps": "乱数ステップ数",
    "{0} M steps": "{0}百万ステップ",
    "at {0} in the video": "動画の{0}",
    "<i></i>{0} runs, one line each; hover a line or point to see which":
        "<i></i>{0}記録（1記録につき1本）。線や点にカーソルを合わせると記録が分かります",
})

# ---- Judge accuracy ----
_SORTS = [  # (title, how) as site.SORTS writes them
    ("Sorted by predicted time saved", "low to high", "予測短縮タイム順", "小さい順"),
    ("Sorted by size of the prediction", "small to large swings", "予測の大きさ順", "振れ幅の小さい順"),
    ("Sorted by how variable the sublevel is", "5th–95th spread, low to high", "階のばらつき順", "5〜95パーセンタイルの幅の小さい順"),
    ("Sorted by sublevel length", "median judge time, short to long", "階の長さ順", "評価タイムの中央値の短い順"),
    ("Sorted by creature pokos on offer", "most pokos the layout's creatures can give, low to high", "原生生物のポコ順",
     "レイアウトの原生生物から得られる最大ポコの少ない順"),
    ("Sorted by game order", "cave and sublevel", "ゲーム順", "洞窟と階の順"),
    ("Sorted by runner", "one runner after another", "走者順", "走者ごと"),
]
for title, how, tja, hja in _SORTS:
    put(title, tja)
    put(how, hja)
    put(f"{title}: no significant bend (p = {{0}})", f"{tja}：有意な曲がりなし（p = {{0}}）")
    put(f"{title}: possible bend (p = {{0}})", f"{tja}：曲がりの可能性あり（p = {{0}}）")
    put(f"{title}: <b>significant bend</b> (p = {{0}})", f"{tja}：<b>有意な曲がりあり</b>（p = {{0}}）")
    for k in range(3, 7):          # ", largest around SH 6 (JackDraz 1:30:25)": cave code, sublevel, runner, time
        args = " ".join(f"{{{i}}}" for i in range(3, k + 1))
        put(f"{title}: possible bend (p = {{0}}), largest around {{1}} {{2}} ({args})",
            f"{tja}：曲がりの可能性あり（p = {{0}}）、最も大きいのは{{1}} {{2}}（{args}）付近")
        put(f"{title}: <b>significant bend</b> (p = {{0}}), largest around {{1}} {{2}} ({args})",
            f"{tja}：<b>有意な曲がりあり</b>（p = {{0}}）、最も大きいのは{{1}} {{2}}（{args}）付近")
    put(f"The judge may be off by a different amount in places: {title.lower()}.",
        f"場所によって評価のずれ方が違うかもしれません：{tja}。")
many({
    "max deviation {0}, p = {1}": "最大偏差 {0}、p = {1}",
    "Does the judge predict real times?": "評価は実際のタイムを予測できる？",
    "Each sublevel's real time is measured from the video: from its entry screen to the next sublevel's entry screen (a "
    "cave's last sublevel runs to the cave's results screen). Both the judge's estimate and the real time are compared "
    "within the same sublevel across runs, after removing each runner's overall pace. For Pay Off Debt the outcome counts "
    "pokos too, at two pokos per second; for other categories, plays where the runner collected a different number of "
    "treasures than most runs of that sublevel are left out. Only seeds read at high confidence are used: a misread seed "
    "is a wrong layout, so its judge score would be noise. Hover a point for its seed and pokos; click it to open the video "
    "there.":
        "各階の実際のタイムは動画から測ります。階層名の画面から次の階の階層名の画面まで（洞窟の最後の階は洞窟のリザルト画面まで）"
        "です。評価の見積もりと実際のタイムは、各走者の全体のペースを除いたうえで、同じ階の記録どうしで比べます。借金返済では"
        "ポコも結果に含め（2ポコ＝1秒）、ほかの部門では、その階の多くの記録と違う数のお宝を集めたプレイを除きます。使うのは"
        "確度の高いシードだけです。読み違えたシードは別のレイアウトなので、その評価はノイズになるからです。点にカーソルを"
        "合わせるとシードとポコ、クリックでその場面の動画が開きます。",
    "Predicted vs actual, one dot per sublevel play": "予測と実際（点は1回の階のプレイ）",
    "judge: seconds vs the other runs' layouts (negative = faster layout)": "評価：ほかの記録のレイアウトとの差（秒、マイナス＝速いレイアウト）",
    "run: net seconds vs other runs (time − pokos ÷ {0}; negative = faster)":
        "記録：ほかの記録との実質タイム差（タイム − ポコ ÷ {0}、マイナス＝速い）",
    "run: seconds vs other runs (negative = faster)": "記録：ほかの記録との差（秒、マイナス＝速い）",
    "judge: bad layout": "評価：悪いレイアウト", "judge: good layout": "評価：良いレイアウト",
    "run: slower": "記録：遅い", "run: faster": "記録：速い",
    "The numbers": "数値",
    "Slope ({0}%)": "傾き（{0}%）",
    "R² (slope {0})": "R²（傾き{0}）",
    "Run vs others": "ほかの記録との差",
    "<input> Colour by runner": "<input> 走者で色分け",
    "<i></i>others": "<i></i>その他",
    "<i></i>unusual play (far off the prediction)": "<i></i>外れたプレイ（予測から大きく外れる）",
    "<i></i>y = x (perfect calibration)": "<i></i>y = x（完全に較正された状態）",
    "<i></i>one sublevel in one run": "<i></i>1つの記録の1つの階",
    "<i></i>fitted slope": "<i></i>あてはめた傾き",
    "fit: slope {0}": "あてはめ：傾き {0}",
    "{0} ({1} plays)": "{0}（{1}プレイ）",
    "without the {0} unusual plays": "外れたプレイ{0}件を除く",
    "{0} unusual plays (ringed in the charts)": "外れたプレイ {0}件（グラフでは丸で囲んでいます）",
    "{0} unusual play (ringed in the charts)": "外れたプレイ {0}件（グラフでは丸で囲んでいます）",
    "More than {0} robust standard deviations off what the judge predicts: no layout judge explains them. Many are real "
    "choices (a skipped treasure); some are mistakes (a death, a misplay). They are kept in the fit; the table above also "
    "gives it without them.":
        "評価の予測からロバスト標準偏差で{0}以上外れたプレイです。どんなレイアウト評価でも説明できません。多くは実際の判断"
        "（お宝を取らないなど）で、ミス（死亡、操作ミス）もあります。あてはめには含めたままで、上の表には除いた場合も載せています。",
    "layout seed {0}": "レイアウトシード {0}",
    "judge: layout {0} s vs the median layout": "評価：中央値のレイアウト比 {0}秒",
    "judge: no median": "評価：中央値なし",
    "runner: took {0} s vs the median run here": "走者：この階の中央値の記録比 {0}秒",
    "runner: took {0} s vs the median run here, net {1} s": "走者：この階の中央値の記録比 {0}秒、実質 {1}秒",
    "run {0} s net": "記録 実質{0}秒",
    "run {0} s": "記録 {0}秒",
    "judge {0} s (after runner pace)": "評価 {0}秒（走者のペースを除いた後）",
    "predicted {0} s, actual {1} s": "予測 {0}秒、実際 {1}秒",
    "Is the judge equally right everywhere?": "評価はどこでも同じように正しい？",
    "No sign that the judge is better or worse for any cave, runner or layout size.":
        "洞窟・走者・レイアウトの大きさによって評価の正しさが変わる兆候はありません。",
    "Show the checks": "検定を表示",
    "Each chart walks through the same plays in a different order, adding up prediction² along the bottom and prediction × "
    "actual up the side, so the slope of the walk so far is the regression slope over those plays. If the judge is off by "
    "the same proportion everywhere, the walk follows the dashed line and stays inside the grey {0}% band. A bend that "
    "leaves the band shows where the slope differs: for example, a steeper end in \"size\" would mean big predicted swings "
    "are more reliable than small ones. The test allows each play its own noise level. Under each chart are the sort's "
    "values; drag across a chart to see the slope of just that stretch.":
        "各グラフは同じプレイを別の順に並べ、横に予測²、縦に予測×実際を足していきます。そのため、ここまでの道のりの傾きが、"
        "それらのプレイでの回帰の傾きになります。評価のずれがどこでも同じ割合なら、道のりは破線に沿い、灰色の{0}%の帯の中に"
        "収まります。帯から出る曲がりは、傾きが違う場所を示します。たとえば「大きさ」順で終わりのほうが急なら、大きく振れる予測ほど"
        "信頼できるということです。検定では、プレイごとに異なるノイズの大きさを考慮しています。各グラフの下は並べ替えの値で、"
        "グラフをドラッグするとその区間だけの傾きが分かります。",
    "cumulative prediction² (s²)": "予測²の累積（秒²）",
    "drag to measure a stretch": "ドラッグで区間を測定",
    "cumulative prediction × actual (s²)": "予測×実際の累積（秒²）",
    "The outcome is time with pokos counted: seconds minus pokos ÷ {0}. On plain time the judge would have slope {1} "
    "(correlation {2}).":
        "結果はポコを含めたタイム（秒 − ポコ ÷ {0}）です。単純なタイムでは、評価の傾きは{1}（相関{2}）になります。",
    "Over <b>{0}</b> sublevel plays ({1} sublevels seen in at least two runs), each second the judge predicts should be "
    "worth one second of net time.":
        "<b>{0}</b>回の階のプレイ（2つ以上の記録にある{1}階）で、評価が予測する1秒は実質タイムの1秒に相当するはずです。",
    "Over <b>{0}</b> sublevel plays ({1} sublevels seen in at least two runs), each second the judge predicts should be "
    "worth one second of real time.":
        "<b>{0}</b>回の階のプレイ（2つ以上の記録にある{1}階）で、評価が予測する1秒は実際のタイムの1秒に相当するはずです。",
    "Not enough runs share sublevels to check calibration.": "較正を確かめられるほど同じ階を走った記録がありません。",
    "Plays left out: a different number of treasures than most runs of that sublevel": "除いたプレイ：その階の多くの記録とお宝の数が違う",
    "Usual": "通常", "Treasures": "お宝",
})
for who, wja in (("The judge", "評価"), ("CaveGen's judge", "CaveGenの評価")):
    put(f"{who} is right on average: a layout it calls {{0}} s faster really is about {{1}} s faster. It explains about "
        f"{{2}}% of the differences between runs on the same sublevel; the rest is the runners.",
        f"{wja}は平均すると正確です。{{0}}秒速いとされたレイアウトは、実際にも約{{1}}秒速くなっています。同じ階での記録どうしの"
        f"差の約{{2}}%を説明し、残りは走者によるものです。")
    for verb, vja in (("overstates", "大きく"), ("understates", "小さく")):
        put(f"{who} {verb} the differences between layouts by about {{0}}% (a layout it calls {{1}} s faster is about {{2}} s faster).",
            f"{wja}はレイアウトの差を約{{0}}%{vja}見積もっています（{{1}}秒速いとされたレイアウトは実際には約{{2}}秒速い）。")
put("{0} plays left out: a different number of treasures than most runs of that sublevel",
    "除いたプレイ {0}件：その階の多くの記録とお宝の数が違う")
_SLOPE = ("The slope is what a predicted second is actually worth ({0} = calibrated, below {1} = the judge overstates "
          "differences between layouts); R² is the share of the runs' differences the judge explains taking its seconds at "
          "face value.")
_SLOPE_JA = ("傾きは、予測の1秒が実際にどれだけに当たるかです（{0}＝較正済み、{1}未満＝評価がレイアウトの差を大きく見積もっている）。"
             "R²は、評価の秒数をそのまま受け取ったときに、記録どうしの差のうち評価が説明できる割合です。")
_JUDGE_NOTES = [
    ("The judge is CaveGen's Pay Off Debt judge refit on these runs: no credit for pokos from enemies or for treasures runners "
     "don't collect, a choice of which treasures to skip, and re-weighted walking, carrying, enemy and gate times. CaveGen's "
     "original judge had slope {2} here (it overstated layout differences by about a fifth) and R² {3}.",
     "評価は、CaveGenの借金返済の評価をこれらの記録で合わせ直したものです：原生生物のポコや走者が取らないお宝は加点せず、"
     "取らないお宝を選べるようにし、歩き・運搬・原生生物・ゲートの時間の重みを付け直しています。CaveGen本来の評価は、ここでは"
     "傾き{2}（レイアウトの差を約5分の1大きく見積もる）、R² {3}でした。"),
    ("The judge is CaveGen's Pay Off Debt judge, with the parts and weights refit on the GameCube Pay Off Debt runs (see that "
     "section's judge page), and its scale refit here on these Wii runs. Wii and Wii U loads are shorter, and on the Wii U many "
     "sublevel titles are cut short or skipped, so fewer sublevels have a seed than on GameCube.",
     "評価はCaveGenの借金返済の評価で、要素と重みはゲームキューブの借金返済の記録で合わせ直し（そちらの評価のしくみのページを参照）、"
     "スケールはここのWiiの記録で合わせ直しています。WiiとWii Uは読み込みが短く、Wii Uでは多くの階で階層名が途中で切れたり"
     "表示されなかったりするため、シードのある階はゲームキューブより少なくなります。"),
    ("The judge is CaveGen's All Treasures judge (with the Japanese treasure weights for Japanese runs), its walking, carrying, "
     "enemy and gate times weighted as the Pay Off Debt judge's, which were fitted on that category's runs and never on these. "
     "CaveGen's own weights had slope {2} here (they overstated layout differences by about a fifth) and R² {3}.",
     "評価はCaveGenのお宝全回収の評価（日本の記録には日本版のお宝の重さ）で、歩き・運搬・原生生物・ゲートの時間には借金返済の評価の"
     "重みを使っています。その重みは借金返済の記録で合わせたもので、これらの記録では合わせていません。CaveGen本来の重みは、ここでは"
     "傾き{2}（レイアウトの差を約5分の1大きく見積もる）、R² {3}でした。"),
]
for note, nja in _JUDGE_NOTES:
    put(f"{_SLOPE} {note}", _SLOPE_JA + nja)

# Dragging across a cumulative chart (charts.BRUSH_JS): "SH 6 to BK 2: 12 plays, slope 0.85 (all 0.90)"
_ENDS = ["{}", "{} s", "{} pk", "{} {}"]
for fmt in _ENDS:
    k = fmt.count("{}")
    a = fmt.format(*[f"{{{i}}}" for i in range(k)])
    b = fmt.format(*[f"{{{i}}}" for i in range(k, 2 * k)])
    n = 2 * k
    for slope in ("{%d}" % (n + 1), "–"):
        rest_en = f"{{{n}}} plays, slope {slope} (all {{{n + 2 if slope != '–' else n + 1}}})"
        rest_ja = f"{{{n}}}プレイ、傾き {slope}（全体 {{{n + 2 if slope != '–' else n + 1}}}）"
        put(f"{a} to {b}: {rest_en}", f"{a} 〜 {b}：{rest_ja}".replace(" s", "秒").replace(" pk", "ポコ"))
for slope in ("{1}", "–"):
    last = "{2}" if slope == "{1}" else "{1}"
    put(f"{{0}} plays, slope {slope} (all {last})", f"{{0}}プレイ、傾き {slope}（全体 {last}）")

# ---- How the judge works ----
many({
    "How the judge works": "評価のしくみ",
    "The judge looks at a sublevel's layout (where the ship, the treasures, the enemies and the hole are) and estimates how "
    "many seconds a good runner needs to clear it in Pay Off Debt. It never watches the run: it only sees the layout, so it "
    "can say how kind the layout was, apart from how well it was played.":
        "評価は階のレイアウト（ポッド、お宝、原生生物、穴の位置）を見て、上手な走者が借金返済でその階をクリアするのに何秒かかるかを"
        "見積もります。走りそのものは見ずレイアウトだけを見るので、プレイの出来とは別に、レイアウトがどれだけ有利だったかが分かります。",
    "The judge looks at a sublevel's layout (where the ship, the treasures, the enemies and the hole are) and estimates how "
    "many seconds a good runner needs to collect every treasure on it and leave. It never watches the run: it only sees the "
    "layout, so it can say how kind the layout was, apart from how well it was played.":
        "評価は階のレイアウト（ポッド、お宝、原生生物、穴の位置）を見て、上手な走者がその階のお宝をすべて集めて出るまでに何秒"
        "かかるかを見積もります。走りそのものは見ずレイアウトだけを見るので、プレイの出来とは別に、レイアウトがどれだけ有利だったかが分かります。",
    "What goes into the estimate": "見積もりの中身",
    "<b>Estimate</b>: the time to walk the route, plus the time Pikmin spend carrying each treasure back to the ship, plus "
    "extra time for enemies near a carry path and for gates in the way, plus a fixed cost per treasure.":
        "<b>見積もり</b>：ルートを歩く時間、ピクミンが各お宝をポッドまで運ぶ時間、運搬ルート近くの原生生物や途中のゲートによる"
        "追加の時間、お宝ごとの固定の時間の合計です。",
    "<b>Layout luck</b>: the same estimate for {0} random layouts of the sublevel. This layout against the median one is its "
    "luck (negative = faster), and the share of random layouts it beats is its percentile.":
        "<b>レイアウト運</b>：同じ見積もりを、その階のランダムな{0}個のレイアウトでも計算します。中央値のレイアウトとの差がこの"
        "レイアウトの運（マイナス＝速い）、ランダムなレイアウトの何%に勝つかがパーセンタイルです。",
    "<b>Runner</b>: the real time from the video minus what the judge says the layout was worth. What is left is the "
    "runner's own doing.":
        "<b>走者</b>：動画から測った実際のタイムから、評価によるレイアウトの価値を引いたもの。残りが走者自身の力です。",
    "<b>Runner</b>: the real time from the video, with pokos counted ({0} pokos = {1} s), minus what the judge says the "
    "layout was worth. What is left is the runner's own doing.":
        "<b>走者</b>：動画から測った実際のタイム（ポコを含む：{0}ポコ＝{1}秒）から、評価によるレイアウトの価値を引いたもの。"
        "残りが走者自身の力です。",
    "<b>Walking</b>: the shortest tour from the ship over the treasures, then on to the hole.":
        "<b>歩き</b>：ポッドからお宝を回って穴へ向かう最短ルート。",
    "<b>Carrying</b>: for each treasure, the time to gather carriers, dig it up if it is buried, and carry it home at a "
    "speed set by its weight and how many Pikmin fit on it.":
        "<b>運搬</b>：各お宝について、運ぶピクミンを集め、埋まっていれば掘り出し、重さと持てるピクミンの数で決まる速さでポッドまで運ぶ時間。",
    "<b>Hazards</b>: enemies within reach of a carry path, by how dangerous they are.":
        "<b>危険</b>：運搬ルートの近くにいる原生生物（危険度に応じて）。",
    "<b>Gates</b>: gates on a carry path or on the way to the hole, by their health.":
        "<b>ゲート</b>：運搬ルートや穴への道にあるゲート（体力に応じて）。",
    "<b>{0} seconds per treasure</b> taken, for picking it up and the collection cutscene.":
        "取ったお宝1つにつき<b>{0}秒</b>（拾う時間と回収ムービーの分）。",
    "<b>Pokos</b>: if the treasures it expects you to take are worth fewer pokos than usual, the shortfall counts against "
    "the layout at {0} pokos per second, the same rate the runner numbers use.":
        "<b>ポコ</b>：取ると予測するお宝のポコがいつもより少ないと、その不足分を1秒あたり{0}ポコでレイアウトの不利として数えます。"
        "走者の数値と同じ換算です。",
    "Each part has its own weight, fitted to real times (below): walking ×{0}, carrying ×{1}, hazards ×{2}, gates ×{3}.":
        "各要素には実際のタイムに合わせた重みがあります（下記）：歩き×{0}、運搬×{1}、危険×{2}、ゲート×{3}。",
    "<b>Missing treasures and purple flowers</b>: a quirk of the spawning sometimes leaves a treasure out of the layout, or "
    "fewer purple flowers than usual where runners pick purples. The judge adds {0} s when a treasure is missing (as "
    "CaveGen's All Treasures judge does) and {1} s per missing purple flower (CaveGen: {2} s; see below).":
        "<b>欠けたお宝と紫のポンガシグサ</b>：出現の仕様で、お宝がレイアウトから欠けたり、走者が紫ピクミンを増やす場所で紫の"
        "ポンガシグサがいつもより少なかったりすることがあります。お宝が欠けると{0}秒（CaveGenのお宝全回収の評価と同じ）、"
        "欠けた紫のポンガシグサ1つにつき{1}秒（CaveGenでは{2}秒、下記参照）を加えます。",
    "Which treasures it expects the runner to take": "走者が取ると予測するお宝",
    "Runners skip a treasure when it costs more time than its pokos are worth. The judge tries every take/skip choice "
    "(every combination of up to four treasures) and scores each. It doesn't simply pick the fastest; it averages the "
    "choices, leaning heavily on the fast ones, because runners don't always make the best call. When one choice is clearly "
    "best (about {0}% of the weight) the run pages name the treasure it expects to be skipped.":
        "走者は、ポコの価値より時間がかかるお宝は取りません。評価は取る・取らないのすべての選択（最大4つのお宝の組み合わせ）を"
        "試して採点します。いちばん速いものを選ぶのではなく、速い選択に大きく重みをかけて平均します。走者がいつも最善の判断を"
        "するとは限らないからです。1つの選択が明らかに最善（重みの約{0}%）のときは、記録のページに取らないと予測したお宝を表示します。",
    "<b>Optional treasures are assumed left behind.</b> Six treasures that runners almost never collect get no time and no "
    "pokos in the estimate: the chess pieces on {0} {1}, the locket, the gum tape on {2} {3}, the leaf on {4} {5} and the "
    "queen on {6} {7}. On {8} {9}, {10} of {11} runs here took a chess piece. When a runner does take one, its pokos still "
    "count in the runner's number ({12} pokos = {13} s), so the detour is judged on whether it paid for itself. About {14} "
    "low-value treasures are ignored altogether.":
        "<b>取らなくてもよいお宝は置いていくものとします。</b>走者がほとんど取らない6つのお宝は、見積もりで時間もポコも0です："
        "{0} {1}のチェスの駒、ロケット、{2} {3}のガムテープ、{4} {5}の葉っぱ、{6} {7}のクイーン。{8} {9}では、ここの{11}記録中"
        "{10}記録がチェスの駒を取りました。取った場合もそのポコは走者の数値に入る（{12}ポコ＝{13}秒）ので、寄り道が割に合ったかで"
        "評価されます。価値の低いお宝約{14}個は完全に無視します。",
    "Special cases": "特別な場合",
    "<b>{0} {1}</b>: if the Dwarf Bulborb carrying the lens would have to cross water, the lens counts as so costly that the "
    "judge expects runners to skip it, which they do.":
        "<b>{0} {1}</b>：レンズを持ったコチャッピーが水を渡る必要があるときは、レンズのコストがとても大きいとみなし、走者は取らないと"
        "予測します（実際に取りません）。",
    "<b>{0}</b>: CaveGen's own adjustments for {1} are kept, with a fitted weight (×{2}).":
        "<b>{0}</b>：{1}に対するCaveGen独自の調整はそのまま使い、重みを合わせています（×{2}）。",
    "<b>Fixed floors</b> (the same layout for every seed, such as boss floors) have no luck: they are shown but never counted.":
        "<b>固定の階</b>（ボスの階など、どのシードでも同じレイアウトの階）には運がありません。表示はしますが、集計には含めません。",
    "How it was made and checked": "作り方と検証",
    "It starts from CaveGen's Pay Off Debt judge, rebuilt in CaveGen3. The original treated every treasure as taken, gave "
    "credit for optional treasures and for creature pokos, and overstated layout differences by about a fifth. This version "
    "(\"judge2\") changes those rules and refits the weights on the real sublevel times in these runs.":
        "出発点は、CaveGenの借金返済の評価をCaveGen3で作り直したものです。元の評価はすべてのお宝を取るものとし、取らなくてもよい"
        "お宝や原生生物のポコも加点していたため、レイアウトの差を約5分の1大きく見積もっていました。この版（「judge2」）はそれらの"
        "ルールを変え、これらの記録の実際の階のタイムで重みを合わせ直しています。",
    "It is CaveGen's All Treasures judge, rebuilt in CaveGen3, with the Japanese release's treasure weights for Japanese runs. "
    "Its parts are weighted as the Pay Off Debt judge's, which were fitted on that category's real times: walking ×{0}, "
    "carrying ×{1}, hazards ×{2}, gates ×{3}. On the All Treasures runs here those weights come out right (a predicted second "
    "is worth about one real second), while CaveGen's own weights overstate layout differences by about a fifth. A fit on "
    "these runs alone could not do better: with a handful of runs, every reasonable set of weights explains about as much.":
        "CaveGenのお宝全回収の評価をCaveGen3で作り直したもので、日本の記録には日本版のお宝の重さを使います。各要素の重みは、"
        "借金返済の実際のタイムで合わせた借金返済の評価と同じです：歩き×{0}、運搬×{1}、危険×{2}、ゲート×{3}。ここのお宝全回収の"
        "記録では、この重みで正しく合います（予測の1秒は実際の約1秒）が、CaveGen本来の重みではレイアウトの差を約5分の1大きく見積もります。"
        "これらの記録だけで合わせ直しても良くはなりません。記録が少ないため、妥当な重みならどれも同じくらいしか説明できないからです。",
    "To avoid tuning it to the runs it is then judged on, the weights were fitted on some runners' runs and tested on the "
    "others. On the held-out runners, it explained about {0}% of the differences in time between layouts, against {1}% for "
    "the original.":
        "評価する記録に合わせすぎないよう、一部の走者の記録で重みを合わせ、残りの走者で検証しました。検証用の走者では、レイアウトによる"
        "タイム差の約{0}%を説明できました（元の評価は{1}%）。",
    "The comparison works within each sublevel and each runner, so it asks only: when the same runner meets a different "
    "layout of the same sublevel, does the time move as the judge says?":
        "比較は階ごと・走者ごとに行うので、問うのは「同じ走者が同じ階の別のレイアウトに当たったとき、タイムは評価のとおりに変わるか」だけです。",
    "Across {0} sublevel plays on this site, one second the judge predicts is worth {1} real seconds ({2} would be perfect), "
    "and its estimates correlate {3} with the real times. See <a>Judge accuracy</a> for the checks.":
        "このサイトの{0}回の階のプレイでは、評価が予測する1秒は実際の{1}秒に相当し（{2}なら完璧）、見積もりと実際のタイムの"
        "相関は{3}です。検証は<a>評価の精度</a>をご覧ください。",
    "The missing-treasure cost could not be checked yet: none of these runs met a missing treasure. Missing purple flowers "
    "are common on a few sublevels (about a third of random {0} {1} and {2} {3} layouts, two thirds of {4} {5}), but the "
    "only two plays here that met them, both on {6} {7}, lost about {8} s (± {9} s), not a minute; with {10} s the judge "
    "overstated layout differences by {11}%. So a missing purple counts {12} s until more runs show where purples matter more.":
        "お宝が欠ける場合のコストはまだ検証できていません。これらの記録には、お宝が欠けたレイアウトがありませんでした。紫の"
        "ポンガシグサが欠けることは一部の階でよくあります（ランダムな{0} {1}と{2} {3}のレイアウトの約3分の1、{4} {5}の約3分の2）"
        "が、ここでそれに当たったのは{6} {7}の2回だけで、失ったのは1分ではなく約{8}秒（±{9}秒）でした。{10}秒にすると、評価は"
        "レイアウトの差を{11}%大きく見積もりました。そこで、紫が重要な場所がもっと分かるまでは、欠けた紫1つを{12}秒としています。",
    "What it can't see": "評価に見えないもの",
    "Execution: deaths, misplays, lucky enemy behaviour, how well a runner manages Pikmin.":
        "実行面：死亡、操作ミス、原生生物の動きの運、ピクミンの扱いのうまさ。",
    "Route habits beyond the take/skip choice, and tricks the base judge doesn't model.":
        "取る・取らないの選択以外のルートの癖や、基本の評価が扱わないテクニック。",
    "Route habits and tricks the base judge doesn't model.": "基本の評価が扱わないルートの癖やテクニック。",
    "It is an estimate. Single sublevels can be off by several seconds; totals over a run are much steadier.":
        "あくまで見積もりです。1つの階では数秒ずれることもありますが、記録全体の合計ははるかに安定しています。",
})

# ---- A run's layouts page (run_page.py) ----
for cat, cja in (("Pay Off Debt", "借金返済"), ("All Treasures", "お宝全回収"), ("Pay Off Debt (Wii)", "借金返済（Wii）")):
    put(f"{cat}, {{0}}-{{1}}-{{2}} · <a>speedrun.com</a> · <a>how the seeds were read</a>",
        f"{cja}、{{0}}-{{1}}-{{2}} · <a>speedrun.com</a> · <a>シードの読み取り方</a>")
    put(f"{cat}, {{0}}-{{1}}-{{2}} · <a>how the seeds were read</a>", f"{cja}、{{0}}-{{1}}-{{2}} · <a>シードの読み取り方</a>")
    put(f"{cat} · <a>speedrun.com</a> · <a>how the seeds were read</a>", f"{cja} · <a>speedrun.com</a> · <a>シードの読み取り方</a>")
    put(f"{cat} · <a>how the seeds were read</a>", f"{cja} · <a>シードの読み取り方</a>")
_RUN_INTROS = [
    ("Every layout was rebuilt from the seed read off the video and timed by the layout judge (CaveGen's Pay Off Debt judge, "
     "refit on these runs' real times). <b>Layout luck</b> is the judge's time against the median of {0} random layouts of "
     "the same sublevel. <b>Runner</b> is what the runner did against the median run on this site, counting {1} pokos as {2} "
     "second, with the judge's difference between this layout and the median run's taken out, so a bad layout is not counted "
     "against the runner. <b>Par</b> is a median runner on a median layout: the diamonds below show the runner against par, "
     "luck included. Negative is faster, as on splits.",
     "どのレイアウトも、動画から読み取ったシードで再現し、レイアウト評価（これらの記録の実際のタイムで合わせ直したCaveGenの借金返済の評価）"
     "で計時しています。<b>レイアウト運</b>は、同じ階のランダムな{0}個のレイアウトの中央値に対する評価タイムの差です。<b>走者</b>は、"
     "このサイトの中央値の記録に対する走者の結果（{1}ポコ＝{2}秒で換算）から、このレイアウトと中央値の記録のレイアウトの評価の差を"
     "除いたもので、悪いレイアウトは走者の不利になりません。<b>パー</b>は中央値の走者が中央値のレイアウトで走った場合で、下のひし形は"
     "運を含めたパーに対する走者を示します。マイナスはスプリットと同じく速いことを表します。", 3),
    ("Every layout was rebuilt from the seed read off the video and timed by the layout judge (CaveGen's All Treasures judge, "
     "with its walking, carrying, enemy and gate times weighted as the Pay Off Debt judge refit on real times, which matches "
     "All Treasures runs too). <b>Layout luck</b> is the judge's time against the median of {0} random layouts of the same "
     "sublevel. <b>Runner</b> is what the runner did against the median run on this site, with the judge's difference between "
     "this layout and the median run's taken out, so a bad layout is not counted against the runner. <b>Par</b> is a median "
     "runner on a median layout: the diamonds below show the runner against par, luck included. Negative is faster, as on splits.",
     "どのレイアウトも、動画から読み取ったシードで再現し、レイアウト評価（CaveGenのお宝全回収の評価に、実際のタイムで合わせ直した"
     "借金返済の評価と同じ歩き・運搬・原生生物・ゲートの重みをかけたもので、お宝全回収の記録にも合います）で計時しています。"
     "<b>レイアウト運</b>は、同じ階のランダムな{0}個のレイアウトの中央値に対する評価タイムの差です。<b>走者</b>は、このサイトの"
     "中央値の記録に対する走者の結果から、このレイアウトと中央値の記録のレイアウトの評価の差を除いたもので、悪いレイアウトは走者の"
     "不利になりません。<b>パー</b>は中央値の走者が中央値のレイアウトで走った場合で、下のひし形は運を含めたパーに対する走者を示します。"
     "マイナスはスプリットと同じく速いことを表します。", 1),
]
for en, ja, n in _RUN_INTROS:
    put(en, ja)
    put(en + f" {{{n}}} sublevels whose seed is uncertain are shown faded and never counted.",
        ja + f"シードが不確かな{{{n}}}階は薄く表示し、集計には含めません。")
    put(en + f" {{{n}}} sublevel whose seed is uncertain is shown faded and never counted.",
        ja + f"シードが不確かな{{{n}}}階は薄く表示し、集計には含めません。")
many({
    "Every sublevel": "全階",
    "Every sublevel: seconds against the median (negative = faster)": "全階：中央値との差（秒、マイナス＝速い）",
    "Through the run": "記録の流れ",
    "Through the run: running totals, seconds (negative = ahead)": "記録の流れ：累計（秒、マイナス＝先行）",
    "Blue: the time the layouts handed the runner so far, against median layouts. Orange: the time the runner gained on the "
    "median run so far beyond what the layouts gave. Hover for the numbers; click to jump to the card.":
        "青：ここまでにレイアウトが走者にもたらした時間（中央値のレイアウト比）。オレンジ：ここまでに走者がレイアウトの分を除いて"
        "中央値の記録より縮めた時間。カーソルを合わせると数値、クリックでその階のカードへ移動します。",
    "Luck and the runner through the run": "記録全体での運と走者",
    "The judge against the runner": "評価と走者",
    "The judge against the runner, one dot per sublevel": "評価と走者（点は1つの階）",
    "Across: how much faster or slower the judge rates this layout than the median run's layout. Up: how much faster or "
    "slower the runner actually was than the median run. On the orange line the layout explains the whole difference; dots "
    "below it beat what the layout predicts, dots above it lost time beyond the layout.":
        "横：評価によるこのレイアウトと中央値の記録のレイアウトの差。縦：走者が実際に中央値の記録より速かった・遅かった秒数。"
        "オレンジの線上ならレイアウトだけで差が説明できます。線より下の点はレイアウトの予測より速く、上の点はレイアウト以外で時間を失っています。",
    "judge: this layout vs the median run's layout, seconds": "評価：このレイアウトと中央値の記録のレイアウトの差（秒）",
    "runner vs the median run, seconds": "走者と中央値の記録の差（秒）",
    "runner vs the median run, seconds, pokos counted": "走者と中央値の記録の差（秒、ポコを含む）",
    "better layout, faster": "良いレイアウト、速い", "worse layout, slower": "悪いレイアウト、遅い",
    "better layout,": "良いレイアウト、", "worse layout,": "悪いレイアウト、",
    "still faster": "それでも速い", "still slower": "それでも遅い",
    "Across: layout {0} s vs the median run's layout": "横：中央値の記録のレイアウト比 {0}秒",
    "Up: runner {0} s vs the median run": "縦：走者 中央値の記録比 {0}秒",
    "Up: runner {0} s vs the median run, pokos counted": "縦：走者 中央値の記録比 {0}秒（ポコを含む）",
    "Each sublevel: random layouts, this layout and the runner": "各階：ランダムなレイアウト、このレイアウト、走者",
    "<i></i>{0} random layouts (1st–99th percentile; wider = more common)":
        "<i></i>ランダムな{0}個のレイアウト（1〜99パーセンタイル、幅が広いほど多い）",
    "<i></i>this layout (green faster, red slower)": "<i></i>このレイアウト（緑は速い、赤は遅い）",
    "<i></i>the runner against par: a median runner on a median layout, pokos counted. The gap from tick to diamond is the "
    "runner’s own part":
        "<i></i>パーに対する走者：中央値の走者が中央値のレイアウトで走った場合との差（ポコを含む）。目盛りからひし形までが走者自身の分です",
    "<i></i>the runner against par: a median runner on a median layout. The gap from tick to diamond is the runner’s own part":
        "<i></i>パーに対する走者：中央値の走者が中央値のレイアウトで走った場合との差。目盛りからひし形までが走者自身の分です",
    "Seconds vs the median run beyond what the layout gave": "レイアウトの分を除いた中央値の記録との差（秒）",
    "Seconds vs the median run beyond what the layout gave, pokos counted ({0} = {1} s)":
        "レイアウトの分を除いた中央値の記録との差（秒、ポコを含む：{0}＝{1}秒）",
    "Judge: estimated clear time, with the difference from the median random layout. Beats: share of random layouts this one "
    "beats. Click a heading to sort, a sublevel to see its card.":
        "評価：見積もりクリアタイムと、ランダムなレイアウトの中央値との差。勝率：このレイアウトが勝つランダムなレイアウトの割合。"
        "見出しをクリックで並べ替え、階をクリックでそのカードを表示します。",
    "The judge's estimated clear time (vs the median layout)": "評価による見積もりクリアタイム（中央値のレイアウト比）",
    "Share of {0} random layouts this one beats": "ランダムな{0}個のレイアウトのうち、このレイアウトが勝つ割合",
    "Vs par": "パー比",
    "{0} s vs par": "パー比 {0}秒",
    "Pokos <span>(vs median)</span>": "ポコ <span>（中央値比）</span>",
    "Highlights <span>most time saved beyond the layout</span>": "ベスト <span>レイアウト以外で最も時間を縮めた階</span>",
    "Lowlights <span>most time lost beyond the layout</span>": "ワースト <span>レイアウト以外で最も時間を失った階</span>",
    "Luckiest layouts": "最も幸運なレイアウト",
    "Unluckiest layouts": "最も不運なレイアウト",
    "{0} <span>layouts <span>{1} s</span> · runner <span>{2} s</span></span>":
        "{0} <span>レイアウト <span>{1}秒</span> · 走者 <span>{2}秒</span></span>",
    "{0} <span>layouts <span>{1} s</span></span>": "{0} <span>レイアウト <span>{1}秒</span></span>",
    "{0} {1} layout": "{0} {1} のレイアウト",
    "after {0} {1}": "{0} {1} の後",
    "sublevels in the order played": "プレイした順の階",
    "layout luck: what {0} layouts should save against median layouts of the same sublevels":
        "レイアウト運：{0}個のレイアウトが、同じ階の中央値のレイアウトに比べて短縮できるはずの時間",
    "luck percentile: luckier than {0}% of random runs over the same sublevels":
        "運のパーセンタイル：同じ階でのランダムな記録の{0}%より幸運",
    "runner: time saved against the median run over {0} sublevels, beyond what the layouts gave":
        "走者：{0}階で中央値の記録より縮めた時間（レイアウトの分を除く）",
    "runner: time saved against the median run over {0} sublevels, beyond what the layouts gave, pokos counted":
        "走者：{0}階で中央値の記録より縮めた時間（レイアウトの分を除く、ポコを含む）",
    "layout luck so far {0} s ({1} s here)": "ここまでのレイアウト運 {0}秒（この階 {1}秒）",
    "layout luck so far {0} s (– here)": "ここまでのレイアウト運 {0}秒（この階 –）",
    "runner so far {0} s ({1} s here)": "ここまでの走者 {0}秒（この階 {1}秒）",
    "runner so far {0} s (– here)": "ここまでの走者 {0}秒（この階 –）",
    "layout luck {0} s": "レイアウト運 {0}秒",
    "runner {0} s": "走者 {0}秒",
    "runner {0} s beyond the layout": "走者 レイアウト以外で{0}秒",
    "Runner {0} s beyond the layout": "走者 レイアウト以外で{0}秒",
    "runner {0} s vs par (a median runner on a median layout)": "走者 パー比 {0}秒（中央値の走者が中央値のレイアウトで走った場合）",
    "layout {0} s vs the median layout (faster than {1}% of layouts)": "レイアウト 中央値のレイアウト比 {0}秒（レイアウトの{1}%より速い）",
    "layout {0} s vs the median layout (about the best of {1} random layouts)":
        "レイアウト 中央値のレイアウト比 {0}秒（ランダムな{1}個のレイアウトでほぼ最良）",
    "layout {0} s vs the median layout (about the worst of {1} random layouts)":
        "レイアウト 中央値のレイアウト比 {0}秒（ランダムな{1}個のレイアウトでほぼ最悪）",
    "Layout {0} s": "レイアウト {0}秒",
    "beats {0}% of layouts": "レイアウトの{0}%に勝つ",
    "beats {0}%": "{0}%に勝つ",
    "Judge {0} s (median {1})": "評価 {0}秒（中央値 {1}）",
    "{0} s (median {1})": "{0}秒（中央値 {1}）",
    "{0} s (median run {1})": "{0}秒（中央値の記録 {1}）",
    "{0} (median run {1})": "{0}（中央値の記録 {1}）",
    "Took {0} s (median run {1})": "所要 {0}秒（中央値の記録 {1}）",
    "Pokos {0} (median run {1})": "ポコ {0}（中央値の記録 {1}）",
    "{0} s vs the median run's": "中央値の記録比 {0}秒",
    "Where this layout falls among {0} random layouts": "ランダムな{0}個のレイアウトの中での位置",
    "Seed {0}": "シード {0}", "seed {0}": "シード {0}", "video {0}": "動画 {0}",
    "Seed {0} · <a>how it was read</a>": "シード {0} · <a>読み取り方</a>",
    "how it was read": "読み取り方",
    "fixed floor": "固定の階",
    "uncertain seed": "不確かなシード",
    "no judge": "評価なし",
    "farm visit": "紫集め",
    "<small>layout</small>–": "<small>レイアウト</small>–",
    "<small>runner</small>–": "<small>走者</small>–",
    "layout · vs par": "運 · パー比",          # a narrow column heading in the chart
    "vs par": "パー比",
    "Judge expects a skip: {0}": "評価の予測：{0}は取らない",
    "The judge expects a skip: {0}": "評価は{0}を取らないと予測しています",
    "A purple-farm visit (the cave is entered again later): not counted.": "紫ピクミン集めのための訪問（後でこの洞窟に入り直す）：集計に含めません。",
    "Layout lacks": "レイアウトに欠けているもの",
    "Missing from this layout: {0} purple flower.": "このレイアウトで欠けているもの：紫のポンガシグサ{0}つ。",
    "Missing from this layout: {0} purple flowers.": "このレイアウトで欠けているもの：紫のポンガシグサ{0}つ。",
    "{0} purple missing": "紫{0}つ欠け",
    "{0} treasure missing": "お宝{0}つ欠け",
})

# ---- A run's detection page (details.py; these pages are not rebuilt, so older wordings stay too) ----
many({
    "How to read a detection": "検出結果の読み方",
    "Each sublevel's entry screen drops the cave name's letters with starting speeds drawn from the game's random number "
    "generator. The detector tracks every letter's fall (the boxes in the pictures: green = used in the fit, orange = matched "
    "but not used, for example while bouncing; red ticks = where the fitted fall puts the letter), fits one starting speed per "
    "letter, then finds the generator state that produces those speeds.":
        "各階の階層名の画面では、洞窟名の文字がゲームの乱数で決まる初速で落ちてきます。検出器は各文字の落下を追跡し（画像の枠："
        "緑＝あてはめに使用、オレンジ＝一致したが未使用（跳ねている間など）、赤い目盛り＝あてはめた落下での文字の位置）、文字ごとに"
        "初速を1つあてはめ、その速さを生む乱数の状態を探します。",
    "<b>Letter seed</b> is the random number generator's state when the title's letters start falling; the <b>layout seed</b> "
    "is its state when the floor was generated, a fixed number of steps earlier, and is what CaveGen needs.":
        "<b>文字シード</b>は階層名の文字が落ち始めるときの乱数の状態、<b>レイアウトシード</b>は床が作られたときの状態です。"
        "レイアウトシードは決まったステップ数だけ前にあり、CaveGenに必要なのはこちらです。",
    "<b>Letters</b>: how many letters had a clean enough fall to measure. Each letter narrows the seed down about {0}-fold, "
    "so {1} or more letters pin it down on their own.":
        "<b>文字</b>：落下をきれいに測れた文字の数。1文字ごとにシードの候補が約{0}分の1に絞られるので、{1}文字以上あれば"
        "それだけで特定できます。",
    "<b>Fit</b>: the typical distance in pixels between a tracked letter and its fitted fall. Below about {0} px is a clean "
    "capture; above about {1} px something is off (a dropped frame, blur, a mistracked letter).":
        "<b>フィット</b>：追跡した文字とあてはめた落下との典型的な距離（ピクセル）。約{0} px未満ならきれいな映像、約{1} pxを"
        "超えると何かがおかしい（フレーム落ち、ぼやけ、文字の追跡ミス）。",
    "<b>Score</b>: how far the best seed's letter speeds are from the measured ones, in units of each letter's own "
    "measurement error, squared and summed over the letters (each letter's share capped, so one bad letter can't dominate) "
    "after removing a shared speed offset. Lower is better; about {0} per letter is a perfect match.":
        "<b>スコア</b>：最良シードの文字の速さが測定値からどれだけ離れているか。各文字の測定誤差を単位として二乗し、全文字で"
        "合計します（1文字の寄与には上限があり、1つの悪い文字に左右されません）。共通の速さのずれは除いて計算します。小さいほど"
        "良く、1文字あたり約{0}なら完全に一致しています。",
    "<b>Next</b>: the same score for the second-best seed. A big gap between the two means nothing else comes close.":
        "<b>次点</b>：2番目に良いシードの同じスコア。2つの差が大きいほど、ほかに近いシードがないことを意味します。",
    "Two pictures from the video show the floor as the sublevel starts: the <b>comedown</b>, the high, wide view behind the "
    "title while the pod comes down (often dim, so it is brightened), and the <b>landing view</b>, the first view once the "
    "pod has landed. The layout, drawn by CaveGen3, outlines both on the floor: the comedown in blue (the game holds this one "
    "still shot, nearly straight down, while the title is up) and the landing view in yellow, with an arrow for the way the "
    "pod faces, so the pictures and the layout should match.":
        "動画の2枚の画像が、階の始まりの床を写しています。<b>降下中</b>は、ポッドが降りてくる間に階層名の後ろに映る高く広い視点"
        "（暗いことが多いので明るくしています）、<b>着地時の画面</b>は、ポッドが着地して最初の画面です。CaveGen3で描いたレイアウトには"
        "両方の範囲を床に示しています：降下中は青（階層名が出ている間、ゲームはほぼ真下を向いたこの1枚を動かさずに映します）、"
        "着地時は黄色で、ポッドの向きを矢印で示します。画像とレイアウトが一致するはずです。",
    "Falling letters: green boxes were used in the fit, orange ones were not; the plot below shows each letter's fall against "
    "its fitted curve. Click to enlarge.":
        "落ちてくる文字：緑の枠はあてはめに使った文字、オレンジは使わなかった文字です。下のグラフは各文字の落下とあてはめた曲線です。"
        "クリックで拡大します。",
    "Layout (CaveGen3): comedown (blue), landing view (yellow), pod facing (arrow)":
        "レイアウト（CaveGen3）：降下中（青）、着地時の画面（黄）、ポッドの向き（矢印）",
    "Comedown (behind the title, brightened)": "降下中（階層名の後ろ、明るく補正）",
    "Entry screen": "階層名の画面", "entry screen": "階層名の画面", "Landing view": "着地時の画面", "landing view": "着地時の画面",
    "comedown": "降下中", "falling letters": "落ちてくる文字",
    "<a>{0}</a> · <a>layout and luck</a>": "<a>{0}</a> · <a>レイアウトと運</a>",
    "layout and luck": "レイアウトと運",
    "Layouts by <a>CaveGen3</a> and <a>CaveGen</a>; runs from <a>speedrun.com</a>. Source: <a>github.com/{0}/p2-vod-seeds</a>.":
        "レイアウトは<a>CaveGen3</a>と<a>CaveGen</a>、記録は<a>speedrun.com</a>から。ソース：<a>github.com/{0}/p2-vod-seeds</a>",
    "<span>high</span> read with confidence <span>medium</span> <span>low</span> uncertain: left out of every total":
        "<span>高</span> 確実に読めた <span>中</span> <span>低</span> 不確か：どの合計にも含めない",
    "<span>high</span> read with confidence <span>medium</span> <span>low</span> uncertain: left out of every total (a medium "
    "seed in order with its neighbours is counted)":
        "<span>高</span> 確実に読めた <span>中</span> <span>低</span> 不確か：どの合計にも含めない（前後と順序が合う中のシードは数える）",
    "<input> Show only the uncertain sublevels": "<input> 不確かな階だけを表示",
    "Sublevel from": "階の判定元", "sequence": "並び", "digit": "数字", "digit (sequence said {0})": "数字（並びからは{0}）",
    "high": "高", "medium": "中", "low": "低", "none": "なし",
    "high confidence": "確度：高", "medium confidence": "確度：中", "low confidence": "確度：低", "none confidence": "確度：なし",
    "{0} sublevel entries": "階への突入 {0}回",
    "{0} high, {1} medium, {2} low, {3} no seed": "高 {0}、中 {1}、低 {2}、シードなし {3}",
    "processed in {0} s": "処理 {0}秒",
    "{0} measured": "{0}文字測定", "fit {0} px": "フィット {0} px", "fit None px": "フィットなし",
    "score {0} (next {1})": "スコア {0}（次点 {1}）", "score {0} (next None)": "スコア {0}（次点なし）",
    "score None (next None)": "スコアなし",
    # a reading, split at "; " and ", "
    "{0} letters measured": "{0}文字を測定", "{0} letters measured.": "{0}文字を測定。",
    "fit {0} px (clean)": "フィット {0} px（きれい）", "fit {0} px (fair)": "フィット {0} px（まずまず）",
    "fit {0} px (poor)": "フィット {0} px（悪い）",
    "fit {0} px (clean).": "フィット {0} px（きれい）。", "fit {0} px (fair).": "フィット {0} px（まずまず）。",
    "fit {0} px (poor).": "フィット {0} px（悪い）。",
    "best seed scores {0} ({1} per letter)": "最良シードのスコア {0}（1文字あたり {1}）",
    "no runner-up seed": "次点のシードなし", "no runner-up seed.": "次点のシードなし。",
    "next best {0}": "次点 {0}", "a gap of {0}": "差 {0}", "a gap of {0}.": "差 {0}。",
    "confirmed by the neighbouring sublevels' seeds.": "前後の階のシードで確認済み。",
    "confirmed by the neighbouring sublevels' seeds": "前後の階のシードで確認済み",
    "high: {0} letters, a clear best seed": "高：{0}文字、明らかな最良シード",
    "high: {0} letters": "高：{0}文字", "a clear best seed": "明らかな最良シード",
    "high: confirmed by the neighbouring sublevels": "高：前後の階で確認",
    "medium: confirmed by the neighbouring sublevels": "中：前後の階で確認",
    "low: not confirmed by the neighbouring sublevels": "低：前後の階で確認できず",
    "low: only {0} letters measured (needs {1}+)": "低：測定できたのは{0}文字のみ（{1}文字以上必要）",
    "none: fit failed: too few letters with a usable fall": "なし：あてはめ失敗（使える落下の文字が少なすぎる）",
    "none: letter fit too poor ({0} px)": "なし：文字のフィットが悪すぎる（{0} px）",
    "none: no seed matches": "なし：一致するシードなし",
    "none: too few letters measured": "なし：測定できた文字が少なすぎる",
    # notes on a reading, split at ", " and before "seed confirmed", "seed found", "(its own read", "(a linked seed"
    "timed by the video clock": "動画の時刻で計時",
    "first falling stretch": "最初の落下区間",
    "timing step of {0} frame at fall frame {1}": "落下{1}フレーム目で{0}フレームのずれ",
    "timing step of {0} frames at fall frame {1}": "落下{1}フレーム目で{0}フレームのずれ",
    "redone with a newer detector": "新しい検出器でやり直し",
    "redone with the newer detector": "新しい検出器でやり直し",
    "weaker letter matches allowed": "弱い文字一致も許可",
    "blended frames (overlapping doubled letters)": "混ざったフレーム（重なって二重の文字）",
    "blended frames (letters doubled)": "混ざったフレーム（文字が二重）",
    "cave name matched weakly (blurry capture)": "洞窟名の一致が弱い（ぼやけた映像）",
    "seed confirmed by its neighbour": "前後の階でシードを確認",
    "seed confirmed by its neighbor's": "前後の階でシードを確認",
    "seed confirmed by a later or earlier sublevel's": "前後の別の階でシードを確認",
    "seed confirmed by a chain of {0} sublevels": "{0}階の連鎖でシードを確認",
    "(its own read was out of RNG order with its neighbours)": "（単独の読み取りは前後と乱数の順序が合わなかった）",
    "(a linked seed was out of order with its neighbors, so it was dropped)": "（つながったシードが前後と順序が合わないため除外）",
    "seed found near the previous sublevel ({0} {1})": "前の階（{0} {1}）の近くでシードを発見",
    "seed found just before the next sublevel ({0} {1})": "次の階（{0} {1}）の直前でシードを発見",
    "seed found by following the gap from {0} {1} to {2} {3}": "{0} {1}から{2} {3}までの間をたどってシードを発見",
    "title cut short: cave from the route": "階層名が途中で切れた：洞窟はルートから判断",
    "letters fitted as they fell": "落下中の文字であてはめ",
    "title cut short": "階層名が途中で切れた",
    "cave as its neighbour's": "洞窟は前後の階から判断",
    "fit failed: too few letters with a usable fall": "あてはめ失敗：使える落下の文字が少なすぎる",
    "letter fit too poor ({0} px)": "文字のフィットが悪すぎる（{0} px）",
    "too few letters measured": "測定できた文字が少なすぎる",
    "no seed matches": "一致するシードなし",
})
_CONF = ("<b>Confidence</b>: <i>high</i> needs {0}+ letters, under {1} per letter and a gap of {2}+; <i>medium</i> needs "
         "{3}+, under {4} and a gap of {5}+. A seed can also be confirmed by its neighbours: consecutive sublevels' seeds "
         "sit a few hundred thousand steps apart in the generator, which almost never happens by chance.")
_CONF_JA = ("<b>確度</b>：<i>高</i>は{0}文字以上、1文字あたり{1}未満、差{2}以上、<i>中</i>は{3}文字以上、{4}未満、差{5}以上が"
            "必要です。前後の階で確認されることもあります。連続する階のシードは乱数で数十万ステップしか離れておらず、偶然そうなることは"
            "まずありません。")
put(_CONF, _CONF_JA)
put(_CONF + " A <i>medium</i> seed that sits in order between its high neighbours (within {6} million steps of each) is "
    "counted in the totals too.",
    _CONF_JA + "前後の高確度のシードの間に順序どおり（それぞれから{6}百万ステップ以内）ある<i>中</i>のシードも合計に数えます。")
_UNSURE = {"medium": "中", "low": "低", "none": "なし"}
put("Seeds read with confidence on {0} of {1} sublevels.", "{1}階中{0}階でシードを確実に読めました。")
for mask in range(1, 8):
    kinds = [k for i, k in enumerate(_UNSURE) if mask >> i & 1]
    en = ", ".join(f"{{{3 + i}}} {k}" for i, k in enumerate(kinds))
    ja = "、".join(f"{_UNSURE[k]} {{{3 + i}}}" for i, k in enumerate(kinds))
    put(f"Seeds read with confidence on {{0}} of {{1}} sublevels ({{2}} uncertain: {en}).",
        f"{{1}}階中{{0}}階でシードを確実に読めました（不確か {{2}}：{ja}）。")

# ---- Gecko code page ----
many({
    "Gecko code: play a run's layouts": "Geckoコード：記録のレイアウトで遊ぶ",
    "Pick your copy of the game and a run. The code below makes every cave sublevel that run has a trusted seed for come out "
    "with the run's layout, so you can practise the same caves the runner had. Sublevels the run doesn't have (or whose seed "
    "wasn't read with confidence) stay random. Story mode only; challenge mode and {0}-player battle are left alone.":
        "お持ちのゲームのバージョンと記録を選んでください。下のコードを使うと、その記録で信頼できるシードがある洞窟の階が記録と同じ"
        "レイアウトになるので、走者と同じ洞窟を練習できます。記録にない階（またはシードを確実に読めなかった階）はランダムのままです。"
        "ストーリーモードのみで、チャレンジモードと{0}人対戦には影響しません。",
    "Game version": "ゲームのバージョン",
    "Copy code": "コードをコピー",
    "Download .gct": ".gctをダウンロード",
    "Copied.": "コピーしました。",
    "Press Ctrl+C to copy.": "Ctrl+Cでコピーしてください。",
    "Using it": "使い方",
    "<b>Dolphin</b>: right-click the game, Properties, Gecko Codes, Add New Code; paste the code (the first line, starting "
    "with $, is its name), save, and tick it. Cheats must be on: Config, General, Enable Cheats. Then start the game.":
        "<b>Dolphin</b>：ゲームを右クリックして［プロパティ］→［Gecko Codes］→［Add New Code］。コードを貼り付けて（$で始まる"
        "1行目がコード名です）保存し、チェックを入れます。チートを有効にしておく必要があります：［設定］→［一般］→"
        "［チートコードを有効にする］。その後ゲームを起動します。",
    "<b>Nintendont</b> (Wii or Wii U): download the .gct and copy it to <code></code> on your SD card or USB drive, then turn "
    "on Cheats in Nintendont's settings. On a Wii, the Wii version's .gct works with a cheat-code loader such as Gecko OS or "
    "USB Loader GX. Nintendont keeps cheats in a small space, so a run with many sublevels can be too long for it.":
        "<b>Nintendont</b>（WiiまたはWii U）：.gctをダウンロードしてSDカードかUSBドライブの<code></code>にコピーし、"
        "Nintendontの設定でCheatsをオンにします。Wiiでは、Wii版の.gctがGecko OSやUSB Loader GXなどのチートコードローダーで"
        "使えます。Nintendontのチート用の領域は小さいため、階の多い記録ではコードが長すぎることがあります。",
    "The layout is set each time the sublevel is made, so dying, leaving and re-entering, or reloading the cave gives the "
    "same layout again. Where the runner went through a sublevel more than once (All Treasures runners farm purple Pikmin in "
    "{0} first), it is the layout of their first visit. Only the layout is fixed: enemies, eggs and anything else random "
    "after the sublevel loads behave as usual.":
        "レイアウトは階が作られるたびに設定されるので、全滅しても、出て入り直しても、洞窟をやり直しても同じレイアウトになります。"
        "走者が同じ階を複数回通った場合（お宝全回収の走者は先に{0}で紫ピクミンを集めます）は、最初に訪れたときのレイアウトです。"
        "固定されるのはレイアウトだけで、原生生物やタマゴなど、階の読み込み後に決まるランダムな要素はふだんどおりです。",
    "Sublevels in this code": "このコードに含まれる階",
    "Versions": "バージョン",
    "The versions marked untested use addresses from the <a>Pikmin {0} decompilation</a>'s symbol maps; the USA release and "
    "the USA demo {1} build were also checked against real copies of the game. The Wii version (New Play Control!) has no "
    "decompilation; its addresses were found in a memory dump of the USA game. If an untested one doesn't work for you, "
    "please say so in the suggestion box. Not supported:":
        "未検証と書かれたバージョンは、<a>ピクミン{0}の逆コンパイル</a>のシンボルマップにあるアドレスを使っています。北米版と"
        "北米体験版{1}のビルドは、実際のゲームでも確認しました。Wii版（Wiiであそぶ ピクミン2）には逆コンパイルがないため、"
        "北米版のメモリダンプからアドレスを探しました。未検証のバージョンで動かなかった場合は、ご意見箱でお知らせください。"
        "対応していないもの：",
    "Any other build or a romhack: the addresses differ; the code would do nothing or crash":
        "その他のビルドや改造版：アドレスが異なるため、コードは何もしないかクラッシュします",
    "Wii New Play Control! Europe and Japan (R92P01, R92J01): no copy of the game to find the addresses in yet":
        "Wiiであそぶ ピクミン2の欧州版と日本版（R92P01、R92J01）：アドレスを調べるためのゲームがまだ手元にありません",
    "How it works": "しくみ",
    "Pikmin {0} makes each sublevel from its global random number generator. This code hooks <code></code> (on both GameCube "
    "and Wii), just before the game's first draw for the layout (the same place as Meeo's set-seed code, whose seeds CaveGen "
    "uses). There it reads the cave and floor from the story mode section and, if the run has a seed for that sublevel, "
    "writes it into the generator's state. Seeds are the layout seeds this site shows on each run's page; the CaveGen3 links "
    "show what each one should look like. Details: <a>docs/gecko-code.md</a>.":
        "ピクミン{0}は、各階をゲーム全体の乱数から作ります。このコードは、レイアウトのための最初の乱数を引く直前にある"
        "<code></code>にフックします（ゲームキューブ・Wiiとも。Meeoのシード固定コードと同じ場所で、CaveGenはそのシードを使っています）。"
        "そこでストーリーモードのデータから洞窟と階を読み、記録にその階のシードがあれば乱数の状態に書き込みます。シードは各記録の"
        "ページに載っているレイアウトシードで、CaveGen3のリンクでそれぞれのレイアウトを確認できます。詳しくは<a>docs/gecko-code.md</a>。",
    "{0} sublevels": "{0}階",
    "USA (GPVE01)": "北米版（GPVE01）",
    "Europe / PAL (GPVP01)": "欧州版 / PAL（GPVP01）",
    "Japan (GPVJ01)": "日本版（GPVJ01）",
    "USA demo {0} (GPVE01, demo build {1})": "北米体験版{0}（GPVE01、デモビルド{1}）",
    "Wii New Play Control! USA (R92E01)": "Wiiであそぶ ピクミン2 北米版（R92E01）",
})
for v, vja in (("USA (GPVE01)", "北米版（GPVE01）"), ("Europe / PAL (GPVP01)", "欧州版 / PAL（GPVP01）"),
               ("Japan (GPVJ01)", "日本版（GPVJ01）"), ("USA demo {0} (GPVE01, demo build {1})", "北米体験版{0}（GPVE01、デモビルド{1}）"),
               ("Wii New Play Control! USA (R92E01)", "Wiiであそぶ ピクミン2 北米版（R92E01）")):
    put(v + " (untested)", vja + "（未検証）")
_UNTESTED = (" <b>This version's addresses come from the decomp's symbol map and have not been tried on a real copy of the "
             "game yet.</b>")
_UNTESTED_JA = "<b>このバージョンのアドレスは逆コンパイルのシンボルマップによるもので、実際のゲームではまだ試していません。</b>"
for plat, pja in (("GameCube", "ゲームキューブ"), ("Wii", "Wii"), ("Wii U Virtual Console", "Wii U バーチャルコンソール"), ("Wii U", "Wii U")):
    for on, oja in (("the Wii", "Wii"), ("GameCube", "ゲームキューブ")):
        _PLAT = (f" This run was played on {plat}, so on {on} its seeds give the run's layouts only where the two versions' "
                 "cave files are the same.")
        _PLAT_JA = f"この記録は{pja}で走られたため、{oja}では2つのバージョンの洞窟ファイルが同じ階でしか記録のレイアウトになりません。"
        for unt in (False, True):
            put("{0} sublevels get <a>this run's layouts</a>; any other sublevel stays random." + (_UNTESTED if unt else "") + _PLAT,
                "{0}階が<a>この記録のレイアウト</a>になり、ほかの階はランダムのままです。" + (_UNTESTED_JA if unt else "") + _PLAT_JA)
put("{0} sublevels get <a>this run's layouts</a>; any other sublevel stays random.",
    "{0}階が<a>この記録のレイアウト</a>になり、ほかの階はランダムのままです。")
put("{0} sublevels get <a>this run's layouts</a>; any other sublevel stays random." + _UNTESTED,
    "{0}階が<a>この記録のレイアウト</a>になり、ほかの階はランダムのままです。" + _UNTESTED_JA)

# ---- Suggestion box ----
many({
    "Spotted a wrong seed, a misread poko count, a run that is missing, or have an idea for this site? Leave a note. It goes "
    "privately to the site's maker (through a Google Form) and is not published. Both other fields are optional.":
        "シードの誤り、ポコの読み間違い、載っていない記録、このサイトへのアイデアなどがあればお知らせください。内容は"
        "（Googleフォームを通じて）サイトの作者だけに届き、公開されません。ほかの2つの欄は任意です。",
    "Name (optional)": "名前（任意）",
    "e.g. your speedrun.com name": "例：speedrun.comの名前",
    "Suggestion": "ご意見",
    "How to reach you (optional)": "連絡先（任意）",
    "Discord username or email, if you'd like a reply": "返信が必要な場合は、Discordのユーザー名かメールアドレス",
    "Send": "送信",
    "Sending…": "送信中…",
    "Thanks! Your suggestion was sent.": "ありがとうございます。送信しました。",
    "Sorry, it couldn't be sent. Please try again later.": "送信できませんでした。時間をおいて再度お試しください。",
})

# The footers, whether or not the account name in their link is also a runner's (a placeholder then).
for _k in list(T):
    if "github.com/{0}/" in _k:
        T[_k.replace("{0}", "JHawk4")] = T[_k].replace("{0}", "JHawk4")
