# -*- coding: utf-8 -*-
# native_qhighlighter

高性能 Python 代码高亮扩展，使用 C++ 正则批量 token 化，结合 PySide6 `QSyntaxHighlighter`
实现快速渲染。默认主题为 `monaco-dark`，并提供 `set_theme()` 接口支持自定义主题。

## 依赖

- Python 3.10+
- PySide6
- pybind11
- 可选：MSVC (Windows) / clang 或 gcc (Linux) 编译器

## 构建

```powershell
cd ui/native_extensions/native_qhighlighter
python setup.py build_ext --inplace
```

构建成功后将生成 `native_qhighlighter_core.pyd` (Windows) 或 `.so` 文件，可被
`NativePythonHighlighter` 自动加载。

## 使用

```python
from native_qhighlighter import NativePythonHighlighter

editor = QPlainTextEdit()
highlighter = NativePythonHighlighter(editor.document(), theme="monaco-dark")
```

设置主题：

```python
highlighter.set_theme("monaco-dark")
```

在扩展不可用时，模块会抛出 `NativeHighlighterUnavailable`，外部可捕获并回退至 Python
实现，同时在日志中记录原因。


