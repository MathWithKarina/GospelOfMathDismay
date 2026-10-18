"""Math-aware notation expansion for readable TTS input; not a symbolic algebra system."""
from __future__ import annotations
from dataclasses import dataclass, field
import re

@dataclass
class NormalizationResult:
    text: str
    warnings: list[str] = field(default_factory=list)
    source: str = ""

ONES = {0:"ноль",1:"один",2:"два",3:"три",4:"четыре",5:"пять",6:"шесть",7:"семь",8:"восемь",9:"девять"}
FEM = {0:"ноль",1:"одна",2:"две",3:"три",4:"четыре",5:"пять",6:"шесть",7:"семь",8:"восемь",9:"девять"}
TEENS = {10:"десять",11:"одиннадцать",12:"двенадцать",13:"тринадцать",14:"четырнадцать",15:"пятнадцать",16:"шестнадцать",17:"семнадцать",18:"восемнадцать",19:"девятнадцать"}
TENS = {20:"двадцать",30:"тридцать",40:"сорок",50:"пятьдесят",60:"шестьдесят",70:"семьдесят",80:"восемьдесят",90:"девяносто"}
HUNDREDS = {100:"сто",200:"двести",300:"триста",400:"четыреста",500:"пятьсот",600:"шестьсот",700:"семьсот",800:"восемьсот",900:"девятьсот"}
GREEK = {"alpha":"альфа","beta":"бета","gamma":"гамма","delta":"дельта","epsilon":"эпсилон","theta":"тета","lambda":"лямбда","mu":"мю","pi":"пи","rho":"ро","sigma":"сигма","phi":"фи","omega":"омега","α":"альфа","β":"бета","γ":"гамма","δ":"дельта","ε":"эпсилон","θ":"тета","λ":"лямбда","μ":"мю","π":"пи","ρ":"ро","σ":"сигма","φ":"фи","ω":"омега"}
VARIABLES = {"x":"икс","y":"игрек","z":"зет","a":"а","b":"бэ","c":"цэ","n":"эн","m":"эм","t":"тэ","r":"эр","f":"эф","g":"же","v":"вектор вэ","X":"икс","Y":"игрек","Z":"зет","E":"и","I":"ай","U":"ю","R":"ар","P":"пэ","T":"тэ","F":"эф","N":"эн","M":"эм","C":"цэ","V":"вэ","L":"эл"}
FUNCTIONS = {"sin":"синус","cos":"косинус","tan":"тангенс","ln":"натуральный логарифм","log":"логарифм","exp":"экспонента","lim":"предел","max":"максимум","min":"минимум"}
UNITS = {"км":"километров","см":"сантиметров","мм":"миллиметров","кг":"килограммов","м":"метров","г":"граммов","с":"секунд","сек":"секунд","мин":"минут","ч":"часов","час":"часов","Гц":"герц","кГц":"килогерц","Н":"ньютонов","Дж":"джоулей","Вт":"ватт","В":"вольт","А":"ампер","Па":"паскалей","°C":"градусов Цельсия"}
DATIVE = {0:"нулю",1:"одному",2:"двум",3:"трём",4:"четырём",5:"пяти",6:"шести",7:"семи",8:"восьми",9:"девяти",10:"десяти",11:"одиннадцати",12:"двенадцати",13:"тринадцати",14:"четырнадцати",15:"пятнадцати",16:"шестнадцати",17:"семнадцати",18:"восемнадцати",19:"девятнадцати"}
GENITIVE = {0:"нуля",1:"одного",2:"двух",3:"трёх",4:"четырёх",5:"пяти",6:"шести",7:"семи",8:"восьми",9:"девяти",10:"десяти",11:"одиннадцати",12:"двенадцати",13:"тринадцати",14:"четырнадцати",15:"пятнадцати",16:"шестнадцати",17:"семнадцати",18:"восемнадцати",19:"девятнадцати"}

def _under_1000(n: int, feminine: bool = False) -> str:
    parts=[]
    h=(n//100)*100
    if h: parts.append(HUNDREDS[h])
    r=n%100
    if r in TEENS: parts.append(TEENS[r])
    else:
        t=(r//10)*10
        if t: parts.append(TENS[t])
        o=r%10
        if o: parts.append((FEM if feminine else ONES)[o])
    return " ".join(parts) or "ноль"

def integer_to_words(n: int) -> str:
    if n < 0: return "минус " + integer_to_words(-n)
    if n < 1000: return _under_1000(n)
    if n < 1_000_000:
        thousands, rest = divmod(n,1000)
        tail = "тысяча" if thousands%10==1 and thousands%100!=11 else ("тысячи" if 2<=thousands%10<=4 and not 12<=thousands%100<=14 else "тысяч")
        bits=[_under_1000(thousands, True),tail]
        if rest: bits.append(_under_1000(rest))
        return " ".join(bits)
    return str(n)  # Keep large integers literal rather than inventing a questionable declension.

def number_to_words(token: str, case: str = "nominative") -> str:
    raw=token.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try: value=float(raw)
    except ValueError: return token
    if not (value == value and abs(value) != float("inf")): return token
    prefix=""
    if value < 0: prefix="минус "; value=abs(value)
    if "." not in raw:
        n=int(value); table=DATIVE if case=="dative" else GENITIVE if case=="genitive" else None
        return prefix + (table[n] if table and n in table else integer_to_words(n))
    whole, frac=raw.split(".",1); frac=frac.rstrip("0") or "0"
    whole_n=int(whole or 0); frac_n=int(frac)
    if case=="dative":
        whole_text={0:"нулому",1:"одному",2:"двум",3:"трём",4:"четырём",5:"пяти",6:"шести",7:"семи",8:"восьми",9:"девяти"}.get(whole_n,integer_to_words(whole_n))
        whole_form="целому" if whole_n==1 else "целым"
        if len(frac)==1:
            numerator="одной" if frac_n==1 else GENITIVE.get(frac_n,integer_to_words(frac_n))
            denominator="десятой" if frac_n==1 else "десятым"
            frac_text=f"{numerator} {denominator}"
        elif len(frac)==2: frac_text=GENITIVE.get(frac_n,integer_to_words(frac_n))+" сотым"
        elif len(frac)==3: frac_text=GENITIVE.get(frac_n,integer_to_words(frac_n))+" тысячным"
        else: frac_text=" ".join(ONES[int(ch)] for ch in frac)
        return prefix+f"{whole_text} {whole_form} {frac_text}"
    whole_text="одна" if whole_n==1 else integer_to_words(whole_n)
    whole_form="целая" if whole_n==1 else "целых"
    if len(frac)==1:
        frac_text=integer_to_words(frac_n)+(" десятая" if frac_n==1 else " десятых")
    elif len(frac)==2:
        frac_text=integer_to_words(frac_n)+(" сотая" if frac_n==1 else " сотых")
    elif len(frac)==3:
        frac_text=integer_to_words(frac_n)+" тысячных"
    else:
        frac_text=" ".join(ONES[int(ch)] for ch in frac)
    return prefix + f"{whole_text} {whole_form} {frac_text}"

TOKEN_RE = re.compile(r"=>|->|<=|>=|!=|==|\\(?:sqrt|frac|alpha|beta|gamma|delta|theta|lambda|pi|sigma|omega|int|sum|prod|lim|infty|vec|overrightarrow)|\d+(?:[.,]\d+)?|[A-Za-zА-Яа-яЁёα-ωΑ-Ω]+|°C|[⁰¹²³⁴⁵⁶⁷⁸⁹]|[+−\-*/×÷=<>^_(){}\[\],.;:!?√∫∑∏∞]|\s+|.", re.UNICODE)

class ExpressionParser:
    def __init__(self, source: str):
        raw_tokens=[t for t in TOKEN_RE.findall(source) if not t.isspace()]
        self.tokens=[]
        for token in raw_tokens:
            if (re.fullmatch(r"[A-Za-zА-Яа-яЁёα-ωΑ-Ω]+", token) and len(token)>1
                    and token.lower() not in FUNCTIONS and token.lower() not in GREEK and token not in UNITS):
                self.tokens.extend(token)
            else:
                self.tokens.append(token)
        self.pos=0; self.warnings=[]
    def peek(self): return self.tokens[self.pos] if self.pos<len(self.tokens) else None
    def take(self):
        value=self.peek()
        if value is None: raise ValueError("unexpected end")
        self.pos+=1; return value
    def match(self,*items):
        if self.peek() in items: return self.take()
        return None
    def parse(self):
        result=self.relation()
        if self.pos<len(self.tokens): raise ValueError("unexpected token: "+str(self.peek()))
        return result
    def relation(self):
        left=self.additive()
        ops={"=":"равно", "==":"равно", "<":"меньше", ">":"больше", "<=":"меньше или равно", ">=":"больше или равно", "!=":"не равно"}
        variable_words=set(VARIABLES.values())|set(GREEK.values())
        while self.peek() in ops:
            op=self.take(); start=self.pos; right=self.additive(); consumed=self.tokens[start:self.pos]
            # Apply a modest grammatical case only when the right side is a single literal.
            if len(consumed)==1 and re.fullmatch(r"\d+(?:[.,]\d+)?",consumed[0]) and op in ("=","==","<",">","<=",">="):
                right=number_to_words(consumed[0],"dative")
            phrase=ops[op]
            if op in ("=","==") and (left in variable_words or left.startswith("корень квадратный из ")):
                phrase="равен"
            left=f"{left} {phrase} {right}"
        return left
    def additive(self):
        left=self.product()
        while self.peek() in ("+","-","−"):
            op=self.take(); right=self.product(); left=f"{left} {'плюс' if op=='+' else 'минус'} {right}"
        return left
    def product(self):
        left=self.power()
        while True:
            op=self.peek()
            if op in ("*","×","·"):
                self.take(); left=f"{left} умножить на {self.power()}"
            elif op in ("/","÷"):
                self.take(); left=f"{left} разделить на {self.power()}"
            elif self._starts_atom(op):
                left=f"{left} {self.power()}"  # conventional implicit multiplication, e.g. 2x
            else: break
        return left
    def _starts_atom(self, op):
        if op is None or op in (")", "}", "]", "+", "-", "−", "=", "==", "<", ">", "<=", ">=", "!=" ,",", ";", ":"): return False
        return bool(re.fullmatch(r"\d+(?:[.,]\d+)?|[A-Za-zА-Яа-яЁёα-ωΑ-Ω]+|\\[A-Za-z]+|[({\[]|√|[⁰¹²³⁴⁵⁶⁷⁸⁹]",op))
    def power(self):
        base=self.unary()
        if self.match("_"):
            if self.match("{"):
                if self.peek() and re.fullmatch(r"\d+",self.peek()): sub=number_to_words(self.take())
                else: sub=self.relation()
                self.match("}")
            else: sub=self.atom()
            base=f"{base} с индексом {sub}"
        if self.match("^"):
            exponent=self.unary()
            if exponent in ("два", "2"): return base+" в квадрате"
            if exponent in ("три", "3"): return base+" в кубе"
            return f"{base} в степени {exponent}"
        if self.peek() and re.fullmatch(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]", self.peek()):
            exp=self.take().translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹","0123456789"))
            return base+(" в квадрате" if exp=="2" else " в кубе" if exp=="3" else f" в степени {integer_to_words(int(exp))}")
        return base
    def unary(self):
        if self.match("-") or self.match("−"): return "минус "+self.unary()
        if self.match("+"): return "плюс "+self.unary()
        return self.atom()
    def atom(self):
        tok=self.take()
        if tok in ("(","{","["):
            inner=self.relation(); closing={"(":")","{":"}","[":"]"}[tok]
            if not self.match(closing): raise ValueError("missing closing bracket")
            return "открываем скобку "+inner+" закрываем скобку"
        if tok in ("\\sqrt","√"):
            if self.match("{"):
                # A direct numeric radicand has an unambiguous genitive reading.
                if self.peek() and re.fullmatch(r"\d+(?:[.,]\d+)?",self.peek()): val=number_to_words(self.take(),"genitive")
                else: val=self.relation()
                self.match("}")
            else: val=self.atom()
            return "корень квадратный из "+val
        if tok=="\\frac":
            self.match("{"); num=self.relation(); self.match("}"); self.match("{"); den=self.relation(); self.match("}")
            return f"дробь: {num}, делённое на {den}"
        if tok in ("\\vec","\\overrightarrow"):
            if self.match("{"): val=self.relation(); self.match("}")
            else: val=self.atom()
            return "вектор "+val
        if tok in ("\\int","∫"): return "интеграл"
        if tok in ("\\sum","∑"): return "сумма"
        if tok in ("\\prod","∏"): return "произведение"
        if tok in ("\\infty","∞"): return "бесконечность"
        if re.fullmatch(r"\d+(?:[.,]\d+)?",tok): return number_to_words(tok)
        if tok.startswith("\\"): tok=tok[1:]
        # Unit readings are selected for symbols immediately following a number (5 м, 3 кг).
        previous=self.tokens[self.pos-2] if self.pos>=2 else None
        if tok in UNITS and previous is not None and re.fullmatch(r"\d+(?:[.,]\d+)?",previous): return UNITS[tok]
        low=tok.lower()
        if low in GREEK: return GREEK[low]
        if tok in VARIABLES: return VARIABLES[tok]
        if low in FUNCTIONS: return FUNCTIONS[low]
        if len(tok)==1 and tok.isalpha(): return tok.lower()
        if tok in (",",";",":"): return ""
        raise ValueError("unrecognised token: "+tok)

class MathTextEngine:
    def normalize(self, source: str) -> NormalizationResult:
        if not isinstance(source,str): raise TypeError("source must be text")
        warnings=[]; parts=[]
        # Preserve prose and normalize only explicit math spans or lines containing relations.
        for line in source.splitlines() or [source]:
            clean=line.strip()
            if not clean:
                parts.append(""); continue
            if "=>" in clean or "->" in clean:
                chunks=re.split(r"\s*(?:=>|->)\s*",clean)
                converted=[]
                for idx,chunk in enumerate(chunks):
                    spoken, warn=self._convert_expression(chunk)
                    converted.append(("отсюда следует, что " if idx else "")+spoken)
                    warnings.extend(warn)
                parts.append(", ".join(converted)); continue
            if "$" in clean:
                def sub(m):
                    spoken, warn=self._convert_expression(m.group(1)); warnings.extend(warn); return spoken
                parts.append(re.sub(r"\$(.+?)\$",sub,clean)); continue
            if "=" in clean or re.search(r"(?:<=|>=|!=|(?<!<)<(?! )|(?<!>)>(?! ))",clean):
                spoken,warn=self._convert_expression(clean)
                if warn and spoken==clean:
                    # Try only explicitly introduced suffixes so prose is not misread as variables.
                    found=False
                    for match in re.finditer(r"\b(если|когда|что|при условии, что|if|when)\s+",clean,re.IGNORECASE):
                        suffix=clean[match.end():]
                        candidate,candidate_warnings=self._convert_expression(suffix)
                        if not candidate_warnings:
                            parts.append(clean[:match.end()]+candidate); warnings.extend(candidate_warnings); found=True; break
                    if not found: parts.append(clean); warnings.extend(warn)
                else: parts.append(spoken); warnings.extend(warn)
            elif re.fullmatch(r"-?\d+(?:[.,]\d+)?", clean):
                parts.append(number_to_words(clean))
            elif re.fullmatch(r"[-+A-Za-zА-Яа-яЁёα-ωΑ-Ω0-9\s.,*/^_(){}\[\]×÷√∫∑∏]+",clean) and (
                    re.search(r"[0-9^_√∫∑∏*/]",clean)
                    or re.fullmatch(r"\s*[A-Za-zА-Яа-яЁёα-ωΑ-Ω]\s*(?:[+−-]\s*[A-Za-zА-Яа-яЁёα-ωΑ-Ω]\s*)+",clean)
                    or re.fullmatch(r"\s*(?:sin|cos|tan|ln|log|exp)\s*\(.*\)\s*",clean,re.IGNORECASE)):
                spoken,warn=self._convert_expression(clean)
                parts.append(spoken); warnings.extend(warn)
            else:
                parts.append(self._normalize_inline_latex(clean,warnings))
        return NormalizationResult("\n".join(parts), warnings, source)

    def _convert_expression(self, expression: str) -> tuple[str,list[str]]:
        source=expression.strip()
        if not source: return source,["Пустое математическое выражение."]
        mixed=re.fullmatch(r"(\d+)\s+(\d+)\s*/\s*(\d+)",source)
        if mixed:
            whole,num,den=(int(x) for x in mixed.groups())
            den_forms={2:("вторая","вторых"),3:("третья","третьих"),4:("четвёртая","четвёртых"),5:("пятая","пятых"),6:("шестая","шестых"),7:("седьмая","седьмых"),8:("восьмая","восьмых"),9:("девятая","девятых"),10:("десятая","десятых"),100:("сотая","сотых")}
            den_form=den_forms.get(den)
            if den_form and num<den and num>0:
                whole_form="целая" if whole==1 else "целых"
                numerator="одна" if num==1 else integer_to_words(num)
                fraction=den_form[0] if num==1 else den_form[1]
                return f"{number_to_words(str(whole))} {whole_form} {numerator} {fraction}",[]
            return source,["Смешанная дробь распознана, но её знаменатель требует ручной проверки."]
        unit=re.fullmatch(r"(?P<num>-?\d+(?:[.,]\d+)?)\s*(?P<u>м/с\^?2?|км/ч|кг|г|м|км|см|мм|с|сек|мин|ч|час|Гц|кГц|Н|Дж|Вт|В|А|Па|°C)",source)
        if unit:
            n=unit.group("num").replace(",","."); u=unit.group("u"); value=float(n)
            if u=="м/с": phrase="метров в секунду"
            elif u in ("м/с2","м/с^2"): phrase="метров в секунду в квадрате"
            elif u=="км/ч": phrase="километров в час"
            else:
                forms={"м":("метр","метра","метров"),"км":("километр","километра","километров"),"см":("сантиметр","сантиметра","сантиметров"),"мм":("миллиметр","миллиметра","миллиметров"),"кг":("килограмм","килограмма","килограммов"),"г":("грамм","грамма","граммов"),"с":("секунда","секунды","секунд"),"сек":("секунда","секунды","секунд"),"мин":("минута","минуты","минут"),"ч":("час","часа","часов"),"час":("час","часа","часов"),"Гц":("герц","герца","герц"),"кГц":("килогерц","килогерца","килогерц"),"Н":("ньютон","ньютона","ньютонов"),"Дж":("джоуль","джоуля","джоулей"),"Вт":("ватт","ватта","ватт"),"В":("вольт","вольта","вольт"),"А":("ампер","ампера","ампер"),"Па":("паскаль","паскаля","паскалей"),"°C":("градус Цельсия","градуса Цельсия","градусов Цельсия")}
                forms_for_unit=forms.get(u)
                if forms_for_unit:
                    whole=int(abs(value)); last_two=whole%100; last=whole%10
                    idx=0 if abs(value)==1 else 1 if 2<=last<=4 and not 12<=last_two<=14 else 2
                    phrase=forms_for_unit[idx]
                else: phrase=UNITS.get(u,u)
            return f"{number_to_words(n)} {phrase}",[]
        try:
            parser=ExpressionParser(source); result=parser.parse()
            # Refine basic equality delivery: relational phrases read naturally for common school notation.
            result=re.sub(r"\bравно (?=(?:один|два|три|четыре|пять|шесть|семь|восемь|девять|ноль)\b)","равно ",result)
            return result,parser.warnings
        except (ValueError, IndexError) as exc:
            return source,[f"Не удалось однозначно разобрать «{source}»: {exc}. Проверьте преобразование вручную."]

    def _normalize_inline_latex(self, text: str, warnings: list[str]) -> str:
        # Inline LaTeX outside dollar-delimited spans is converted only for known standalone commands.
        def replace(m):
            word=GREEK.get(m.group(1),m.group(1))
            return word
        result=re.sub(r"\\(alpha|beta|gamma|delta|theta|lambda|pi|sigma|omega)\b",replace,text)
        if "\\" in result and re.search(r"\\(?:frac|sqrt|int|sum|prod)",result):
            warnings.append("Обнаружена LaTeX-конструкция вне знаков $…$; заключите формулу в $…$ для надёжной обработки.")
        return result

def normalize_math_text(source: str) -> NormalizationResult:
    return MathTextEngine().normalize(source)
