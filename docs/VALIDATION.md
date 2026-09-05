# 実動画検証結果

Unreal Editor不使用、RTX 5090 / DirectML。7動画、合計10人物、各124フレーム・24fps。

| 動画 | 人数 | 時間 | 結果 |
| --- | --- | --- | --- |
| 00016 | 1 | 34.3秒 | success |
| 00011 | 1 | 34.8秒 | success |
| 00014 | 1 | 35.1秒 | success |
| 00015 | 1 | 33.5秒 | success |
| 00025 | 2 | 62.2秒 | success |
| 00023 | 2 | 62.7秒 | success |
| 00024 | 2 | 63.0秒 | success |

全出力でNaN/Infなし、骨長一定、FBX再読み込み後の全ローカル変換一致を確認。中央フレームの関節重ね画像を目視し、1人のパンチ姿勢および2人の左右の身体が取得されていることを確認しました。遮蔽された手足や全フレームのID維持の品質保証ではありません。

`OpenValidation.bat` から一覧を開けます。詳細は `runs/user_validation/numeric_validation.json`、各ケースの `metadata.json` / `fbx_validation.txt` / `keypoints.mp4` にあります。
