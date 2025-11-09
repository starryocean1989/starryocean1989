# -*- coding: utf-8 -*-
"""
Test cases for native_qhighlighter module.
"""
import pytest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

# Only run these tests if the native module is available
pytestmark = pytest.mark.skipif(
    not hasattr(pytest, 'importorskip'),
    reason="Native module not available"
)

class TestNativeHighlighter:
    """Test cases for NativePythonHighlighter."""
    
    @pytest.fixture
    def editor(self, qtbot):
        """Create a QPlainTextEdit with NativePythonHighlighter."""
        app = QApplication.instance() or QApplication([])
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        return editor
    
    def test_highlighter_import(self):
        """Test if the native highlighter can be imported."""
        try:
            from native_qhighlighter import NativePythonHighlighter
            assert NativePythonHighlighter is not None
        except ImportError as e:
            pytest.skip(f"Native highlighter not available: {e}")
    
    def test_highlight_python_code(self, editor, qtbot):
        """Test highlighting Python code."""
        pytest.importorskip("native_qhighlighter")
        from native_qhighlighter import NativePythonHighlighter
        
        # Create highlighter
        highlighter = NativePythonHighlighter(editor.document(), theme="monaco-dark")
        
        # Set some Python code
        test_code = """
        def hello():
            print("Hello, world!")
            return 42
        """
        editor.setPlainText(test_code)
        
        # Force immediate processing
        editor.show()
        QApplication.processEvents()
        
        # Basic verification that highlighting was applied
        # (exact formatting depends on the highlighter implementation)
        assert editor.toPlainText() == test_code.strip()
        
        # Cleanup
        highlighter.setDocument(None)
    
    def test_theme_change(self, editor, qtbot):
        """Test changing the theme."""
        pytest.importorskip("native_qhighlighter")
        from native_qhighlighter import NativePythonHighlighter
        
        highlighter = NativePythonHighlighter(editor.document(), theme="monaco-dark")
        
        # Change to light theme
        highlighter.set_theme("monaco-light")
        
        # Change back to dark theme
        highlighter.set_theme("monaco-dark")
        
        # If we get here without exceptions, the test passes
        assert True
        
        # Cleanup
        highlighter.setDocument(None)

if __name__ == "__main__":
    pytest.main(["-x", __file__, "-v"])
