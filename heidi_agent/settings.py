"""Project paths and conservative default limits (no data from previous runs)."""
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
INPUT = ROOT / 'data' / 'input' / 'Heidi_Input.xlsx'
DATABASE = ROOT / 'data' / 'heidi.sqlite3'
OUTPUT = ROOT / 'data' / 'output'


def config():
    return {
        'gemini_key': os.getenv('GEMINI_API_KEY', '').strip(),
        'tavily_key': os.getenv('TAVILY_API_KEY', '').strip(),
        'model': os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite').strip(),
        'max_gemini_calls': max(1, int(os.getenv('MAX_GEMINI_CALLS', '55'))),
        'http_timeout': float(os.getenv('HTTP_TIMEOUT_SECONDS', '15')),
        'crawl_delay': float(os.getenv('CRAWL_DELAY_SECONDS', '1')),
    }
