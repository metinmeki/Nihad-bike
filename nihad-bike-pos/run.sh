#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt > /dev/null
( sleep 1 && python3 -c "import webbrowser; webbrowser.open('http://127.0.0.1:5000')" ) &
python3 app.py
