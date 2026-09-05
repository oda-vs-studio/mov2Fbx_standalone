# Movie2Anim Standalone

Unreal Editorを起動せず、人物動画からSMPL-Xの3D骨格アニメーションを推定する検証用ツールです。
姿勢推定用ONNXモデルはローカルUE 5.8プラグインから初回に抽出します。自動検出用YOLOX-Sは公式公開モデルを初回に取得し、以降はPython / ONNX Runtimeだけで実行します。
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

## 動画をドロップしてQuinn FBXを書き出す

`DropVideoToQuinnFBX.bat` に動画をドロップしてください。複数ファイルも順に処理します。
例: `D:\video\dance.mp4` → `D:\video\dance.fbx`。既存の同名FBXは上書きせずエラーにします。

- 入力骨格: `C:\temp\SKM_Quinn_Simple.FBX` から抽出した89ボーン。メッシュは含みません。
- `QuinnSkeleton.fbx` は骨だけの基準姿勢です。通常実行では元FBXやUEを参照しません。
- 全フレームを処理します。12フレーム以上、自動人物検出・追跡による1〜2人対応です。600フレーム制限は撤廃し、動画を順次デコードして全長を推論窓で処理します。長尺は処理時間と出力サイズが増えます。
- AポーズとTポーズの差、ボーンのローカル軸、体格に応じた移動量を補正します。
- 骨名と親子関係を維持し、指を含む55ボーンを対応付けます。余剰のねじり骨は親に追従し、IK補助骨は対応する手足へ追従します。
- rootにシーン内の移動、pelvisに身体の回転を格納。前回と同じY-up、cmです。足固定・接触IK・Quinnの補正リグは適用しません。
- 2人の場合は `<動画名>.fbx` に2人を収録し、`<動画名>_person_01.fbx` / `_person_02.fbx` も出力します。個別FBXも共通座標を保持し、両方を変換せず読み込むと位置関係が保たれます。
- 人物ごとに原点化せず、カメラ・原点・移動量の縮尺を共有します。接地を基準に共通床を設定します。**固定カメラの単眼映像からの推定**なので、実距離・前後関係・接触位置の正確さは保証できません。
- **冒頭0.2秒は両足が接地している前提**で、リターゲット前に足裏の仮想接地点から傾きを推定します。共通の床回転に加え、人物ごとの残りの傾きを初期接地点の周りで一度だけ補正します。その後の前傾・ジャンプ・関節運動を毎フレーム垂直化する処理ではありません。
- 足裏平面が不安定、広がり不足、推定角度40度以上の場合は、その人物独自の追加補正を省略します。結果と角度は `scene.json` を参照してください。
- 冒頭から片足立ち・空中・階段上の場合はCLIに `--no-tilt-correction` を付けて補正を無効化できます。
- `runs/drop/日時_ID/tracking.mp4` は自動人物IDの確認映像、`scene_preview.html` は2人を同じ空間で見るプレビューです。長尺のHTMLプレビューは軽量化のため間引き表示しますが、FBXは全フレームを書き出します。
- `runs/drop/日時_ID` に生の推定結果、リターゲットNPZ、検証ログを保存します。

人物検出モデルは `SetupPersonDetection.bat` で公式YOLOX-S ONNXを取得できます（通常実行はオフライン）。このPCでは設定済みです。

骨格の再設定（初回または別PC）は次を実行してください。

```powershell
tools\build_skeleton.bat
tools\build_retarget.bat
.venv\Scripts\python.exe -m tools.configure_quinn 'C:\temp\SKM_Quinn_Simple.FBX'
```

既存の推定結果への適用はPythonから `m2a.retarget.export_retarget(run_directory, output_fbx)` を呼び出せます。
通常GUIと既存CLIの `motion.fbx` は引き続きSMPL-X骨格です。Quinn出力は上記BATで行います。

## GUIの手動2人モード（従来方式）

自動検出・共有位置・傾き補正は上記のBATを使用してください。以下はGUIの従来方式です。

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

この表は通常GUI / solveコマンドの出力です。Quinnへの書き出しは上記の専用BATを使用します。元のMovie2Animとの完全互換は未実装です。

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
12フレーム以上に対応します。固定600フレーム制限はありません。動画の画像は一括保持せず、時間方向の推論を窓に分割します。動画のVFRタイムスタンプ補正は未実装で、OpenCVが返すfpsに従います。

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

- 自動BATではYOLOX-S + 外観・移動量による追跡を使用します。GUIは固定ROIです。人物が長時間重なる場面での識別やマスク分離は未実装です。
- カメラ校正は選択範囲の先頭フレームで行います。自動BATは全人物で共有します。
- UEのBodyTrackingOptimizerによる接地・足固定は未移植です。
- 自動BATは基準姿勢の足首とつま先の高低差を補正した仮想足裏点を使用します。GUIは足・足首の関節位置です。UEのスキンメッシュ接地とは異なります。
- QuinnへのFKリターゲットは専用BATで実装済みです。UEのIKリターゲット、Root/Pelvisの各モード、YAML履歴は未移植です。
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
