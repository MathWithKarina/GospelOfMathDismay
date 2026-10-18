import math
import pytest
from gomd.graphs.safe_expr import SafeExpression, ExpressionError
from gomd.graphs.render import GraphRenderer

def test_safe_expression_math():
    f=SafeExpression("x^2 + sin(x)")
    assert abs(f.evaluate(2)-(4+math.sin(2)))<1e-9

def test_safe_expression_rejects_python_execution():
    for expr in ("__import__('os')", "x.__class__", "open('secret')", "lambda x: x"):
        with pytest.raises(ExpressionError): SafeExpression(expr)

def test_graph_png_and_csv_export(tmp_path):
    png=GraphRenderer().render(["y=x^2","y=sin(x)"],tmp_path/"graph.png",-2,2,-1,4,samples=150)
    csv=GraphRenderer().export_csv(["y=x^2"],tmp_path/"graph.csv",-2,2,samples=100)
    assert png.stat().st_size>1000
    assert csv.read_text(encoding="utf-8-sig").startswith("x,y=x^2")
