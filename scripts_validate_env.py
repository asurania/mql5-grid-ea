import json
import time
import platform
import importlib

mods = ['torch','numpy','pandas','polars','pyarrow','sklearn','xgboost','matplotlib','seaborn','orjson','pydantic','zmq','httpx']
report = {
    'platform': platform.platform(),
    'modules': {},
    'benchmarks': {}
}
for m in mods:
    try:
        mod = importlib.import_module(m)
        report['modules'][m] = {'ok': True, 'version': getattr(mod, '__version__', 'unknown')}
    except Exception as e:
        report['modules'][m] = {'ok': False, 'error': repr(e)}

import torch
report['torch'] = {
    'version': torch.__version__,
    'hip': getattr(torch.version, 'hip', None),
    'cuda_available': torch.cuda.is_available(),
    'device_count': torch.cuda.device_count(),
}
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    report['torch']['device_0'] = {
        'name': props.name,
        'total_memory_gb': round(props.total_memory / (1024**3), 2),
        'gcnArchName': getattr(props, 'gcnArchName', None),
        'multi_processor_count': getattr(props, 'multi_processor_count', None),
    }
    torch.set_float32_matmul_precision('high')
    sizes = [2048, 4096, 6144]
    gpu_runs = []
    for n in sizes:
        x = torch.randn((n, n), device='cuda', dtype=torch.float32)
        y = torch.randn((n, n), device='cuda', dtype=torch.float32)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        z = x @ y
        torch.cuda.synchronize()
        dt = time.perf_counter() - t0
        gpu_runs.append({
            'size': n,
            'seconds': round(dt, 4),
            'tflops_est': round((2 * (n ** 3)) / dt / 1e12, 3),
            'mean': float(z.mean().item()),
        })
        del x, y, z
    report['benchmarks']['gpu_matmul_fp32'] = gpu_runs

    cpu_n = 2048
    a = torch.randn((cpu_n, cpu_n), device='cpu', dtype=torch.float32)
    b = torch.randn((cpu_n, cpu_n), device='cpu', dtype=torch.float32)
    t0 = time.perf_counter()
    c = a @ b
    dt = time.perf_counter() - t0
    report['benchmarks']['cpu_matmul_fp32'] = {
        'size': cpu_n,
        'seconds': round(dt, 4),
        'tflops_est': round((2 * (cpu_n ** 3)) / dt / 1e12, 3),
        'mean': float(c.mean().item()),
    }

print(json.dumps(report, indent=2))
