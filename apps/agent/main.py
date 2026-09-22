import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.agent.agent_service import LRAgentWorker

def main():
    print("=========================================================")
    print(" CtrlBooks Standalone Local Sync Agent (ctrlbooks_agent.exe)")
    print("=========================================================")
    agent = LRAgentWorker(interval_seconds=30)
    try:
        agent.start()
    except KeyboardInterrupt:
        print("\nKeyboard Interrupt received. Stopping agent...")
        agent.stop()
        print("Agent stopped cleanly.")

if __name__ == "__main__":
    main()
