@echo off
echo.
echo =====================================================
echo   Earth Agent -- LLM + ArrayDBMS Live Run
echo   Model  : qwen2.5:7b via Ollama
echo   DBMS   : 13,398 raster datasets
echo =====================================================
echo.
echo  Connecting to Ollama and starting agent...
echo  (this takes ~60-90 seconds)
echo.
"C:\Users\shehz\AppData\Local\Programs\Python\Python313\python.exe" "%~dp0run_ollama_agent.py"
echo.
pause
