#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_ai_docs.py —— AI 文档一致性校验脚本

用途
    提取 modules/*.py 中公共函数/类的签名，与 ai_context/module_specs/*.md
    中记录的接口签名对比，检测「AI 文档与代码不同步」的情况，作为代码
    与文档同步的硬性闸门。

校验维度
    1. 每个 modules/<name>.py 是否存在对应 module_specs/<name>.md
    2. 代码公共接口是否都已记录在文档（缺文档）
    3. 文档记录的接口是否仍存在于代码（过期文档）
    4. 函数/方法签名（参数结构 + 返回注解）是否一致

module_specs 规格文件格式约定
    每个规格文件使用 ```python 代码块记录接口签名，签名必须是合法 Python
    （可省略函数体，使用 ... 占位）。示例：

        ```python
        class EnvInfo: ...
        def check_environment() -> EnvInfo: ...
        def print_env_info(info: EnvInfo) -> None: ...
        ```

    方法的参数可省略 self/cls，脚本会自动对齐比较。

比较规则
    - 按符号名（方法含所属类）匹配：先精确键匹配，再按名兜底。
    - 参数结构：比较参数名、顺序、是否有默认值、*args/**kwargs（忽略类型注解）。
    - 返回注解：双方都写明时必须文本一致；一方省略则视为兼容（允许文档简化）。
    - @property 装饰的方法不参与校验（属性，非可调用接口）。

用法
    python ai_context/check_ai_docs.py

退出码
    0 —— 全部一致
    1 —— 存在不一致或缺失
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# ------------------------------------------------------------------
# 路径定位（基于本脚本位置，可在任意目录下运行）
# ------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # ai_context/
PROJECT_ROOT = SCRIPT_DIR.parent                      # project_root/
MODULES_DIR = PROJECT_ROOT / "modules"
SPECS_DIR = SCRIPT_DIR / "module_specs"

# 期望的「模块 ↔ 规格」对应关系
EXPECTED_MODULES: List[str] = [
    "env_check",
    "file_utils",
    "subtitle_extractor",
    "ocr_subtitle",
    "transcriber",
    "subtitle_writer",
]

# 视为公共接口的 dunder 方法（其余以下划线开头的方法视为私有，跳过）
PUBLIC_DUNDERS = {"__init__", "__call__", "__str__", "__repr__"}

# 匹配 Markdown 中的 ```python 代码块
PY_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------
@dataclass
class Symbol:
    """一个被提取的接口符号（函数 / 类 / 方法）。"""
    kind: str            # "function" | "class" | "method"
    name: str
    arg_struct: str      # 归一化参数结构，如 "(a,b=?,*args,**kwargs)"
    ret: str             # 返回注解文本（已去空格），无则 ""
    display: str         # 用于展示的可读签名
    owner: str = ""      # 方法所属类名；顶层符号为空

    @property
    def key(self) -> str:
        """用于精确匹配的键（方法含所属类）。"""
        return f"{self.owner}.{self.name}" if self.owner else self.name


# ------------------------------------------------------------------
# 从代码 AST 提取符号
# ------------------------------------------------------------------
def _arg_struct(args: ast.arguments, drop_first: bool = False) -> str:
    """
    把 ast.arguments 归一化为不含类型注解的参数结构串。

    Args:
        args:        函数的 ast.arguments 节点
        drop_first:  方法场景下去掉首参 self/cls（文档常省略）

    Returns:
        形如 "(a,b=?,*args,**kwargs)" 的结构串
    """
    pos = list(args.args)
    if drop_first and pos and pos[0].arg in ("self", "cls"):
        pos = pos[1:]  # self/cls 不会有默认值，删去不影响默认值对齐

    n_defaults = len(args.defaults)          # 位置参数默认值数量
    parts: List[str] = []
    for i, a in enumerate(pos):
        marker = a.arg
        # 默认值作用于 pos 的最后 n_defaults 个
        if i >= len(pos) - n_defaults:
            marker += "=?"
        parts.append(marker)

    if args.vararg:
        parts.append("*" + args.vararg.arg)             # *args
    elif args.kwonlyargs:
        parts.append("*")                               # 裸 * 分隔符

    for j, a in enumerate(args.kwonlyargs):
        marker = a.arg
        if j < len(args.kw_defaults) and args.kw_defaults[j] is not None:
            marker += "=?"
        parts.append(marker)

    if args.kwarg:
        parts.append("**" + args.kwarg.arg)             # **kwargs

    return "(" + ",".join(parts) + ")"


def _return_text(node: ast.FunctionDef) -> str:
    """提取返回注解文本并去空格，无注解返回空串。"""
    if node.returns is not None:
        return ast.unparse(node.returns).replace(" ", "")
    return ""


def _first_sig_line(node: ast.AST) -> str:
    """
    从 ast.unparse 结果中取第一条 def/class 声明行（跳过装饰器行），
    去掉结尾冒号，作为展示签名。
    """
    src = ast.unparse(node)
    for line in src.splitlines():
        ls = line.strip()
        if ls.startswith(("def ", "class ", "async def ")):
            return ls.rstrip(":").rstrip()
    return src.splitlines()[0].rstrip(":").strip() if src else ""


def _is_property(node: ast.FunctionDef) -> bool:
    """判断方法是否为 @property / @x.setter / @x.getter（不参与校验）。"""
    for d in node.decorator_list:
        if isinstance(d, ast.Name) and d.id == "property":
            return True
        if isinstance(d, ast.Attribute) and d.attr in ("setter", "getter"):
            return True
    return False


def _is_public_method(name: str) -> bool:
    """判断方法名是否为对外公共接口（含选定 dunder）。"""
    if name in PUBLIC_DUNDERS:
        return True
    return not name.startswith("_")


def _make_function_symbol(node: ast.FunctionDef, kind: str, owner: str = "") -> Symbol:
    """构造函数/方法符号。方法场景去掉 self/cls。"""
    drop = kind == "method"
    return Symbol(
        kind=kind,
        name=node.name,
        arg_struct=_arg_struct(node.args, drop_first=drop),
        ret=_return_text(node),
        display=_first_sig_line(node),
        owner=owner,
    )


def _make_class_symbol(node: ast.ClassDef) -> Symbol:
    """构造类符号（arg_struct 记录基类列表）。"""
    bases = ",".join(ast.unparse(b) for b in node.bases)
    return Symbol(
        kind="class",
        name=node.name,
        arg_struct="(" + bases + ")",
        ret="",
        display=_first_sig_line(node),
        owner="",
    )


def extract_symbols(tree: ast.Module) -> List[Symbol]:
    """
    从模块 AST 中提取顶层公共函数、公共类及其公共方法。

    私有（下划线开头）顶层符号、@property 方法、私有方法均跳过。
    """
    syms: List[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                syms.append(_make_function_symbol(node, "function"))
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                syms.append(_make_class_symbol(node))
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and _is_public_method(m.name) \
                            and not _is_property(m):
                        syms.append(_make_function_symbol(m, "method", owner=node.name))
    return syms


# ------------------------------------------------------------------
# 从 Markdown 规格文件提取符号
# ------------------------------------------------------------------
def _parse_block(block: str) -> List[Symbol]:
    """解析一个 ```python 代码块为符号列表。"""
    out: List[Symbol] = []
    # 1) 尝试整块解析（块内若为合法 Python，可保留类-方法层级关系）
    try:
        out.extend(extract_symbols(ast.parse(block)))
        if out:
            return out
    except SyntaxError:
        pass
    # 2) 逐行修复解析（兼容逐行罗列签名的写法）
    for raw in block.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line.startswith(("def ", "class ", "async def ")):
            continue
        if line.endswith("..."):
            line = line[:-3].strip()
        if not line.endswith(":"):
            line += ":"
        try:
            out.extend(extract_symbols(ast.parse(line + " pass")))
        except SyntaxError:
            continue
    return out


def extract_symbols_from_md(path: Path) -> List[Symbol]:
    """读取规格 md 文件，提取其中所有 ```python 块里的签名符号。"""
    text = path.read_text(encoding="utf-8")
    syms: List[Symbol] = []
    for block in PY_BLOCK_RE.findall(text):
        syms.extend(_parse_block(block))
    return syms


# ------------------------------------------------------------------
# 比较逻辑
# ------------------------------------------------------------------
def _find(counterparts_by_key: dict, counterparts_by_name: dict, sym: Symbol) -> Optional[Symbol]:
    """在对侧查找对应符号：先精确键匹配，再按名兜底。"""
    if sym.key in counterparts_by_key:
        return counterparts_by_key[sym.key]
    return counterparts_by_name.get(sym.name)


def _sig_match(a: Symbol, b: Symbol) -> bool:
    """
    判断两符号签名是否一致。

    - 参数结构必须相同（名称/顺序/默认值/*args/**kwargs）。
    - 返回注解：双方都写明时必须文本一致；一方省略视为兼容。
    """
    if a.arg_struct != b.arg_struct:
        return False
    if a.ret and b.ret:
        return a.ret == b.ret
    return True


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------
def main() -> int:
    print("=" * 64)
    print("AI 文档一致性校验  check_ai_docs.py")
    print("=" * 64)
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"模块目录:   {MODULES_DIR}")
    print(f"规格目录:   {SPECS_DIR}")

    total_issues = 0
    total_ok = 0

    # 已存在的规格文件（用于孤儿检测）
    all_specs = {p.stem for p in SPECS_DIR.glob("*.md")} if SPECS_DIR.exists() else set()

    for name in EXPECTED_MODULES:
        py = MODULES_DIR / f"{name}.py"
        md = SPECS_DIR / f"{name}.md"
        print(f"\n--- 模块: {name} ---")

        # 提取代码侧符号
        code_syms: List[Symbol] = []
        if py.exists():
            try:
                code_syms = extract_symbols(ast.parse(py.read_text(encoding="utf-8")))
            except SyntaxError as e:
                print(f"  [X] 代码解析失败 {py.name}: {e}")
                total_issues += 1
        else:
            print(f"  [X] 缺实现文件: {py}")
            total_issues += 1

        # 提取文档侧符号
        doc_syms: List[Symbol] = []
        if md.exists():
            try:
                doc_syms = extract_symbols_from_md(md)
            except OSError as e:
                print(f"  [X] 规格文件读取失败 {md.name}: {e}")
                total_issues += 1
        else:
            print(f"  [!] 缺规格文件: {md.name}（请在 module_specs/ 下补充）")
            total_issues += 1

        if not code_syms and not doc_syms:
            continue

        code_by_key = {s.key: s for s in code_syms}
        code_by_name = {s.name: s for s in code_syms}
        doc_by_key = {s.key: s for s in doc_syms}
        doc_by_name = {s.name: s for s in doc_syms}

        # 维度 2：代码 → 文档（缺文档 / 签名不一致）
        for s in code_syms:
            d = _find(doc_by_key, doc_by_name, s)
            if d is None:
                print(f"  [>] 代码有、文档无: {s.display}")
                total_issues += 1
            elif not _sig_match(s, d):
                print(f"  [~] 签名不一致: {s.name}")
                print(f"        代码: {s.display}")
                print(f"        文档: {d.display}")
                total_issues += 1
            else:
                total_ok += 1

        # 维度 3：文档 → 代码（过期文档）
        for s in doc_syms:
            c = _find(code_by_key, code_by_name, s)
            if c is None:
                print(f"  [<] 文档有、代码无（过期）: {s.display}")
                total_issues += 1

    # 孤儿规格：有规格文件但无对应模块
    orphan_specs = all_specs - set(EXPECTED_MODULES)
    for o in sorted(orphan_specs):
        print(f"\n[?] 多余规格文件（无对应模块）: module_specs/{o}.md")
        total_issues += 1

    # 未登记模块：modules/ 下有 .py 但不在期望清单（且非 __init__）
    if MODULES_DIR.exists():
        extra_py = {p.stem for p in MODULES_DIR.glob("*.py")} - set(EXPECTED_MODULES) - {"__init__"}
        for e in sorted(extra_py):
            print(f"\n[?] 未登记模块（无对应规格）: modules/{e}.py")
            total_issues += 1

    # 汇总
    print("\n" + "=" * 64)
    print(f"校验完成: 一致 {total_ok} 项, 问题 {total_issues} 项")
    if total_issues == 0:
        print("结果: 通过 —— 文档与代码保持同步")
    else:
        print("结果: 未通过 —— 请按上述提示同步文档与代码")
    print("=" * 64)
    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 兜底，避免脚本自身异常无提示
        print(f"[X] 校验脚本发生异常: {e}", file=sys.stderr)
        sys.exit(2)
