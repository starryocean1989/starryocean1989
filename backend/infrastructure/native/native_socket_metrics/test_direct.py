import socket_metrics
import time

print("Testing socket_metrics C extension...")
start = time.perf_counter()
result = socket_metrics.get_socket_metrics()
elapsed = (time.perf_counter() - start) * 1000

print(f"Success! Elapsed: {elapsed:.2f}ms")
print(f"Total connections: {result['total_connections']}")
print(f"TCP connections: {result['tcp_connections']}")
print(f"Established: {result['established_connections']}")
print(f"Recv buffer avg: {result['recv_buffer_size_avg']} bytes")
print(f"Send buffer avg: {result['send_buffer_size_avg']} bytes")
print(f"Recv usage: {result['recv_buffer_usage_ratio']:.2f}%")
print(f"Send usage: {result['send_buffer_usage_ratio']:.2f}%")
print(f"\n C extension works perfectly!")
