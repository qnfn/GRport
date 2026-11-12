@echo off

setlocal EnableExtensions

rem Builds GRport's runtime from the patched source and installs it into a GRport folder, so a

rem change to runtime\grport-runtime.patch can be tried in the launcher.

rem

rem   build-runtime.bat "C:\path\to\GRport"

rem

rem Without the folder it only builds and prints where GRport-runtime.exe is. Overrides:

rem   GRPORT_DIR          the GRport folder (same as the first argument)

rem   GRPORT_RUNTIME_SRC  the source checkout (default: ..\grport-runtime beside this repository)

rem   MSYS2_ROOT          MSYS2's installation (default: C:\msys64)

rem

rem Needs MSYS2 (winget install MSYS2.MSYS2) with the CLANG64 packages listed in the runtime

rem source's packaging/windows/README.md, and about 1 GB of disk for the checkout.



set "HERE=%~dp0"

for %%I in ("%HERE%..") do set "REPO=%%~fI"

set "PATCH=%REPO%\runtime\grport-runtime.patch"

set "COMMIT=de2e38af055f09f819946951075c6bb119e62ae6"

rem Version 1.9.2 of github.com/Supermedo/bloodborne_pc: the tree grport-runtime.patch is made for.

set "SOURCE=https://github.com/Supermedo/bloodborne_pc"



if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"

if not defined GRPORT_RUNTIME_SRC set "GRPORT_RUNTIME_SRC=%REPO%\..\grport-runtime"

if not "%~1"=="" set "GRPORT_DIR=%~1"



if not exist "%PATCH%" (

    echo Could not find %PATCH% - run this script from a GRport checkout.

    exit /b 1

)

if not exist "%MSYS2_ROOT%\msys2_shell.cmd" (

    echo MSYS2 is not installed in "%MSYS2_ROOT%".

    echo Install it with:  winget install MSYS2.MSYS2

    echo Then, in the MSYS2 CLANG64 shell, install the packages listed in

    echo packaging\windows\README.md of %SOURCE% ^(toolchain, cmake, ninja, pkgconf,

    echo vulkan, sdl3, freetype2, fmt, boost, xxhash, openssl, ...^).

    exit /b 1

)



rem MSYS2's bash understands C:/folder/file paths, which saves converting them.

set "SRC=%GRPORT_RUNTIME_SRC%"

set "SRC=%SRC:\=/%"

set "PATCHNAME=%PATCH:\=/%"



rem One bash command: clone or reuse the source, put it at the patched commit, build it. A

rem checkout with changes of its own is never reset: delete it and this clones it again.

set "BASHCMD=if [ ! -d '%SRC%' ]; then git clone '%SOURCE%' '%SRC%'; fi"

set "BASHCMD=%BASHCMD% && cd '%SRC%' && git config core.autocrlf false"

set "BASHCMD=%BASHCMD% && { git cat-file -e '%COMMIT%^{commit}' 2>/dev/null || git fetch --depth 1 origin '%COMMIT%'; }"

set "BASHCMD=%BASHCMD% && { if git apply --reverse --check '%PATCHNAME%' 2>/dev/null; then echo 'grport-runtime.patch is already applied'; elif ! { git diff --quiet && git diff --cached --quiet; }; then echo 'error: %SRC% has changes of its own, so grport-runtime.patch cannot be applied.' >&2; echo '       Delete that folder and run this script again to clone a fresh one.' >&2; exit 1; else git reset --hard -q '%COMMIT%' && echo 'Reset %SRC% to the 1.9.2 commit'; fi; }"

set "BASHCMD=%BASHCMD% && git submodule update --init --recursive"

set "BASHCMD=%BASHCMD% && { git apply --reverse --check '%PATCHNAME%' 2>/dev/null || git apply --binary '%PATCHNAME%'; }"

set "BASHCMD=%BASHCMD% && bash build.sh && echo 'Built' '(%SRC%/out/bb-probe.exe)'"



echo Building GRport's runtime in "%GRPORT_RUNTIME_SRC%" ...

echo This takes a while the first time: the checkout is cloned and the renderer compiled.

"%MSYS2_ROOT%\msys2_shell.cmd" -defterm -no-start -clang64 -c "%BASHCMD%"

if errorlevel 1 (

    echo.

    echo The runtime did not build. See the messages above; the full log is

    echo "%GRPORT_RUNTIME_SRC%\out\gpu-build.log".

    exit /b 1

)



if not exist "%GRPORT_RUNTIME_SRC%\out\bb-probe.exe" (

    echo The build reported success but "%GRPORT_RUNTIME_SRC%\out\bb-probe.exe" is missing.

    exit /b 1

)



if not defined GRPORT_DIR (

    echo.

    echo Built "%GRPORT_RUNTIME_SRC%\out\bb-probe.exe".

    echo Run this script with the GRport folder to install it there:

    echo     "%~nx0" "C:\path\to\GRport"

    exit /b 0

)



if not exist "%GRPORT_DIR%\runtime" (

    echo "%GRPORT_DIR%" has no runtime folder: it is not a GRport folder.

    exit /b 1

)

if not exist "%GRPORT_DIR%\runtime\GRport-runtime.exe.bak" (

    if exist "%GRPORT_DIR%\runtime\GRport-runtime.exe" (

        copy /y "%GRPORT_DIR%\runtime\GRport-runtime.exe" "%GRPORT_DIR%\runtime\GRport-runtime.exe.bak" >nul

    )

)

copy /y "%GRPORT_RUNTIME_SRC%\out\bb-probe.exe" "%GRPORT_DIR%\runtime\GRport-runtime.exe" >nul

if errorlevel 1 (

    echo Could not write "%GRPORT_DIR%\runtime\GRport-runtime.exe". Is the game running?

    exit /b 1

)



echo.

echo Installed "%GRPORT_DIR%\runtime\GRport-runtime.exe" ^(the old one is kept as .bak^).

echo Start the launcher: it sees the new runtime and prepares each game once more before PLAY.

echo If Windows reports a missing DLL, copy the DLLs it names from "%MSYS2_ROOT%\clang64\bin".

exit /b 0

