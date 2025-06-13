from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    print("✅ Ping received at /")
    return "I'm alive!"

def run():
    print("🚀 Web server started at http://0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    print("🛡️ Starting keep_alive thread...")
    t = Thread(target=run)
    t.start()
