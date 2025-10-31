import sys
sys.path.insert(0, '.')

try:
    from async_ipc import ipc_async, IPC_AVAILABLE
    print('IPC_AVAILABLE:', IPC_AVAILABLE)
    print('ipc_async:', ipc_async)
except ImportError as e:
    print('Import failed:', e)
    import traceback
    traceback.print_exc()
