import argparse
import json
from pathlib import Path
from .pipeline import solve


def main():
    parser = argparse.ArgumentParser(description='Movie2Anim standalone — local ONNX body capture')
    commands = parser.add_subparsers(dest='command',required=True)
    p = commands.add_parser('solve')
    p.add_argument('video',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--models',type=Path,default=Path('models'))
    p.add_argument('--start',type=int,default=0)
    p.add_argument('--end',type=int)
    p.add_argument('--rotation',type=int,choices=[0,90,180,270],default=0)
    p.add_argument('--roi',type=float,nargs=4,metavar=('X0','Y0','X1','Y1'))
    p.add_argument('--roi2',type=float,nargs=4,help='Second person ROI; writes two independent animations')
    p.add_argument('--provider',choices=['cpu','dml'],default='cpu')
    p.add_argument('--focal',type=float)
    p.add_argument('--height',type=float,default=0)
    p.add_argument('--seed',type=int,default=42)
    commands.add_parser('gui')
    commands.add_parser('doctor')
    p = commands.add_parser('export')
    p.add_argument('output',type=Path)
    p.add_argument('--models',type=Path,default=Path('models'))
    args = vars(parser.parse_args())
    command = args.pop('command')
    if command == 'gui':
        from .gui import main as gui
        gui()
    elif command == 'doctor':
        import sys, onnxruntime
        print(json.dumps(dict(python=sys.executable,onnxruntime=onnxruntime.__version__,providers=onnxruntime.get_available_providers(),models={p.name:p.stat().st_size for p in Path('models').glob('*') if p.is_file()}),indent=2))
    elif command == 'export':
        from .export import export_motion
        export_motion(**args)
    else:
        roi2 = args.pop('roi2')
        if roi2 is not None:
            from .pipeline import solve_two
            solve_two(roi2,**args,log=lambda s:print(s,flush=True))
            return
        output = solve(**args,log=lambda s:print(s,flush=True))
        from .export import export_motion
        export_motion(output,args['models'])


if __name__ == '__main__':
    main()
