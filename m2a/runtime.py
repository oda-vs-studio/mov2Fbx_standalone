from pathlib import Path
import numpy as np
import onnxruntime as ort


class Model:
    def __init__(self, root, name, provider='cpu', frames=None):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 8
        options.inter_op_num_threads = 1
        options.enable_mem_pattern = False
        options.log_severity_level = 3
        if frames is not None:
            options.add_free_dimension_override_by_name('frames', frames)
        providers = ['CPUExecutionProvider']
        if provider == 'dml':
            if 'DmlExecutionProvider' not in ort.get_available_providers():
                raise RuntimeError('DirectML unavailable; install onnxruntime-directml or choose CPU')
            providers.insert(0, 'DmlExecutionProvider')
        self.session = ort.InferenceSession(str(Path(root) / (name + '.onnx')), sess_options=options, providers=providers)
        self.inputs = self.session.get_inputs()

    def __call__(self, *values):
        if len(values) != len(self.inputs):
            raise ValueError('Model input count mismatch')
        feed = {}
        for spec, value in zip(self.inputs, values):
            dtype = np.int64 if spec.type == 'tensor(int64)' else np.float32
            array = np.asarray(value, dtype=dtype)
            feed[spec.name] = array if array.ndim == 0 else np.ascontiguousarray(array)
        output = self.session.run(None, feed)
        if any(not np.isfinite(x).all() for x in output):
            raise RuntimeError('Model returned NaN/Inf; no motion exported')
        return output
