import sys
sys.path.insert(0, '.')

try:
    from ipc_loop import ipc_async, IPC_AVAILABLE
    print('From ipc_loop - IPC_AVAILABLE:', IPC_AVAILABLE)
    print('From ipc_loop - ipc_async:', ipc_async)
except ImportError as e:
    print('ipc_loop Import failed:', e)
    import traceback
    traceback.print_exc()

print("\n---\n")

try:
    import ipc_async as direct_ipc
    print('Direct import - ipc_async:', direct_ipc)
except ImportError as e:
    print('Direct import failed:', e)
    import traceback
    traceback.print_exc()
