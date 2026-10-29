@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/3] 检查 Python 与 tkinter ...
where python >nul 2>nul
if errorlevel 1 (
    echo    未找到 python，请先安装官方 Python 3.9+ 并勾选 tcl/tk。
    pause & exit /b 1
)
python -c "import tkinter" 2>nul
if errorlevel 1 (
    echo    当前 Python 缺少 tkinter，请安装 python.org 官方发行版。
    pause & exit /b 1
)

echo [2/3] 安装 / 升级 PyInstaller ...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo    安装失败，请检查网络或 pip 源。
    pause & exit /b 1
)

echo [3/3] 打包单文件 exe ...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ClassBell ^
    --icon "%~dp0assets\icon.ico" ^
    --add-data "%~dp0assets;assets" ^
    --workpath "%~dp0build" ^
    --distpath "%~dp0dist" ^
    --specpath "%~dp0build" ^
    "%~dp0main.py"
if errorlevel 1 (
    echo    打包失败，请查看上方日志。
    pause & exit /b 1
)

echo.
echo 打包完成：%~dp0dist\ClassBell.exe
pause
