#!/usr/bin/env python3
import asyncio
import websockets
import json
import argparse
import sys
import datetime

async def connect_to_output_websocket(url):
    """
    Connect to the output websocket and print all received messages.
    
    Args:
        url: The WebSocket URL to connect to (e.g., 'ws://localhost:8000/ws/output')
    """
    try:
        async with websockets.connect(url) as websocket:
            print(f"Connected to output websocket at {url}")
            print("Waiting for messages... (Press Ctrl+C to exit)")
            
            while True:
                # Wait for a message
                message = await websocket.recv()
                
                # Try to parse as JSON for prettier output
                try:
                    parsed = json.loads(message)
                    print(json.dumps(parsed, indent=2))
                except json.JSONDecodeError:
                    # If not JSON, print as is
                    print(f"Received non-JSON message: {message}")
                except Exception as e:
                    print(f"Error processing message: {e}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description='WebSocket Output Client')
    parser.add_argument('--host', default='localhost', help='Host to connect to')
    parser.add_argument('--port', type=int, default=8000, help='Port to connect to')
    parser.add_argument('--path', default='/ws/output', help='WebSocket path')
    args = parser.parse_args()
    
    url = f"ws://{args.host}:{args.port}{args.path}"
    
    try:
        asyncio.run(connect_to_output_websocket(url))
    except KeyboardInterrupt:
        print("\nClient stopped by user")

if __name__ == "__main__":
    main()