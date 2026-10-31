@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/3] Установка зависимостей...
python -m pip install -r requirements.txt pyinstaller || goto :err

echo [2/3] Сборка LayoutFix.exe...
python -m PyInstaller --noconfirm --clean LayoutFix.spec || goto :err

echo [3/3] Сборка установщика...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 не найден. Установите: winget install JRSoftware.InnoSetup
  echo Программа без установщика лежит в dist\LayoutFix\
  goto :end
)
"%ISCC%" installer.iss || goto :err

echo.
echo Готово: output\LayoutFix-Setup-*.exe
goto :end

:err
echo.
echo ОШИБКА сборки
exit /b 1

:end
pause
