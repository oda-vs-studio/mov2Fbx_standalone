"""Small native launcher; inference runs in a separate, cancellable process."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

ROOT = Path(__file__).resolve().parent.parent


class App:
    def __init__(self, window):
        self.window = window
        window.title('Movie2Anim — Standalone verification tool')
        window.geometry('900x690')
        window.minsize(760,600)
        self.process = None
        self.events = queue.Queue()
        self.last_output = None
        self.cancelled = False
        frame = ttk.Frame(window,padding=22)
        frame.pack(fill='both',expand=True)
        frame.columnconfigure(1,weight=1)
        ttk.Label(frame,text='Movie2Anim / Standalone',font=('Segoe UI',21,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
        ttk.Label(frame,text='Local ONNX inference · SMPL-X 55 bones · FBX / BVH / 3D preview').grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,20))
        self.video = tk.StringVar()
        self.output = tk.StringVar(value=str(ROOT/'runs'/'capture'))
        self.start = tk.StringVar(value='0')
        self.end = tk.StringVar(value='119')
        self.roi = tk.StringVar()
        self.roi2 = tk.StringVar()
        self.rotation = tk.StringVar(value='0')
        self.provider = tk.StringVar(value='dml')
        self.info = tk.StringVar(value='Choose a video. For the first test, use a short range with one person visible.')
        self.fields = []
        for row,label,var,callback in [(2,'Video',self.video,self.choose_video),(3,'Output folder',self.output,self.choose_output)]:
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',padx=(0,16),pady=5)
            entry = ttk.Entry(frame,textvariable=var)
            entry.grid(row=row,column=1,sticky='ew',pady=5)
            button = ttk.Button(frame,text='Browse…',command=callback)
            button.grid(row=row,column=2,padx=(8,0))
            self.fields.extend([entry,button])
        controls = ttk.Frame(frame)
        controls.grid(row=4,column=0,columnspan=3,sticky='ew',pady=10)
        for label,var,width in [('Start F',self.start,8),('End F (inclusive)',self.end,8)]:
            ttk.Label(controls,text=label).pack(side='left',padx=(0,6))
            entry = ttk.Entry(controls,textvariable=var,width=width)
            entry.pack(side='left',padx=(0,18))
            self.fields.append(entry)
        for label,var,values in [('Rotation',self.rotation,['0','90','180','270']),('Device',self.provider,['cpu','dml'])]:
            ttk.Label(controls,text=label).pack(side='left',padx=(0,6))
            combo = ttk.Combobox(controls,textvariable=var,values=values,state='readonly',width=7)
            combo.pack(side='left',padx=(0,15))
            self.fields.append(combo)
        ttk.Label(frame,text='Person ROI').grid(row=5,column=0,sticky='w')
        entry = ttk.Entry(frame,textvariable=self.roi)
        entry.grid(row=5,column=1,sticky='ew')
        button = ttk.Button(frame,text='Select in video',command=self.select_roi)
        button.grid(row=5,column=2,padx=(8,0))
        self.fields.extend([entry,button])
        ttk.Label(frame,text='Optional: x0 y0 x1 y1 in rotated preview pixels. Blank uses the full image.').grid(row=6,column=1,columnspan=2,sticky='w',pady=(4,12))
        ttk.Label(frame,text='Second person ROI').grid(row=7,column=0,sticky='w')
        entry2 = ttk.Entry(frame,textvariable=self.roi2)
        entry2.grid(row=7,column=1,sticky='ew',pady=(0,10))
        button2 = ttk.Button(frame,text='Select person 2',command=lambda:self.select_roi(self.roi2))
        button2.grid(row=7,column=2,padx=(8,0),pady=(0,10))
        self.fields.extend([entry2,button2])
        ttk.Label(frame,textvariable=self.info,wraplength=800).grid(row=8,column=0,columnspan=3,sticky='w',pady=(0,12))
        buttons = ttk.Frame(frame)
        buttons.grid(row=9,column=0,columnspan=3,sticky='w')
        self.run = ttk.Button(buttons,text='Analyze + export',command=self.begin)
        self.run.pack(side='left',padx=(0,10))
        self.stop = ttk.Button(buttons,text='Cancel',command=self.cancel,state='disabled')
        self.stop.pack(side='left',padx=(0,10))
        self.preview = ttk.Button(buttons,text='Open 3D preview',command=self.open_preview,state='disabled')
        self.preview.pack(side='left',padx=(0,10))
        self.folder = ttk.Button(buttons,text='Open output',command=lambda:os.startfile(self.last_output),state='disabled')
        self.folder.pack(side='left')
        self.log = tk.Text(frame,height=17,wrap='word',bg='#101622',fg='#d5e3f7',font=('Consolas',10),state='disabled')
        self.log.grid(row=10,column=0,columnspan=3,sticky='nsew',pady=(14,10))
        frame.rowconfigure(10,weight=1)
        ttk.Label(frame,text='Prototype: static ROIs · no foot-lock optimizer / Manny retargeting. Person 2 blank = single-person mode.',wraplength=800).grid(row=11,column=0,columnspan=3,sticky='w')
        window.protocol('WM_DELETE_WINDOW',self.close)
        window.after(100,self.poll)

    def choose_video(self):
        path = filedialog.askopenfilename(filetypes=[('Video','*.mp4 *.mov *.avi *.mkv *.webm'),('All','*.*')])
        if not path:
            return
        import cv2
        cap = cv2.VideoCapture(path)
        count,fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        self.video.set(path)
        self.start.set('0')
        self.end.set(str(min(119,max(0,count-1))))
        self.roi.set('')
        self.roi2.set('')
        self.info.set(f'{count} frames · {fps:.3f} fps. Start with 16–120 frames; CPU processing may take several minutes.')

    def choose_output(self):
        parent = filedialog.askdirectory(title='Choose parent folder (a new capture subfolder will be created)')
        if parent:
            self.output.set(str(Path(parent)/'capture'))

    def select_roi(self,target=None):
        try:
            import cv2
            from .pipeline import read_frames
            frames,_ = read_frames(self.video.get(),int(self.start.get()),int(self.start.get()),int(self.rotation.get()))
            x,y,w,h = cv2.selectROI('Person ROI — Enter to accept / Esc to cancel',frames[0],fromCenter=False,showCrosshair=True)
            cv2.destroyAllWindows()
            if w and h:
                (target if target is not None else self.roi).set(f'{x} {y} {x+w} {y+h}')
        except Exception as e:
            messagebox.showerror('ROI selection',str(e))

    def begin(self):
        try:
            start,end = int(self.start.get()),int(self.end.get())
            if end-start+1 < 12 or start < 0:
                raise ValueError('Choose at least 12 frames with a nonnegative start.')
            if not Path(self.video.get()).is_file():
                raise ValueError('Choose an existing video.')
            output = Path(self.output.get()).resolve()
            if output.exists():
                raise ValueError('Choose a new output folder name; existing results are kept.')
            args = [sys.executable,'-u','-m','m2a','solve',self.video.get(),'--output',str(output),'--start',str(start),'--end',str(end),'--rotation',self.rotation.get(),'--provider',self.provider.get()]
            if self.roi.get().strip():
                roi = [float(v) for v in self.roi.get().replace(',',' ').split()]
                if len(roi) != 4:
                    raise ValueError('ROI requires x0 y0 x1 y1.')
                args += ['--roi',*map(str,roi)]
            if self.roi2.get().strip():
                roi2 = [float(v) for v in self.roi2.get().replace(',',' ').split()]
                if len(roi2) != 4 or not self.roi.get().strip():
                    raise ValueError('Two-person mode requires both person ROIs.')
                args += ['--roi2',*map(str,roi2)]
            self.cancelled = False
            self.last_output = str(output)
            self.process = subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.set_running(True)
            def collect():
                for line in self.process.stdout:
                    self.events.put(('line',line.replace('\x00','')))
                self.events.put(('exit',self.process.wait()))
            threading.Thread(target=collect,daemon=True).start()
        except Exception as e:
            messagebox.showerror('Cannot start',str(e))

    def set_running(self,running):
        for widget in self.fields:
            widget.configure(state='disabled' if running else ('readonly' if isinstance(widget,ttk.Combobox) else 'normal'))
        self.run.configure(state='disabled' if running else 'normal')
        self.stop.configure(state='normal' if running else 'disabled')
        self.preview.configure(state='disabled')
        self.folder.configure(state='disabled')

    def poll(self):
        while not self.events.empty():
            kind,value = self.events.get_nowait()
            if kind == 'line':
                self.log.configure(state='normal')
                self.log.insert('end',value)
                self.log.see('end')
                self.log.configure(state='disabled')
            else:
                self.process = None
                self.set_running(False)
                success = value == 0 and (Path(self.last_output)/'SUCCESS').exists()
                self.info.set('Completed. Open the 3D preview or FBX output.' if success else ('Cancelled. Partial files remain in the output folder.' if self.cancelled else 'Failed. Details are shown in the log; choose a new output name to retry.'))
                if success:
                    self.preview.configure(state='normal')
                if Path(self.last_output).exists():
                    self.folder.configure(state='normal')
        self.window.after(100,self.poll)

    def cancel(self):
        if self.process and self.process.poll() is None:
            self.cancelled = True
            self.process.terminate()

    def open_preview(self):
        webbrowser.open((Path(self.last_output)/'preview.html').as_uri())

    def close(self):
        self.cancel()
        self.window.destroy()


def main():
    window = tk.Tk()
    App(window)
    window.mainloop()
