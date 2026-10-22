import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from miem_assistant.engine import Assistant
q=' '.join(sys.argv[1:]) or input('Вопрос: ')
print(json.dumps(Assistant().answer(q),ensure_ascii=False,indent=2))
