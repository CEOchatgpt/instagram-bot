import asyncio
import aiohttp
import json
import os

async def test_profile():
    RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
    RAPIDAPI_HOST = "instagram120.p.rapidapi.com"
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    username = "cristiano"  # یا هر یوزری که میخوای
    
    async with aiohttp.ClientSession() as session:
        url = f"https://{RAPIDAPI_HOST}/api/instagram/userInfo"
        async with session.post(url, json={"username": username}, headers=headers) as resp:
            data = await resp.json()
            print("Full response:")
            print(json.dumps(data, indent=2))
            
            result = data.get("result", data)
            user_data = result.get("user", result)
            
            print("\n" + "="*50)
            print("Extracted data:")
            print(f"Username: {user_data.get('username')}")
            print(f"Full name: {user_data.get('full_name')}")
            print(f"Followers: {user_data.get('follower_count')}")
            print(f"Following: {user_data.get('following_count')}")
            print(f"Posts: {user_data.get('media_count')}")

asyncio.run(test_profile())
