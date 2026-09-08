# Movie2Anim Standalone

Unreal Editorを起動せず、人物動画からSMPL-Xの3D骨格アニメーションを推定する検証用ツールです。
姿勢推定用ONNXモデルはローカルUE 5.8プラグインから初回に抽出します。自動検出用YOLOX-Sは公式公開モデルを初回に取得し、以降はPython / ONNX Runtimeだけで実行します。
FBX SDKを使う小さなネイティブ書き出しプログラムにもUEモジュールの依存はありません。

## BATの用途

| BAT | 用途 |
|---|---|
| `SetupMovie2Anim.bat` | 初回・更新時の一括セットアップ |
| `DropVideoToMovie2Anim.bat` | 通常の動画ドロップ。移動カメラ・成功全区間・専用フォルダ保存 |
| `DropVideoToQuinnFBX.bat` | 固定カメラ用の従来処理 |
| `LaunchStandalone.bat` | GUIでフレーム範囲・ROIなどを指定する処理 |

日常の利用は上の2本です。重複した個別セットアップと旧名のドロップBAT、過去の検証一覧専用BATは整理済みです。個別の保守処理が必要な場合は `tools.bootstrap_setup`、`tools.setup_camera`、`tools.setup_detection` のPythonモジュールを直接実行できます。

## 移動カメラ：一括セットアップと動画ドロップ

1. `SetupMovie2Anim.bat` を実行し、UE 5.8のフォルダ（Engineを含むフォルダ）を選択します。
2. `DropVideoToMovie2Anim.bat` に動画をドロップします。複数動画にも対応します。

通常ドロップは主役1人を推論します。動画全体で実検出フレーム数が最多の人物IDを選び、同数なら検出時の矩形面積の中央値が大きい人物を選びます。背景人物の出入りでは主役を分割せず、背景人物もカメラ推定の除外マスクには残します。選択結果は `_work/actor_selection.json` と出力JSONに記録します。これは主役の意味を理解する判定ではなく、主役自身の長い未検出やID分断・カメラ推定失敗は従来どおり区間分割します。

2人を含める従来の処理は `DropVideoToMovie2Anim.bat --actor-mode all "D:\video\pair.mp4"` で実行できます。固定カメラ用BATの動作は変わりません。

元動画の隣に `動画名_Movie2Anim_日時_ID/` を毎回新規作成し、全成功区間のFBX、区間ごとのJSON、`動画名_segments.json` を保存します。中間ファイル・詳細レポート・プレビューは同じフォルダの `_work/` に残ります。失敗後も再探索します。区間間の座標原点は独立、単独区間は最低12フレームです。既存の成果物・モデルは削除しません。

セットアップにはWindows x64、Python 3.13 x64（PATHまたはM2A_PYTHON）、Git、Visual Studio C++ Build Tools、対象プラグインを含むUE 5.8、対応するNVIDIA GPU/ドライバとネット接続が必要です。人体用Python 3.13仮想環境、UE由来ONNX/骨格データ・FBXツール、検出モデルを用意した後、カメラ用Python 3.12仮想環境・CUDA 12.8版Torch・GeoCalib・DA3-LARGEをセットアップします。QuinnSkeleton.fbxと骨格設定は同梱を再利用します。UEに対象プラグインがない場合はモデル取得できません。

無人実行例：`SetupMovie2Anim.bat --engine "D:\UE\UE_5.8" --noninteractive`。GIANTを使う場合は `--camera-model DA3-GIANT` を追加し、推論にも同じオプションを指定します。既定はLARGEです。初期両足接地を仮定できない動画では推論時に `--no-tilt-correction` を指定します。調達元・配置・固定revisionは [移動カメラ説明](docs/MOVING_CAMERA.md) と従来のセットアップ説明を参照してください。

## 起動

このPCではセットアップ済みです。`LaunchStandalone.bat` をダブルクリックしてください。
指定7動画の解析結果は `runs/user_validation/index.html` を直接開いて確認できます。実測結果は `docs/VALIDATION.md` にあります。

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

人物検出モデルは `SetupMovie2Anim.bat` で公式YOLOX-S ONNXを取得できます（通常実行はオフライン）。このPCでは設定済みです。

Quinn基準骨格を変更する場合は、後述の `SetupMovie2Anim.bat --quinn` を使用してください。元の骨格データをバックアップしてから切り替えます。

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

## リポジトリ取得後のセットアップ（Windows）

このリポジトリにはコードと**Quinnの基準骨格**を含めています。巨大な推論モデル、Python仮想環境、生成動画、実行結果、ビルド済みDLL/EXEは含めません。
通常実行ではUEを起動しません。初回のモデル抽出とFBX補助プログラムのビルドにUEのファイルを利用します。

### 最初に用意するもの

1. Windows x64 と [Python 3.13 x64](https://www.python.org/downloads/windows/)。公式インストーラのPython Launcher、pip、Tcl/Tkを含めてインストールします。
2. Visual StudioまたはBuild Toolsの **「C++によるデスクトップ開発」**。MSVC x64コンパイラとWindows SDKが必要です。セットアップが `vswhere.exe` で自動検出します。
3. **Unreal Engine 5.8**。この実装で検証した版は5.8.2です。
4. Fabの [MetaHuman Animator Markerless Motion Capture Plugin](https://www.fab.com/listings/4095b8e0-3eff-44f1-acb4-cb40b99228b9) をそのUEにインストールします。検証済みプラグイン版は1.0.0です。通常のMetaHumanプラグインだけでは必要なモデルが揃いません。
5. 初回のPyPIパッケージとYOLOX取得にインターネット接続。UEを除き、セットアップ中はモデルの抽出用バックアップも含め**15GB以上の空き容量**を目安にしてください。動画出力領域は別途必要です。

選択するUEフォルダの下に、次が必要です。セットアップはこれらを**変更前に検査**し、不足しているパスを表示します。FBXヘッダ・ライブラリがないUEインストールでは、エンジンソース／依存ファイルを含むUE環境を用意してください。

```text
<UE>/Engine/Plugins/Marketplace/MetaHumanBodyTracker_5.8/Content/Models/Offline/*.uasset
<UE>/Engine/Plugins/Marketplace/MetaHumanBodyTracker_5.8/Content/SMPLX_NEUTRAL_2020_locked_head_array_f32.uasset
<UE>/Engine/Source/ThirdParty/FBX/2020.2/include/fbxsdk.h
<UE>/Engine/Source/ThirdParty/FBX/2020.2/lib/vs2017/x64/release/libfbxsdk.lib
<UE>/Engine/Binaries/ThirdParty/FBX/2020.2/Win64/libfbxsdk.dll
```

モデル抽出は上記バージョンの未Cookアセット形式に対応しています。他のUE／プラグイン版への互換性は保証していません。

### 実行

1. リポジトリを任意の書き込み可能なフォルダに取得します。
2. **`SetupMovie2Anim.bat` をダブルクリック**します。
3. フォルダ選択画面で、`Engine` フォルダを含むUE 5.8のルートを選びます。`Engine` 自体を選んだ場合も認識します。
4. 自動で以下を行います。
   - Python 3.13 x64を確認し、リポジトリ専用 `.venv` を作成。
   - `requirements.lock.txt` の固定バージョンを `.venv` にインストール。
   - 選択したUEから7個の姿勢推定ONNX、外部重み、SMPL-X骨格を抽出。
   - Visual Studioを検出し、3個のFBX補助EXEをビルド。必要なFBX DLLをコピー。
   - 公式YOLOX-S ONNXをダウンロードしてSHA256を照合。
   - 同梱Quinn骨格を使って変換・FBX往復テストを実行。
   - カメラ用Python 3.12環境、CUDA版Torch、GeoCalib・DA3モデルをセットアップ。
5. 一括セットアップ末尾の `Setup complete: body models, detection, Quinn FBX tools, GeoCalib and DA3` と出れば完了です。`DropVideoToMovie2Anim.bat` に動画をドロップしてください。GUIは `LaunchStandalone.bat` です。

**同梱Quinnを使う限り、別途FBXを探す必要はありません。** `models/quinn_skeleton.txt` がない場合だけ、エクスポート済みQuinn FBXの選択画面を出します。別の基準FBXを明示的に指定するときは、以下の `--quinn` を使用します。

```bat
SetupMovie2Anim.bat --engine "D:\UE\UE_5.8" --noninteractive
SetupMovie2Anim.bat --engine "D:\UE\UE_5.8" --quinn "D:\Assets\SKM_Quinn_Simple.FBX" --noninteractive
python -m tools.bootstrap_setup --engine "D:\UE\UE_5.8" --check-only --noninteractive
```

`--check-only` は前提ファイルと開発環境の読み取り検査のみです。UE未指定ならGUI選択、環境変数 `UE_ROOT` 指定済みならその値を使用します。Pythonの選択を固定する場合は `M2A_PYTHON` にPython 3.13の実行ファイル、VSを指定する場合は `VS_VCVARS` に `vcvars64.bat` の絶対パスを設定します。無人実行では `M2A_SETUP_NO_PAUSE=1` にするとBAT末尾のキー待ちを省略します。

### 調達元と配置先

手作業でモデルを配置する必要はありません。対応関係は以下です。

| 必要なもの | 調達元／生成方法 | リポジトリ内の配置先 | Git同梱 |
| --- | --- | --- | --- |
| Quinn基準姿勢FBX（骨だけ・89本） | 検証用 `SKM_Quinn_Simple.FBX` から抽出済み | `QuinnSkeleton.fbx` | **あり** |
| Quinn骨名・階層・基準変換と由来 | 上記FBXの抽出データ | `models/quinn_skeleton.txt`, `models/quinn_manifest.json` | **あり** |
| カメラ校正モデル | UEプラグインの `Content/Models/Offline/camera_calib.uasset` | `models/camera_calib.onnx` | なし |
| CHMR画像特徴・人物特徴モデル | 同ディレクトリの `chmr_backbone.uasset`, `chmr_head.uasset` | `models/chmr_backbone.onnx`, `models/chmr_head.onnx` | なし |
| Hue動画モーションモデル | 同ディレクトリの `hue_step_simplified.uasset`, `hue_finalStep_simplified.uasset` | `models/hue_step_simplified.onnx`, `models/hue_finalStep_simplified.onnx` | なし |
| ViTPoseと後処理モデル | 同ディレクトリの `ViTPose.uasset`, `ViTPosePost.uasset` | `models/ViTPose.onnx`, `models/ViTPosePost.onnx` | なし |
| ViTPose外部重み（約2.55GB） | `ViTPose.uasset` の追加データから抽出 | `models/OnnxExternalDataBytes`, `models/OnnxExternalDataDescriptor` | なし |
| SMPL-Xの55関節と体型差分 | プラグイン直下Contentの `SMPLX_NEUTRAL_2020_locked_head_array_f32.uasset` から計算 | `models/skeleton.npz`, `models/skeleton_manifest.json` | なし |
| 抽出済みモデルの由来・ハッシュ | `tools/extract_models.py` が生成 | `models/manifest.json` | なし |
| YOLOX-S人物検出モデル | [Megvii公式ONNX配布](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx) | `models/yolox_s.onnx`, `models/yolox_manifest.json` | なし |
| FBX書き出し・骨格抽出EXE | `native/*.cpp` を選択UEのFBX SDKでビルド | `bin/fbx_export.exe`, `bin/fbx_skeleton.exe`, `bin/fbx_retarget.exe` | なし |
| FBXランタイム | 選択UEの `Engine/Binaries/ThirdParty/FBX/2020.2/Win64/libfbxsdk.dll` | `bin/libfbxsdk.dll` | なし |
| Python依存 | PyPI、`requirements.lock.txt` に固定 | `.venv/` | なし |

YOLOXのSHA256は `tools/setup_detection.py` に固定しています。UEモデルのSHA256は抽出時に記録します。CHMR/Hueを同名の一般公開モデルに置き換えることはできません。上記プラグインのアセットが必要です。

Quinnの元データを別途用意する場合、検証UEには `Templates/TemplateResources/High/Characters/Content/Mannequins/Meshes/SKM_Quinn_Simple.uasset` があります。UEのThird Personテンプレート等でQuinnを開き、Content BrowserのAsset Actions → ExportでFBXに書き出します。この手動作業は同梱骨格を使う場合は不要です。`quinn_manifest.json` の元ファイルパスは由来の記録であり、そのPCパスへのアクセスは通常実行に必要ありません。

### 再実行・データ保持・Git

- 既存 `.venv` は再利用します。Python版が異なる場合は削除せずエラーにします。
- モデル一式が揃っている場合はハッシュ検証して再利用します。新規抽出は `work/setup_models_*` に行い、検証後に `models/` へ配置します。既存の異なるファイルを黙って上書きしません。
- 抽出時のバックアップは `work/setup_models_*` に残します。容量が必要ならセットアップ成功後に利用者が整理できます。
- 明示的にQuinnを差し替える場合、元の骨格データは `work/quinn_backup_*` に残します。
- `runs/`, `work/`, `.venv/`, `bin/`, 大きなモデル／中間ファイルは `.gitignore` で除外します。**Quinnの小さな3ファイルだけ例外として同梱**します。
- Gitから除外しても実ファイルは消しません。推論の再実行に必要なモデルはローカルに残ります。
- Git履歴の書き換えは行いません。すでに他のブランチ／過去コミットへ巨大ファイルを入れた別リポジトリでは、追跡解除だけで過去履歴のサイズが減るわけではありません。
- 過去の検証動画・結果（runs/user_validation）は同梱しません。新規取得したPCは自身の動画で検証してください。

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

## 移動カメラ（同じレンズ・ズームなし）

SetupMovie2Anim.bat で専用CUDA環境を作り、DropVideoToMovie2Anim.bat に動画をドロップしてください。GeoCalib + DA3 の処理、調達元、制約は [docs/MOVING_CAMERA.md](docs/MOVING_CAMERA.md)、進捗は [docs/MOVING_CAMERA_PLAN.md](docs/MOVING_CAMERA_PLAN.md) を参照してください。従来の固定カメラBATも使用できます。

### 長い動画名への対応
出力フォルダには動画名の先頭最大24 UTF-16単位だけを使い、日時・IDを付けます。成果物名には動画名を繰り返さず、scene.fbx または scene_frames_000834-000845_segment_person_01.fbx のように保存します。元動画の完全なパスは input.json に保存します。保存先の親フォルダ自体が長すぎる場合は推定開始前に通知します。既存の結果は変更しません。
