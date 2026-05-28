import urllib.request
import json

def main():
    try:
        url = "http://localhost:8000/api/events"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            print("Response Status Code: 200")
            print("Total events fetched:", len(data))
            for item in data:
                print(f"- {item.get('title')}: {item.get('date')} {item.get('time')}")
    except Exception as e:
        print("Failed to fetch /api/events:", e)

if __name__ == "__main__":
    main()
