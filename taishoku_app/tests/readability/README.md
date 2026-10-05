# 読みやすさ点検（2026-10-04）

7種類の架空データを、実際の評価器とHTML/PDF生成器に通した。Tallyへの送信、承認、外部DBへの書込み、納品は実行していない。

| パターン | 見つけた問題 | 修正 |
| --- | --- | --- |
| 自己都合退職 | 通常ルートに持ち物・窓口で伝える言葉がない。待期・認定の説明がない | 窓口での言い方と必要書類、写真の省略条件を追加。用語と受給フローを折りたたみ |
| 休職中 | 冒頭の「まず確認」が重複。保険者不明時の逃げ道が遠い | 最初の行動を直接表示。行動カードに資料と不明時の聞き方 |
| 体調不良で退職予定 | 継続条件の確認だけで何を聞くか不明 | 加入先への質問例・準備する日付を表示。退職日出勤の警告を保持 |
| 離職理由の争い | 長い見出し、同じ説明の繰り返し | 短い見出しと窓口で伝える言葉に分離。経緯・資料の準備方法 |
| 情報不足 | 内部名 age_at_exit が露出。情報の調べ方がない | 日本語の年齢案内、給与・保険・休業日などの調べ方を追加 |
| 体調不良で退職済み | 働けない人向けの流れに通常の失業手当申請を強く表示 | 現在の相談と、働けるようになってからの流れを分離 |
| 保険者不明 | 長い同一案内が2回出る | 加入先確認を1か所に集約 |

共通：冒頭の窓口一覧・制度名称説明を折りたたみ、手続き一覧を本文へのリンクにした。国保・住民税・DCの「どこに何を聞くか」を具体化。末尾の公式URLをタップ可能にし、重複を除去。CSSに長い文字列の折返しと44pxの折りたたみ操作領域を追加。

## 検証

- 元のbundleを展開し、build.shのパッチを本番順に適用して7件のHTML/PDFを生成。
- 変更前後の評価JSONは evaluated_at のみ除外して完全一致（給付額、可否、review、行動順を含む）。
- 最終承認直前に追加される注意書きも、同じ関数を切り出してHTMLへ挿入。2回呼んでも増えないことを確認。承認関数は呼んでいない。
- HTML内リンク、公式リンク、プレースホルダー残存、内部名露出、退職日出勤の警告を検証。
- 既存 partial_guidance.test.mjs 合格。これはローカルテストでありTally/NeonのE2Eではない。
- Pythonコンパイル・Node構文チェック合格。
- 2026-10-05追記：npm配布のChromium 153とローカル日本語フォントでブラウザー検証を実施。7種類×360/390/768pxの21通りで横はみ出しなし、全detailsの開閉・ページ内リンク・ページエラーなしを確認。390pxスクリーンショットも確認。実機Android/iOSの検証ではない。
- 狭い画面で見出し末尾1文字だけ改行される問題を確認し、640px以下のh1を26pxへ変更。代表1種類を同じ3画面幅で再検証し合格。
- 2026-10-05：ユーザーがMy Workspaceの使用を承認。対象サービスtaishoku-workflow-production-freeのplan=freeを確認。ただし使用量・超過課金設定は接続APIで取得できず、ブラウザーのGoogleログインは502で停止。追加費用0円を確認できないため、マージ・デプロイは保留。

## 公式根拠

2026-10-04確認。既存の金額・給付判定を変更していない。

- ハローワーク（必要書類・写真・離職票未着・離職理由の相談）: https://www.hellowork.mhlw.go.jp/insurance/insurance_procedure.html
- 厚生労働省（基本手当・再就職手当）: https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000139508.html
- 協会けんぽ（申請書）: https://www.kyoukaikenpo.or.jp/application_form/benefit/001/index.html
- 協会けんぽ（FAQ）: https://www.kyoukaikenpo.or.jp/g6/cat620/r307
- 年金手続きの具体的持ち物（自治体公式）: https://www.city.shizuoka.lg.jp/s8435/s000620.html
- 年金の全国案内へのリンク: https://www.nenkin.go.jp/service/kokunen/kanyu/20140710-03.html

## 再現

本番と同じbuild.shでruntimeを準備した後:

```sh
python3 taishoku_app/tests/readability/generate.py taishoku_app/runtime /tmp/after
node taishoku_app/tests/readability/add_caution.mjs taishoku_app/runtime/workflow_pipeline_v0.1/instant_finalize.mjs /tmp/after
python3 taishoku_app/tests/readability/verify.py /tmp/before /tmp/after
node --test taishoku_app/tests/partial_guidance.test.mjs
```

`/tmp/before`は変更前ブランチのruntimeで同じgenerate.pyを実行して用意する。出力には架空データのみ使用する。

## PDF廃止（2026-10-05）

ユーザーの指定により、新規レポートはHTMLだけを生成する。build.shの最後でPDF処理とPyMuPDF依存を除去し、manifestのレビュー対象をhtml_previewに変更。保存済みの過去PDFを削除する処理は追加していない。

- 本番順に全パッチを適用したruntimeで検証。
- 7種類の架空Tallyペイロードを実際の正規化・判定・生成処理へ入力。通常1件、要確認5件、停止1件の状態と判定が変更前後で一致。
- 生成6件のHTMLはバイト単位で一致。新規PDFは0件。Python -Sでも生成でき、pipパッケージ不要を確認。
- 承認、最終化、秘密URL、評価器、ルール、保存・復元のファイルハッシュは変更前後で一致。
- テストは外部サービスへの接続・承認・公開なし。Render廃止や別ホストへの移行は未実施。

```sh
# BASELINE_RUNTIMEはPDF廃止パッチ直前のruntimeを別フォルダーに保存する
python3 taishoku_app/tests/readability/generate.py taishoku_app/runtime /tmp/html-fixtures
node taishoku_app/tests/readability/html_only.test.mjs BASELINE_RUNTIME taishoku_app/runtime /tmp/html-fixtures
```
