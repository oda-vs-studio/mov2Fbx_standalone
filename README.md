# Movie2Anim Standalone

Unreal Editorを起動せず、人物動画からSMPL-Xの3D骨格アニメーションを推定する検証用ツールです。
ローカルのUE 5.8プラグインに含まれるONNXモデルを初回に抽出し、以降はPython / ONNX Runtimeで実行します。
FBX SDKを使う小さなネイティブ書き出しプログラムにもUEモジュールの依存はありません。

## 起動

このPCではセットアップ済みです。`LaunchStandalone.bat` をダブルクリックしてください。
指定7動画の解析結果は `OpenValidation.bat` から開けます。実測結果は `docs/VALIDATION.md` にあります。

1. 動画を選択します。
2. 開始Fと終了Fを指定します。両端を含みます。初回は16〜120フレーム程度を推奨します。
3. 必要なら回転と人物ROIを指定します。ROI選択ウィンドウはEnterで確定します。
4. 新しい出力フォルダ名を指定し、`Analyze + export` を押します。
5. 完了後に `Open 3D preview` または `Open output` を押します。

`dml` はDirectML GPU、`cpu` はCPUです。現在のRTX 5090で両方の経路を実行確認しています。
最終段のHueは、UE側の実装と同様にCPUへ固定しています。
解析中のCancelは、このツールが起動した推論プロセスだけを停止します。途中ファイルは残り、成功表示にはなりません。

## 2人の動画

1人目と2人目のROIを両方指定すると、同じフレーム範囲を人物別に処理します。
`person_01` / `person_02` に別々のFBXを出力し、出力直下の `preview.html` で同期比較できます。

これは**固定した人物範囲を使う独立推定**です。自動の人物識別・交差後のID維持・接触拘束・2人の正確な相対位置は実装していません。
ROI内に他の人物が大きく入る場面や遮蔽では、手足が混ざる可能性があります。`keypoints.mp4` を元動画と照合してください。
各人物の出力は個別に原点化されます。2つのFBXを原点に置くだけでは元動画の間隔になりません。

## 出力

| ファイル | 内容 |
| --- | --- |
| `motion.fbx` | SMPL-Xの55ボーン。Y-up、cm、アニメーションのみ |
| `motion.bvh` | 同じ骨格のBVH。Y-up、cm |
| `motion.npz` | Hueの生出力。姿勢165値、体型10値、移動3値、接触logit6値／フレーム |
| `world_motion.npz` | カメラ傾き・軸・原点を補正した骨格。位置はm、Quaternionはxyzw |
| `features.npz` | 2Dキーポイント、3D特徴量、ROI、fps、焦点距離 |
| `keypoints.mp4` | 入力映像に推定した関節を重ねた確認動画 |
| `preview.html` | インターネット不要の3D骨格プレビュー。ドラッグ回転・ズーム・シーク |
| `metadata.json` | 入力範囲、設定、座標系、処理時間、制約 |
| `fbx_validation.txt` | FBXをSDKで再読み込みし、全キーのローカル変換を検証した結果 |
| `SUCCESS` | 推論・書き出しがすべて完了した場合にだけ作成 |

FBXは**Mannyの骨格ではありません**。Manny用IKリターゲットを含め、元のMovie2Animとの完全互換は未実装です。

## CLI

リポジトリのルートで実行します。

```powershell
.\.venv\Scripts\python.exe -m m2a doctor
.\.venv\Scripts\python.exe -m m2a solve 'D:\video.mp4' --output runs/test01 --start 0 --end 123 --provider dml
.\.venv\Scripts\python.exe -m m2a solve 'D:\two_people.mp4' --output runs/pair01 --start 0 --end 123 --provider dml --roi 140 15 435 478 --roi2 430 15 710 478
.\.venv\Scripts\python.exe -m m2a export runs/test01
```

`--rotation` は0/90/180/270度、`--focal` は縮小後の画像座標の焦点距離px、`--height` は身長cm（0は自動）です。
ROI座標は、回転後かつ高さ896px以下へ縮小した動画のピクセル座標です。GUIのROI選択では自動的にその画像を使います。
12〜600フレームに対応します。長い動画は範囲を分けてください。動画のVFRタイムスタンプ補正は未実装で、OpenCVが返すfpsに従います。

## 初期セットアップの再現

Python 3.13、Visual Studio C++ツール、ローカルUE 5.8とMetaHumanBodyTracker 1.0.0が必要です。
`SetupStandalone.bat` が専用venv、依存パッケージ、モデル、骨格データ、FBX helperを作ります。

- UE既定パス: `D:\UE\UE_5.8`。変更時は環境変数 `UE_ROOT` を設定します。
- Visual Studioのvcvars64.batを変更する場合は `VS_VCVARS` を設定します。
- ONNX外部重みは元アセットから抽出し、標準の外部データ参照へ変換します。
- モデル、SDK DLL、生成アニメーション、venvはGit管理外です。
- `.venv` はPC間でコピーせず再作成してください。抽出済みmodelsとbinが揃えば通常実行にUEのインストール場所を参照しません。

## 実装範囲

移植済み: NNEモデル抽出、カメラ推定、ViTPose、CHMR、Hueの49ステップ＋最終ステップ、時間窓処理、SMPL-X骨格、FBX/BVH、プレビュー、2つのROIの個別処理。

UEとの差分:

- Detectron2/SAM2の検出・追跡は固定ROIに置き換えています。
- カメラ校正は選択範囲の先頭フレームで行います。
- UEのBodyTrackingOptimizerによる接地・足固定は未移植です。
- 床合わせは足・足首の関節位置を使います。UEのスキンメッシュの最低点とは異なります。
- SMPL-XからMetaHuman/MannyへのIKリターゲット、Root/Pelvisの各モード、YAML履歴は未移植です。
- OpenCVの補間、NumPy乱数、ONNX Runtimeの実装差により、UEとの数値一致は保証していません。

## 検証

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/validate_user_videos.py
```

指定7動画の全124フレームを使う実推論テストとログは `runs/user_validation` に保存します。
成功済みケースは再実行を省略します。失敗ケースを再試験する場合は、元の出力を別名へ移してから実行してください。
数値的な出力成功とモーション品質の確認は区別し、2人の動画は特にキーポイント確認動画を見てください。

設計と由来は `docs/ARCHITECTURE.md` を参照してください。
