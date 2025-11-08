try:
    from ._native_calendar import NativeCalendar
except ImportError as e:
    raise ImportError(
        "Failed to import the compiled `native_calendar` module. "
        "Please make sure the project is installed correctly (e.g., by running `pip install .`)"
    ) from e