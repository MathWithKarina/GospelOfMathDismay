"""A deliberately small AST evaluator for mathematical expressions; never uses eval()."""
from __future__ import annotations
import ast, math

class ExpressionError(ValueError): pass

class SafeExpression:
    FUNCTIONS={"sin":math.sin,"cos":math.cos,"tan":math.tan,"asin":math.asin,"acos":math.acos,"atan":math.atan,
        "sinh":math.sinh,"cosh":math.cosh,"tanh":math.tanh,"sqrt":math.sqrt,"abs":abs,"exp":math.exp,
        "log":math.log,"log10":math.log10,"floor":math.floor,"ceil":math.ceil}
    CONSTANTS={"pi":math.pi,"e":math.e,"tau":math.tau}
    def __init__(self, expression: str, variable: str="x"):
        self.original=expression; self.variable=variable
        if not expression or len(expression)>400: raise ExpressionError("Expression is empty or too long.")
        normalized=expression.replace("^","**").replace("−","-").strip()
        try: self.tree=ast.parse(normalized,mode="eval")
        except SyntaxError as exc: raise ExpressionError(f"Invalid mathematical syntax at column {exc.offset or 1}.") from exc
        self._validate(self.tree.body)
    def _validate(self,node):
        if isinstance(node,ast.Constant):
            if type(node.value) not in (int,float): raise ExpressionError("Only numeric constants are allowed.")
            if abs(float(node.value))>1e100: raise ExpressionError("Constant is too large.")
        elif isinstance(node,ast.Name):
            if node.id not in {self.variable,*self.CONSTANTS,*self.FUNCTIONS}: raise ExpressionError(f"Name not allowed: {node.id}")
        elif isinstance(node,ast.BinOp):
            if not isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.Mod)): raise ExpressionError("Operator not allowed.")
            self._validate(node.left); self._validate(node.right)
            if isinstance(node.op,ast.Pow) and isinstance(node.right,ast.Constant) and abs(float(node.right.value))>20: raise ExpressionError("Exponent is limited to ±20 for safety.")
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            self._validate(node.operand)
        elif isinstance(node,ast.Call):
            if not isinstance(node.func,ast.Name) or node.func.id not in self.FUNCTIONS: raise ExpressionError("Only approved mathematical functions may be called.")
            if node.keywords: raise ExpressionError("Named function arguments are not supported.")
            if len(node.args)!=1: raise ExpressionError("Each supported function takes exactly one argument.")
            for arg in node.args: self._validate(arg)
        else: raise ExpressionError(f"Expression element not allowed: {type(node).__name__}")
    def evaluate(self,x):
        return self._eval(self.tree.body,float(x))
    def _eval(self,n,x):
        if isinstance(n,ast.Constant): return float(n.value)
        if isinstance(n,ast.Name):
            if n.id==self.variable: return x
            if n.id in self.CONSTANTS: return self.CONSTANTS[n.id]
            if n.id in self.FUNCTIONS: return self.FUNCTIONS[n.id]
        if isinstance(n,ast.UnaryOp):
            v=self._eval(n.operand,x); return v if isinstance(n.op,ast.UAdd) else -v
        if isinstance(n,ast.BinOp):
            a=self._eval(n.left,x); b=self._eval(n.right,x)
            try:
                if isinstance(n.op,ast.Add): r=a+b
                elif isinstance(n.op,ast.Sub): r=a-b
                elif isinstance(n.op,ast.Mult): r=a*b
                elif isinstance(n.op,ast.Div): r=a/b
                elif isinstance(n.op,ast.Mod): r=a%b
                elif isinstance(n.op,ast.Pow): r=a**b
                else: raise ExpressionError("Operator not supported.")
            except (ArithmeticError,OverflowError,ValueError) as exc: raise ExpressionError(str(exc)) from exc
            if isinstance(r,complex) or not math.isfinite(float(r)): raise ExpressionError("Expression produced a non-real or non-finite value.")
            return float(r)
        if isinstance(n,ast.Call):
            fn=self.FUNCTIONS[n.func.id]; arg=self._eval(n.args[0],x)
            try: result=fn(arg)
            except (ArithmeticError,OverflowError,ValueError) as exc: raise ExpressionError(str(exc)) from exc
            if isinstance(result,complex) or not math.isfinite(float(result)): raise ExpressionError("Function produced a non-finite value.")
            return float(result)
        raise ExpressionError("Unsupported expression node.")
    def sample(self, xs):
        values=[]
        for x in xs:
            try: values.append(self.evaluate(float(x)))
            except (ExpressionError,ArithmeticError,ValueError,OverflowError): values.append(float("nan"))
        return values
