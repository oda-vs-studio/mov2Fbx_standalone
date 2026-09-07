# Moving camera implementation plan (2026-09-07)

Assumption: one fixed lens, no zoom, continuous shot. Preserve existing fixed-camera mode and raw Hue outputs.

- [x] Inspect Image_to_Mesh setup and official DA3/GeoCalib sources.
- [x] Setup isolated Python 3.12 + PyTorch 2.7.1/cu128 for Windows RTX 5090. Preserve current Python 3.13/DirectML environment. Pin official source commits, weights and dependencies.
- [x] Fit one shared GeoCalib simple-radial lens across sampled frames; rectify every frame to the same centered square-pixel pinhole image.
- [x] Infer DA3 overlapping multi-frame windows covering every frame. Refine/check poses with fixed-intrinsic background correspondences. Align overlaps using common depth points (Sim(3)); reject unreliable joins instead of silently truncating.
- [x] Preserve camera w2c matrices, depth, lens metadata and diagnostics. Keep models off GPU before body inference.
- [x] Establish one scene scale from body/depth evidence across actors. Convert camera-relative body root positions and orientations into shared world coordinates before floor correction and retargeting.
- [x] Add setup/drop entry points and README instructions; retain fixed mode.
- [x] Test known synthetic transforms, moving-camera background reprojection, real one/two-person inference and full FBX SDK roundtrip. Record actual results and limitations.

## Findings and gates

DA3 API emits OpenCV world-to-camera [R|t]. A camera center is -R.T @ t, not t. Main DA3 model depth scale is arbitrary. Intrinsics-only input does not condition the pinned backbone (camera encoder requires extrinsics); passing K alone is insufficient. GeoCalib lens rectification is shared by DA3 and body stages. DA3 has no built-in dynamic-person mask argument; exclude person ROIs from geometric refinement/validation instead of claiming masked network inference.

Epic CamAngvel is initialized to zero; its trained encoding is not documented in the available source. Do not invent that encoding. Initial integration uses explicit camera-space reconstruction and records this approximation; camera accuracy and final body quality are separate checks.

Image_to_Mesh setup deletes its venv and pins torch 2.6/cu126. Reuse neither behavior: Blackwell support starts at torch 2.7/cu128. DA3 requires numpy<2, incompatible with the existing body environment, so use a separate process and venv. Standard CUDA wheels avoid a CUDA Toolkit compiler dependency for inference; driver and an actual GPU kernel test are required.

## Sources

- https://github.com/ByteDance-Seed/Depth-Anything-3 (3d835ec1a5802d64a8b8b15f817a1ab54809bfe4)
- https://github.com/cvg/GeoCalib (97b8968e7798a66bf04fcf791fb535624241bda7)
- https://pytorch.org/blog/pytorch-2-7/
- D:\Work\Tool\Image_to_Mesh\setup.bat and requirements.txt


## 実装・検証結果（2026-09-07）

実験モードの実装とセットアップは完了。上のチェックは実装・試験の実施を示し、すべての動画の精度合格を意味しない。

- SetupCamera.batの実行成功。Windows RTX 5090 / driver 591.86 / Python 3.12.14 / torch 2.7.1+cu128 / NumPy 1.26.4でCUDA演算を確認。
- DA3-LARGE revision c54c26b16ec04d218e8d584ecf4bce082a9fcc20、GeoCalib distortedを取得・ハッシュ検証。既存の人体環境とUE由来モデルを保持。
- カメラはDA3深度と姿勢初期値を使った固定Kの背景VOへ変更。独立したフレーム別PnPの揺れを抑え、重複区間の深度尺度と最後の共通姿勢で窓を接続。
- 歩行273フレーム、走行299フレームを全長出力。既存の二人動画16フレームで両者を同時範囲に出力。すべてFBX SDK再読込のローカル行列誤差0。
- 合成カメラの移動・回転、共通尺度、窓接続の連続性、回転の丸め誤差などを含む24テスト成功。
- 歩行の最大フレーム間ルート移動は約0.65m→0.10mへ改善。
- `C:/temp/fbxview.mp4` はユーザー訂正によりテスト対象から除外。

## 残る精度課題

- [ ] 走行サンプルの大きな上下ドリフトを解消する（推定上下範囲6.19m）。以前の出力にはquality_warningsを記録。最新の区間接続検証では停止し、再出力できていない。
- [ ] HueのCamAngvel表現と出力座標の学習上の意味を特定し、明示的な後段変換との二重補正を避けて統合する。
- [ ] 必要に応じて背景の床・重力と人体接地の共同最適化を追加する。現時点はループ閉合・足固定なし。

## 検証ファイル（Git外）

- runs/camera_walk_final/ : 歩行の最終カメラ・人体・FBX
- runs/camera_run_final/ : 走行の以前の出力と精度警告（最新判定では停止）
- runs/camera_pair_smoke02/ : 二人の実推論結果
- work/camera_final_tests.log : 24件のテスト
- work/setup_camera_bat_validation.log : 実Setup BATのログ
- work/camera_environment.lock : 実インストール依存一覧
- C:/temp/walk_cam_move.fbx と C:/temp/run_movecam.fbx : 提供動画の隣の既存出力。走行は最新判定導入前の参考結果


## 過去の全長一括出力の判定（部分出力導入前）

上記の走行FBXは接続判定強化前の参考出力であり、現在のコードによる成功結果ではありません。既存ファイルは保持しています。

| 対象 | 最新結果 | 記録 |
|---|---|---|
| walk_cam_move.mp4 | 全273フレーム成功、FBX SDK再読込誤差0 | runs/camera_walk_checked |
| run_movecam.mp4 | 区間接続で停止。再投影中央値3.23px、90パーセンタイル10.84px、相対3D誤差0.101 | work/camera_run_gate.log |
| parkor.mp4 | 328フレーム、24fps。人物の短い追跡途切れを統合し、1人・観測率97.3%。LARGE、GIANTともカメラ区間接続で停止。FBX未出力 | work/camera_parkor_giant64_gate.log |

parkorはGIANTの64フレーム窓・24フレーム重複でも、40..103の窓接続で再投影中央値2.88px、90パーセンタイル11.34px、相対3D誤差0.227となり停止しました。通常BATの既定はLARGE・24フレーム窓のままです。最初が空中なので、この検証では初期両足接地補正を無効にしています。

接続判定は縮小画像上の中央値>3px、90パーセンタイル>30px、または90パーセンタイル>10pxかつ相対3D誤差>0.2の場合に停止します。これらは実験的な整合性判定であり、合格しても実軌跡の精度を保証しません。失敗を通すための閾値緩和は行いません。

DA3-GIANTも取得・SHA256検証済みです。公式モデル revision 7cd62ae9315b9dff094d2d300e4ad012640607dd、モデル本体5,422,814,644 bytes、SHA256 1e47a08338ca73a6d6a21d37fd060b26b993b672bc6ddf6295fe474df2592001。models/camera/DA3-GIANTに保持し、Git対象外です。

未解決：走行・parkorで安定した移動カメラ出力。次の改善候補は、静止背景の複数フレーム最適化、低視差時の回転・並進の分離、重力と接地制約です。原因を低視差と断定できる検証はまだなく、これらは未実装です。




## 現行仕様：全動画から成功した全区間を出力

最初の失敗で終了する先頭区間のみの方式を廃止しました。カメラ接続が失敗したら、保存済み区間を確定し、次の未採用フレームから独立したカメラ座標で再開します。独立窓でも背景幾何検証に失敗する場合は12フレーム窓へ縮め、1フレームずつ開始位置を進めて、後半の有効区間を探します。判定閾値は緩めません。

- 検証を通った連続区間をすべて別FBXへ出力。区間間は別の座標原点・推定尺度であり、空間的に連結しません。
- 各区間の最初でGeoCalibの重力を再推定します。レンズ補正と焦点距離は動画全体で固定した値を維持します。
- 全人物を同じ元動画フレーム範囲で推定します。ある区間の人体推定・尺度合わせ・出力が失敗しても、理由を記録して後の区間を処理します。
- 出力名は `動画名_frames_000072-000319_segment.fbx`。番号は0始まり・両端を含み、FBX時間は0から始まります。同名JSONに区間情報と精度警告を保存します。
- `動画名_segments.json` に全成功区間、カメラの除外範囲・失敗理由、人体段階の失敗を記録します。JSONのstart/endは半開区間 `[start,end)` です。
- 全長が一つの区間として完了した場合は従来の `動画名.fbx`。既存ファイルは上書きしません。
- 単独区間は人体モデルの制約で最低12フレーム必要です。接続できない短い末尾などは理由を付けて除外します。
- 判定通過は内部整合性の検証であり、人体姿勢やカメラの真値に対する精度保証ではありません。quality_warningsは区間ごとに残します。

### 実測（2026-09-07）

parkor.mp4 全328フレームを探索し、0..71（72フレーム）と72..319（248フレーム）の2区間、計320フレームを出力しました。末尾320..327は接続不整合後の独立区間が12フレーム未満のため除外。全FBXは89ボーン、24fps、SDK再読込の行列誤差0です。後半には推定上下範囲5.53m・最大ルート速度12.25m/sの精度確認警告があり、カメラ・人体のドリフトが解決したことを意味しません。

出力：C:/temp/parkor_frames_000000-000071_segment.fbx、C:/temp/parkor_frames_000072-000319_segment.fbx、C:/temp/parkor_segments.json。
実行記録：runs/drop/20260907_212003_06796646、work/parkor_all_segments.log。
旧partial.fbxは以前の参考出力として保持しています。

30テスト成功。合成不良フレームを除外し後半の全有効フレームを重複なく採用すること、想定外エラーを幾何失敗として隠さないこと、途中の人体区間失敗後も後続を処理すること、全成功区間と一覧の公開を検証しています。
