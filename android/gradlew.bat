@echo off
setlocal
set DIR=%~dp0
if defined JAVA_HOME (
    set JAVA_EXE=%JAVA_HOME%\bin\java.exe
) else (
    set JAVA_EXE=java.exe
)
set CLASSPATH=%DIR%gradle\wrapper\gradle-wrapper.jar
"%JAVA_EXE%" -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %*
endlocal