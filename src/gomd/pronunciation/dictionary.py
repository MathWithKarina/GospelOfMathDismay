from __future__ import annotations
import csv, json, re
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass
class PronunciationRule:
    source: str
    replacement: str
    language: str = "*"
    context: str = ""  # optional regular expression that must match the surrounding text
    case_sensitive: bool = False
    priority: int = 100
    enabled: bool = True
    engine_id: str = "*"
    note: str = ""

class PronunciationDictionary:
    def __init__(self, rules=None): self.rules=list(rules or [])
    def add(self, rule: PronunciationRule):
        if not rule.source: raise ValueError("Rule source cannot be empty")
        self.rules.append(rule)
    def apply(self, text: str, language: str="ru", engine_id: str="*") -> str:
        output=text
        # Larger numeric priority wins; stable insertion order breaks ties.
        rules=sorted((r for r in self.rules if r.enabled and r.source and r.language in ("*",language) and r.engine_id in ("*",engine_id)), key=lambda r:r.priority, reverse=True)
        for rule in rules:
            flags=0 if rule.case_sensitive else re.IGNORECASE
            # Token boundaries protect substrings within longer words.
            pattern=re.compile(r"(?<!\w)"+re.escape(rule.source)+r"(?!\w)", flags)
            if rule.context:
                try: context_re=re.compile(rule.context, flags)
                except re.error as exc: raise ValueError(f"Invalid context regex for {rule.source!r}: {exc}") from exc
                output=pattern.sub(lambda m: rule.replacement if context_re.search(output[max(0,m.start()-80):m.end()+80]) else m.group(0), output)
            else:
                output=pattern.sub(lambda _: rule.replacement, output)
        return output
    def save_json(self,path:Path):
        Path(path).write_text(json.dumps([asdict(r) for r in self.rules],ensure_ascii=False,indent=2),encoding="utf-8")
    @classmethod
    def load_json(cls,path:Path):
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([PronunciationRule(**x) for x in data])
    def export_csv(self,path:Path):
        fields=list(PronunciationRule.__dataclass_fields__)
        with Path(path).open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
            writer.writerows(asdict(rule) for rule in self.rules)
    @classmethod
    def import_csv(cls,path:Path):
        rules=[]
        with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                for key in ("case_sensitive","enabled"): row[key]=str(row.get(key,"false")).lower() in ("1","true","yes")
                row["priority"]=int(row.get("priority") or 100)
                rules.append(PronunciationRule(**{k:row.get(k, getattr(PronunciationRule,k,"")) for k in PronunciationRule.__dataclass_fields__}))
        return cls(rules)
