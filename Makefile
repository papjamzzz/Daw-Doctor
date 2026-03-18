.PHONY: setup run install

setup:
	python3 -m venv venv
	venv/bin/pip install -q -r requirements.txt
	@echo "✅ DAW Doctor ready — run: make run"

run:
	venv/bin/python app.py

install:
	@echo "Installing DAW Doctor to /Applications..."
	@cp -r "DAW Doctor.app" /Applications/ 2>/dev/null || echo "Build .app first"
