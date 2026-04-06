import http.server
import socketserver
import os

PORT = 8000
DIRECTORY = "./"

os.chdir(DIRECTORY)
Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving HTTP on http://localhost:{PORT} from {DIRECTORY}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()