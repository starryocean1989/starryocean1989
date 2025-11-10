# -*- coding: utf-8 -*-
"""
Type stubs for native_gil C extension
"""

from typing import Any, Optional

class ThreadSafeQueue:
    """Thread-safe queue implementation"""

    def __init__(self) -> None:
        """Initialize an empty thread-safe queue"""
        ...

    def empty(self) -> bool:
        """Check if the queue is empty

        Returns:
            True if queue is empty, False otherwise
        """
        ...

    def size(self) -> int:
        """Get the current size of the queue

        Returns:
            Number of items in the queue
        """
        ...

    def put(self, item: Any) -> None:
        """Put an item into the queue

        Args:
            item: The item to put into the queue
        """
        ...

    def get(self) -> Any:
        """Get an item from the queue

        Returns:
            The next item from the queue

        Raises:
            IndexError: If the queue is empty
        """
        ...

class ThreadSafeCounter:
    """Thread-safe counter implementation"""

    def __init__(self, initial_value: int = 0) -> None:
        """Initialize a thread-safe counter

        Args:
            initial_value: Initial value for the counter (default: 0)
        """
        ...

    def get(self) -> int:
        """Get the current value of the counter

        Returns:
            Current counter value
        """
        ...

    def increment(self, amount: int = 1) -> int:
        """Increment the counter by the specified amount

        Args:
            amount: Amount to increment by (default: 1)

        Returns:
            The new counter value after increment
        """
        ...

    def decrement(self, amount: int = 1) -> int:
        """Decrement the counter by the specified amount

        Args:
            amount: Amount to decrement by (default: 1)

        Returns:
            The new counter value after decrement
        """
        ...

    def set(self, value: int) -> None:
        """Set the counter to a specific value

        Args:
            value: The value to set
        """
        ...

# Other classes (placeholders for type checking)
class LockFreeQueue:
    def __init__(self) -> None: ...

class LockFreeHashMap:
    def __init__(self, capacity: int = 16) -> None: ...

    def set(self, key: Any, value: Any) -> None:
        """Set a key-value pair in the hash map.

        Args:
            key: The key to set
            value: The value to associate with the key
        """
        ...

    def get(self, key: Any) -> Any:
        """Get a value by key from the hash map.

        Args:
            key: The key to look up

        Returns:
            The value associated with the key, or None if not found
        """
        ...

    def remove(self, key: str) -> bool:
        """Remove a key-value pair from the hash map.

        Args:
            key: The key to remove

        Returns:
            True if the key was found and removed, False otherwise
        """
        ...

class HighPerfEvent:
    def __init__(self) -> None: ...
    def set(self) -> None: ...
    def clear(self) -> None: ...
    def is_set(self) -> bool: ...
    def wait(self, timeout_ms: Optional[int] = None) -> bool: ...

class HighPerfCondition:
    def __init__(self) -> None: ...

# Functions
def release_gil() -> None: ...
def restore_gil() -> None: ...
def execute_cpu_task() -> None: ...
