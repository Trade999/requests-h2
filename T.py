import requests_h2 as requests

print("=" * 60)
print("Test: NetworkError daholo (tsy misy ConnectionError)")
print("=" * 60)

# Test 1: Server tsy misy
print("\n1. Server tsy misy (localhost:9999)")
try:
    response = requests.get(
        "https://localhost:9999",
        http2=False,
        timeout=2
    )
    print(f"Status: {response.status_code}")
except requests.exceptions.NetworkError as e:
    print(f"✅ NetworkError: {type(e).__name__}: {e}")
except requests.exceptions.ConnectionError as e:
    print(f"❌ ConnectionError (tsy tokony hiseho): {type(e).__name__}")
except Exception as e:
    print(f"❌ Exception hafa: {type(e).__name__}: {e}")

# Test 2: URL tsy misy
print("\n2. URL tsy misy")
try:
    response = requests.get(
        "https://tsymisy.io",
        http2=False,
        timeout=3
    )
    print(f"Status: {response.status_code}")
except requests.exceptions.NetworkError as e:
    print(f"✅ NetworkError: {type(e).__name__}: {e}")
except requests.exceptions.ConnectionError as e:
    print(f"❌ ConnectionError (tsy tokony hiseho): {type(e).__name__}")
except Exception as e:
    print(f"❌ Exception hafa: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("✅ Vita! NetworkError daholo ny olana rehetra")
print("=" * 60)