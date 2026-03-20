import sys
import threading
import time
import socket
import uvicorn

USE_WEBVIEW = "--no-gui" not in sys.argv


def get_local_ip():
    """Get the machine's local network IP for phone access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_server(port):
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


def main():
    port = 8500

    local_ip = get_local_ip()
    print(f"\n  WatchWise is running!")
    print(f"  Local:   http://localhost:{port}")
    print(f"  Phone:   http://{local_ip}:{port}")
    print()

    if USE_WEBVIEW:
        # Start server in background thread
        server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
        server_thread.start()

        time.sleep(1.5)  # Wait for server to start

        import webview
        webview.create_window(
            "WatchWise",
            f"http://localhost:{port}",
            width=1200,
            height=800,
            min_size=(400, 600),
        )
        webview.start()
    else:
        run_server(port)


if __name__ == "__main__":
    main()
