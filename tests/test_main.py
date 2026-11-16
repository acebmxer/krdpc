import os
import signal
import subprocess
import sys
import time


def test_ctrl_c_quits_the_running_app(tmp_path):
    env = {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "XDG_CONFIG_HOME": str(tmp_path),
        "PYTHONPATH": "src",
    }
    app = subprocess.Popen(
        [sys.executable, "-m", "krdpc"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)  # let it open its window
        assert app.poll() is None
        app.send_signal(signal.SIGINT)
        assert app.wait(timeout=5) == 0
    finally:
        if app.poll() is None:
            app.kill()
