@echo off
cd /d "%~dp0"

call .\.venv\Scripts\activate.bat

start "Hotel Retention API" cmd /k python main.py
start "Hotel Retention UI" cmd /k streamlit run app.py --server.port 8501 --server.address 0.0.0.0

exit
