"""Build portable executable bằng PyInstaller."""
import subprocess
import sys
import os
import shutil


def build():
    print("=== Building portable executable ===")
    _verify_build_dependencies()

    # Clean previous build
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"Cleaned {d}/")

    # Run PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "build.spec",
        "--clean",
        "--noconfirm",
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print("BUILD FAILED!")
        sys.exit(1)

    # Check output
    exe_path = os.path.join("dist", "BaoCaoGiaoBan-VideoGenerator.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"BUILD SUCCESS: {exe_path} ({size_mb:.1f} MB)")
    else:
        print("WARNING: Executable not found at expected path")

    print("=== Build complete ===")


def _verify_build_dependencies():
    """Fail sớm nếu dependency runtime quan trọng chưa có trước khi PyInstaller collect."""
    required_modules = ["edge_tts", "aiohttp", "tabulate"]
    missing = []
    for module_name in required_modules:
        try:
            __import__(module_name)
        except ImportError as exc:
            missing.append(f"{module_name}: {exc}")

    if missing:
        print("BUILD FAILED: thiếu dependency để bundle TTS local.")
        for item in missing:
            print(f"  - {item}")
        print("Chạy: python -m pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    build()
