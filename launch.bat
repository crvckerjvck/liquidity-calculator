@echo off
cd /d "%~dp0"
echo Starting Liquidity Lounge Calculator...

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    echo Done.
)

call venv\Scripts\activate

echo Installing/updating dependencies...
pip install -r requirements.txt

echo Launching Streamlit app...
streamlit run app.py --server.headless true

pause
