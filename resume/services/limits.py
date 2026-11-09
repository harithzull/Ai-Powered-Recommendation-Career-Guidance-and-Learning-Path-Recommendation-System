"""OS resource boundaries; failure must prevent untrusted parsing."""
import os
from resume.constants import WORKER_CPU_SECONDS, WORKER_MEMORY_BYTES


def posix_limits():
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY_BYTES, WORKER_MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (WORKER_CPU_SECONDS, WORKER_CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def windows_job(process):
    if os.name != 'nt':
        return lambda: None
    import ctypes
    from ctypes import wintypes
    size = ctypes.c_size_t
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
            ('flags', wintypes.DWORD), ('minimum', size), ('maximum', size),
            ('active', wintypes.DWORD), ('affinity', size), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', size), ('job_memory', size), ('peak_process', size), ('peak_job', size)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise OSError('Worker resource isolation unavailable')
    limits = Extended()
    limits.basic.flags = 0x2 | 0x8 | 0x100 | 0x200 | 0x2000
    limits.basic.process_time = WORKER_CPU_SECONDS*10_000_000
    limits.basic.active = 2  # Windows venv launcher plus its interpreter.
    limits.process_memory = WORKER_MEMORY_BYTES
    limits.job_memory = WORKER_MEMORY_BYTES
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
        kernel.CloseHandle(handle)
        raise OSError('Worker resource isolation unavailable')
    return lambda: kernel.CloseHandle(handle)
