@echo off
cd /d C:\Users\USER\Desktop\terminal_v0.50
echo ========================================
echo Testing Monitor System
echo ========================================
echo.
echo Step 1: Testing Python
python --version
echo.
echo Step 2: Testing import
python -c "print('Python is working'); import sys; sys.path.insert(0, '.'); from backend.infrastructure.system_vnpy import monitor_system; print('Import successful')"
echo.
echo Step 3: Running monitor_system.py
python backend\infrastructure\system_vnpy\monitor_system.py
echo.
echo ========================================
echo Test Complete
echo ========================================
pause
