import asyncio, httpx

async def test():
    proxy = 'socks5://user153520:zrsqka@93.127.149.199:13875'
    print(f'Testing proxy: {proxy}')
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=15) as c:
            r = await c.get('https://api.anthropic.com')
            print(f'PROXY OK status={r.status_code}')
    except Exception as e:
        print(f'PROXY FAILED: {type(e).__name__}: {e}')

asyncio.run(test())
