import httpx

BASE = "https://net1c.ru/api/v1"

# Test registration
r = httpx.post(f"{BASE}/auth/register", json={
    "email": "testadmin123@net1c.ru",
    "password": "testpass123",
    "full_name": "Admin Test",
}, timeout=15)
print("Register:", r.status_code, r.text[:500])
