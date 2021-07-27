@echo off

if exist stroll.exe (
    :: This is a built version of stroll, so executable can be launched directly
    stroll.exe %1 :: Pass the --startup argument to the executable
) else (
    :: This is a source version of stroll, so python script must be launched
    :: NOTE: the venv used has to be named env and be in the root folder for this to work
    env\Scripts\python.exe src\stroll.py %1
)