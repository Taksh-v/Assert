import time

def try_import(name):
    t0 = time.time()
    print(f"Importing {name}...")
    try:
        __import__(name)
        print(f"  Loaded {name} in {time.time()-t0:.4f}s")
    except Exception as e:
        print(f"  Failed to load {name}: {e}")

try_import("click")
try_import("fastuuid")
try_import("httpx")
try_import("importlib_metadata")
try_import("jinja2")
try_import("jsonschema")
try_import("openai")
try_import("pydantic")
try_import("python-dotenv")
try_import("tiktoken")
try_import("tokenizers")
try_import("aiohttp")
print("All deps checked!")
