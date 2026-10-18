from __future__ import annotations
import csv
from pathlib import Path

def _pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt

class GraphRenderer:
    def __init__(self): pass
    def render(self, functions: list[str], output: Path, x_min=-10, x_max=10, y_min=-10, y_max=10, samples=1600,
               grid=True, labels=True) -> Path:
        import numpy as np
        from .safe_expr import SafeExpression
        if not functions: raise ValueError("Enter at least one function")
        if not (-1e6<=x_min<x_max<=1e6 and -1e9<=y_min<y_max<=1e9): raise ValueError("Invalid graph axis range")
        if samples<100 or samples>10000: raise ValueError("Number of samples must be between 100 and 10,000")
        plt=_pyplot(); output=Path(output).expanduser().resolve(); output.parent.mkdir(parents=True,exist_ok=True)
        xs=np.linspace(float(x_min),float(x_max),int(samples))
        fig,ax=plt.subplots(figsize=(9,5.5),dpi=150)
        try:
            for i,expr in enumerate(functions):
                normalized=expr.strip()
                if "=" in normalized: normalized=normalized.split("=",1)[1].strip()
                parser=SafeExpression(normalized)
                ys=np.asarray(parser.sample(xs),dtype=float)
                ys[np.abs(ys)>1e9]=np.nan
                ax.plot(xs,ys,label=expr.strip() or f"f{i+1}",linewidth=1.8)
            ax.set_xlim(x_min,x_max); ax.set_ylim(y_min,y_max)
            if grid: ax.grid(True,alpha=.3)
            if labels:
                ax.axhline(0,linewidth=.8); ax.axvline(0,linewidth=.8); ax.set_xlabel("x"); ax.set_ylabel("y")
            if len(functions)>1: ax.legend()
            fig.tight_layout()
            suffix=output.suffix.lower()
            if suffix not in (".png",".svg",".pdf"): raise ValueError("Graph output must use PNG, SVG, or PDF")
            fig.savefig(output,format=suffix[1:],bbox_inches="tight")
        finally: plt.close(fig)
        return output
    def export_csv(self, functions: list[str], output: Path, x_min=-10, x_max=10, samples=1000) -> Path:
        import numpy as np
        from .safe_expr import SafeExpression
        if not functions: raise ValueError("Enter at least one function")
        xs=np.linspace(float(x_min),float(x_max),int(samples)); result=[]
        for expr in functions:
            expression=expr.split("=",1)[1] if "=" in expr else expr
            result.append(SafeExpression(expression.strip()).sample(xs))
        output=Path(output).resolve(); output.parent.mkdir(parents=True,exist_ok=True)
        with output.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f); w.writerow(["x",*functions])
            for idx,x in enumerate(xs): w.writerow([f"{x:.12g}",*(f"{col[idx]:.12g}" if np.isfinite(col[idx]) else "" for col in result)])
        return output
