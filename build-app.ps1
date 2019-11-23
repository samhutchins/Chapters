pyinstaller `
    --clean `
    --log-level=WARN `
    --noconfirm `
    --windowed `
    --name="Chapters" `
    --add-binary="src\lib\lame.exe;lib" `
    --add-data="LICENSE;." `
    --add-data="COPYING;." `
    src\chapters_gui.py