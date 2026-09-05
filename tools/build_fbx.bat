@echo off
setlocal
cd /d "%~dp0.."
if not defined UE_ROOT set "UE_ROOT=D:\UE\UE_5.8"
set "FBX_ROOT=%UE_ROOT%\Engine\Source\ThirdParty\FBX\2020.2"
if not defined VS_VCVARS set "VS_VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VS_VCVARS%" exit /b 1
call "%VS_VCVARS%" >nul
if errorlevel 1 exit /b 1
if not exist bin mkdir bin
if not exist work mkdir work
cl /nologo /EHsc /O2 /MD /std:c++17 /DFBXSDK_SHARED /I"%FBX_ROOT%\include" native\fbx_export.cpp /Fo:work\fbx_export.obj /Fe:bin\fbx_export.exe /link "%FBX_ROOT%\lib\vs2017\x64\release\libfbxsdk.lib"
if errorlevel 1 exit /b 1
copy /y "%UE_ROOT%\Engine\Binaries\ThirdParty\FBX\2020.2\Win64\libfbxsdk.dll" bin\ >nul
exit /b %errorlevel%
