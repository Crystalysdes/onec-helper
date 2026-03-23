import subprocess, sys, re, threading

url_found = None

def read_output(proc):
    global url_found
    for line in proc.stderr:
        match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', line)
        if match:
            url_found = match.group(0)
            print(f"TUNNEL_URL={url_found}", flush=True)
            break

proc = subprocess.Popen(
    [r"C:\Program Files (x86)\cloudflared\cloudflared.exe", "tunnel", "--url", "http://localhost:3000"],
    stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    text=True, encoding="utf-8", errors="replace",
)

t = threading.Thread(target=read_output, args=(proc,), daemon=True)
t.start()
t.join(timeout=25)

if url_found:
    sys.exit(0)
else:
    print("URL_NOT_FOUND", flush=True)
    proc.terminate()
    sys.exit(1)
