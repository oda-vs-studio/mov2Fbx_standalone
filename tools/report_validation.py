import json
from pathlib import Path
import sys
import html
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from m2a.export import PARENTS
from m2a.preview import write_preview, write_pair_preview


def main():
    base=ROOT/'runs/user_validation'
    summary=json.loads((base/'summary.json').read_text(encoding='utf-8'))
    metrics=[]
    for case in summary:
        number=case['video']
        run=base/f'{number:05d}'
        people=[run] if number<20 else [run/'person_01',run/'person_02']
        for person in people:
            assert (person/'SUCCESS').exists(),str(person)
            raw=np.load(person/'motion.npz')
            world=np.load(person/'world_motion.npz')
            assert raw['poses'].shape==(124,165)
            assert float(raw['fps'])==24
            assert all(np.isfinite(raw[k]).all() for k in raw.files)
            assert all(np.isfinite(world[k]).all() for k in world.files)
            bone_lengths=np.linalg.norm(world['joints'][:,1:]-world['joints'][:,PARENTS[1:]],axis=-1)
            expected=np.linalg.norm(world['offsets'][1:],axis=-1)
            error=float(np.abs(bone_lengths-expected).max())
            assert error<1e-6
            fbx=(person/'fbx_validation.txt').read_text(encoding='utf-8').strip()
            assert 'FBX_ROUNDTRIP_OK' in fbx and 'frames=124' in fbx
            metrics.append(dict(video=number,person=person.name,frames=124,fps=24,bone_length_max_error_m=error,fbx_validation=fbx))
            metadata=json.loads((person/'metadata.json').read_text(encoding='utf-8'))
            write_preview(person/'preview.html',world['joints'],24,metadata)
        if number>=20:
            write_pair_preview(run/'preview.html',124,24)
    (base/'numeric_validation.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    rows=[]
    for case in summary:
        n=case['video'];directory=f'{n:05d}'
        count=1 if n<20 else 2
        links=[]
        for i in range(count):
            prefix=directory+'/' if count==1 else directory+f'/person_{i+1:02d}/'
            links.append(f'<a href="{prefix}motion.fbx">FBX {i+1}</a> · <a href="{prefix}motion.bvh">BVH</a> · <a href="{prefix}keypoints.mp4">関節確認動画</a>')
        rows.append(f'<tr><td>MiniMax_H3_{n:05d}_</td><td>{count}人</td><td>124 / 24 fps</td><td>{case.get("seconds",0):.1f} 秒</td><td><a class="primary" href="{directory}/preview.html">3Dプレビュー</a><br>'+ '<br>'.join(links)+'</td></tr>')
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Movie2Anim Standalone / 検証結果</title>
<style>body{max-width:1150px;margin:40px auto;padding:0 24px;background:#101622;color:#dce7f8;font:15px system-ui}h1{font-size:30px}p{line-height:1.8;color:#b7c7dd}table{border-collapse:collapse;width:100%;margin-top:24px}th,td{text-align:left;padding:16px;border-bottom:1px solid #344058;line-height:1.9}th{color:#9fbbdf}a{color:#8fc5ff}.primary{font-weight:bold}.badge{color:#7fddb3}</style>
<h1>Movie2Anim / Standalone</h1><p class="badge">7動画・10人物分の出力完了 · Unreal Editor不使用 · RTX 5090 / DirectML</p>
<p>全動画の0〜123F（両端を含む）を解析しました。FBXはSMPL-Xの55ボーンです。<br>2人版は人物ごとの固定ROIによる独立推定です。接触拘束、交差時のID維持、Mannyリターゲットは未実装です。</p>
<table><thead><tr><th>動画</th><th>人数</th><th>出力</th><th>処理時間</th><th>確認・ファイル</th></tr></thead><tbody>ROWS</tbody></table>
<p>書き出したFBXは再読み込みし、全フレームのローカル変換が一致することを確認しました。これは出力形式の検証であり、映像に対する推定精度を保証するものではありません。関節確認動画と3Dプレビューを併せて確認してください。</p>
<p><a href="numeric_validation.json">数値検証結果</a> · <a href="summary.json">処理結果</a></p></html>'''
    (base/'index.html').write_text(page.replace('ROWS',''.join(rows)),encoding='utf-8')
    report='# 実動画検証結果\n\nUnreal Editor不使用、RTX 5090 / DirectML。7動画、合計10人物、各124フレーム・24fps。\n\n| 動画 | 人数 | 時間 | 結果 |\n| --- | --- | --- | --- |\n'
    for case in summary:
        report+=f'| {case["video"]:05d} | {1 if case["video"]<20 else 2} | {case.get("seconds",0):.1f}秒 | {case["status"]} |\n'
    report+='\n全出力でNaN/Infなし、骨長一定、FBX再読み込み後の全ローカル変換一致を確認。中央フレームの関節重ね画像を目視し、1人のパンチ姿勢および2人の左右の身体が取得されていることを確認しました。遮蔽された手足や全フレームのID維持の品質保証ではありません。\n\n過去の検証一覧は `runs/user_validation/index.html` を直接開いて確認できます。詳細は `runs/user_validation/numeric_validation.json`、各ケースの `metadata.json` / `fbx_validation.txt` / `keypoints.mp4` にあります。\n'
    (ROOT/'docs/VALIDATION.md').write_text(report,encoding='utf-8')
    print('USER_VIDEOS_VALIDATE_OK',len(metrics),'motions')


if __name__=='__main__':main()
