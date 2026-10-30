# backend/interactive_interview.py
import asyncio
import json
import sys

# 1. Verification of websockets library
try:
    import websockets
except ImportError:
    print("\n[ERROR] 'websockets' library is not installed in this environment.")
    print("Run: pip install websockets\n")
    sys.exit(1)

# Put your exact demo user_id here (from POST /api/v1/users/demo)
USER_ID = "a78fe6a5-4c30-4b91-88e9-f1493234f6fe"
SLUG = "two-sum"
WS_URI = f"ws://127.0.0.1:8000/ws/interview/{SLUG}/{USER_ID}"

async def run_interview():
    print(f"\n[1/3] Target URI: {WS_URI}")
    print("[2/3] Initiating WebSocket handshake with FastAPI...")
    sys.stdout.flush()

    try:
        async with websockets.connect(WS_URI) as ws:
            print("[3/3] Handshake successful! Connected to AI Interviewer.\n")
            print("=" * 55)
            print("AI Mock Interview Session Active")
            print("Type your response and hit Enter. Type 'exit' to quit.")
            print("=" * 55 + "\n")

            while True:
                user_msg = input("\nYou (Candidate): ").strip()
                if not user_msg:
                    continue
                if user_msg.lower() == "exit":
                    print("\nEnding interview session.")
                    break

                payload = {
                    "utterance": user_msg,
                    "language": "python",
                    "sandbox_result": None,
                    "criteria_updates": {}
                }
                await ws.send(json.dumps(payload))

                raw_response = await ws.recv()
                data = json.loads(raw_response)

                print("\n" + "-" * 45)
                print(f"Interviewer: {data.get('spoken_response')}")
                print(f"Stage: [{data.get('current_stage')}] | Transitioned: {data.get('transitioned')}")
                if data.get("hint_tier"):
                    print(f"Hint Tier: {data.get('hint_tier')}")
                if data.get("anti_pattern"):
                    print(f"Anti-Pattern Detected: {data.get('anti_pattern')}")
                print("-" * 45)

    except websockets.exceptions.InvalidStatus as e:
        status_code = getattr(e, "status_code", None) or getattr(
            getattr(e, "response", None), "status_code", "unknown"
        )
        print(f"\n[ERROR] WebSocket Handshake Rejected by Server (HTTP status: {status_code})")
        print("Check your terminal running uvicorn for the backend traceback.")
    except ConnectionRefusedError:
        print("\n[ERROR] Connection Refused: Uvicorn is not running on 127.0.0.1:8000.")
        print("Start it with: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(run_interview())