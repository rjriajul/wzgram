import ast
import inspect
import re
import struct
import subprocess
import sys
import textwrap
import typing
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import pyrogram
from pyrogram import raw, enums, types
from pyrogram.dispatcher import Dispatcher
from pyrogram.handlers import MessageGenerationStoppedHandler
from pyrogram.raw.core import TLObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler" / "methods"))
from compiler import parse_tl_functions
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler" / "botapi"))
from coverage import ENUM_REFERENCE_RE, Coverage, documented_params, enumerated_values


# Verify every ``raw.*`` name referenced by hand-written code exists.
#
# Raw function and type names are PascalCase. A camelCase typo
# (``messages.getPollResults`` instead of ``messages.GetPollResults``) parses
# fine and only blows up as an ``AttributeError`` the first time the method is
# actually called, so it survives review and reaches users.
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pyrogram"
GENERATED = PACKAGE / "raw"


def dotted(node: ast.Attribute):
    parts = []

    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value

    if not isinstance(node, ast.Name):
        return None

    parts.append(node.id)

    return list(reversed(parts))


def raw_references():
    for path in sorted(PACKAGE.rglob("*.py")):
        if GENERATED in path.parents:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue

            parts = dotted(node)

            if parts and parts[0] == "raw" and len(parts) >= 3:
                yield path.relative_to(ROOT), node.lineno, parts[1:]


@pytest.mark.parametrize(
    "path,lineno,parts",
    list(raw_references()),
    ids=lambda v: str(v) if not isinstance(v, list) else ".".join(v)
)
def test_raw_reference_resolves(path, lineno, parts):
    obj = raw

    for part in parts:
        obj = getattr(obj, part, None)

        assert obj is not None, f"{path}:{lineno} references raw.{'.'.join(parts)}, which does not exist"
TL_SOURCE = ROOT / "compiler" / "api" / "source" / "main_api.tl"
TL = parse_tl_functions(TL_SOURCE)


# TL scalars we can recognise in a literal argument
SCALARS = {"int", "long", "double", "string", "bytes", "Bool", "true", "int128", "int256"}
COMPATIBLE = {
    "int": {"int", "long", "true", "Bool"},
    "long": {"int", "long"},
    "double": {"double", "int", "long"},
    "string": {"string"},
    "bytes": {"bytes"},
    "Bool": {"Bool", "true"},
    "true": {"Bool", "true"},
}


def tl_name(parts):
    """raw.types.InputMediaPoll -> inputMediaPoll, raw.functions.messages.X -> messages.x"""
    namespace, name = parts[:-1], parts[-1]

    return ".".join([*namespace, name[:1].lower() + name[1:]])


def literal_kind(node):
    """A coarse TL type for an argument we can be sure about, else None."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "Bool"
        if isinstance(node.value, bytes):
            return "bytes"
        if isinstance(node.value, int):
            return "int"
        if isinstance(node.value, str):
            return "string"

        return None

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in ("bytes", "bytearray"):
            return "bytes"
        if node.func.id == "int":
            return "int"
        if node.func.id == "str":
            return "string"

        return None

    if isinstance(node, (ast.List, ast.Tuple)):
        kinds = {literal_kind(element) for element in node.elts}

        if len(kinds) == 1 and None not in kinds:
            return f"Vector<{kinds.pop()}>"

        return None

    if isinstance(node, ast.ListComp):
        kind = literal_kind(node.elt)

        return f"Vector<{kind}>" if kind else None

    return None


def dotted_raw_argument_types(node):
    parts = []

    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value

    if not isinstance(node, ast.Name):
        return None

    parts.append(node.id)

    return list(reversed(parts))


def local_kinds(scope):
    """Locals assigned exactly one recognisable literal, within one function.

    The argument is rarely a literal at the call site: send_poll built its
    correct_answers into a variable first, and passing the name is what hid the
    type error from a purely literal check.
    """
    assigned = {}

    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        else:
            continue

        kind = literal_kind(node.value) if node.value is not None else None

        if kind is None:
            # an unrecognisable value, or a bare None for an optional field,
            # tells us nothing; it must not cancel a branch we could read
            continue

        for target in targets:
            assigned.setdefault(target.id, set()).add(kind)

    return {
        name: next(iter(kinds)) for name, kinds in assigned.items() if len(kinds) == 1
    }


def scopes(tree):
    """Each function body, plus the module for anything outside one."""
    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    return [*functions, tree]


def raw_arguments():
    """Every hand-written raw constructor argument we can type with confidence."""
    for path in sorted(PACKAGE.rglob("*.py")):
        if GENERATED in path.parents:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))

        for scope in scopes(tree):
            known = local_kinds(scope)

            for node in ast.walk(scope):
                if not isinstance(node, ast.Call):
                    continue

                parts = dotted_raw_argument_types(node.func)

                if not parts or parts[0] != "raw" or len(parts) < 3:
                    continue

                if parts[1] not in ("types", "functions"):
                    continue

                info = TL.get(tl_name(parts[2:]))

                if info is None:
                    continue

                declared = {param["name"]: param["type"] for param in info["params"]}

                for keyword in node.keywords:
                    if keyword.arg is None:
                        continue

                    expected = declared.get(keyword.arg)
                    actual = literal_kind(keyword.value)

                    if actual is None and isinstance(keyword.value, ast.Name):
                        actual = known.get(keyword.value.id)

                    if expected is None or actual is None:
                        continue

                    yield (
                        str(path.relative_to(ROOT)),
                        keyword.value.lineno,
                        ".".join(parts[1:]),
                        keyword.arg,
                        expected,
                        actual,
                    )


def mismatched():
    for path, lineno, target, field, expected, actual in raw_arguments():
        expected_inner = re.fullmatch(r"Vector<(\w+)>", expected)
        actual_inner = re.fullmatch(r"Vector<(\w+)>", actual)

        if bool(expected_inner) != bool(actual_inner):
            continue

        if expected_inner:
            expected, actual = expected_inner.group(1), actual_inner.group(1)

        if expected not in SCALARS or actual not in SCALARS:
            continue

        if actual in COMPATIBLE.get(expected, {expected}):
            continue

        yield path, lineno, target, field, expected, actual
CASES = list(mismatched())


def test_the_schema_was_read():
    assert len(list(raw_arguments())) > 50, (
        "no raw constructor arguments were typed, so this check proves nothing; "
        "run `poe api` first"
    )


@pytest.mark.parametrize(
    "path,lineno,target,field,expected,actual",
    CASES,
    ids=[f"{t}.{f}" for _, _, t, f, _, _ in CASES]
)
def test_no_literal_contradicts_the_schema(path, lineno, target, field, expected, actual):
    """A literal of the wrong TL type only fails when the request is serialised.

    send_poll built its correct_answers as bytes long after layer 228 changed the
    field to Vector<int>, so every quiz poll died in Int.__new__ with 'bytes'
    object has no attribute 'to_bytes'.
    """
    pytest.fail(
        f"{path}:{lineno} passes {target}.{field} a {actual} "
        f"where the schema declares {expected}"
    )


# what an import legitimately pulls: the update types the dispatcher maps, and the
# constructors the enums and filters hold by value. A ceiling and a share of the
# schema, so the guard keeps meaning as the schema grows.
BUDGET = 250
SHARE = 0.1


def run(code):
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr

    return result.stdout.strip().splitlines()


def loaded(extra=""):
    return int(
        run(
            f"""
            import sys
            import pyrogram
            {extra}
            print(len([
                m for m in sys.modules
                if m.startswith(("pyrogram.raw.types.", "pyrogram.raw.functions.",
                                 "pyrogram.raw.base."))
            ]))
            """
        )[-1]
    )


def test_importing_pyrogram_loads_almost_none_of_the_schema():
    count = loaded()
    total = len(list((ROOT / "pyrogram" / "raw").rglob("*.py")))

    assert count < BUDGET and count < total * SHARE, (
        f"importing pyrogram pulled {count} of {total} schema modules; the packages "
        f"under pyrogram/raw are meant to resolve names on first use"
    )


def test_the_schema_is_still_large():
    """A budget is worthless if there is nothing to be under it."""

    total = len(list((ROOT / "pyrogram" / "raw" / "types").rglob("*.py")))

    assert total > 1000, f"only {total} type modules; run poe api"


def test_a_name_loads_only_its_own_module():
    before, after = run(
        """
        import sys
        import pyrogram
        from pyrogram import raw

        def n():
            return len([m for m in sys.modules if m.startswith("pyrogram.raw.types.")])

        print(n())
        raw.types.Message
        print(n())
        """
    )

    assert int(after) - int(before) == 1


@pytest.mark.parametrize(
    "expression",
    [
        "raw.types.Message",
        "raw.functions.messages.SendMessage",
        "raw.base.Message",
        "raw.types.messages.Messages",
    ],
)
def test_every_kind_of_name_still_resolves(expression):
    assert run(
        f"""
        from pyrogram import raw
        print({expression} is not None)
        """
    ) == ["True"]


def test_a_name_the_schema_does_not_have_raises_attribute_error():
    assert run(
        """
        from pyrogram import raw

        try:
            raw.types.NoSuchConstructor
        except AttributeError as e:
            print("AttributeError", "NoSuchConstructor" in str(e))
        """
    ) == ["AttributeError True"]


def test_a_star_import_still_works():
    """__all__ is what makes one possible once the module imports lazily."""

    assert run(
        """
        ns = {}
        exec("from pyrogram.raw.types import *", ns)
        print(ns["Message"].__name__, len(ns) > 1000)
        """
    ) == ["Message True"]


def test_dir_lists_the_whole_package():
    assert run(
        """
        from pyrogram import raw
        names = dir(raw.types)
        print("Message" in names, len(names) > 1000)
        """
    ) == ["True True"]


class TestObjects:
    """The constructor id map resolves an id when it arrives, not before."""

    def test_a_lookup_imports_one_module(self):
        before, after, name = run(
            """
            import sys
            from pyrogram import raw

            def n():
                return len([m for m in sys.modules if m.startswith("pyrogram.raw.types.")])

            print(n())
            cls = raw.objects[0x7600B9D3]
            print(n())
            print(cls.__name__)
            """
        )

        assert int(after) - int(before) == 1
        assert name == "Message"

    def test_it_still_looks_like_the_whole_map(self):
        assert run(
            """
            from pyrogram import raw
            from pyrogram.raw.all import objects

            print(len(raw.objects) == len(objects))
            print(0x7600B9D3 in raw.objects)
            print(raw.objects.get(0xdeadbeef) is None)
            print(len(list(iter(raw.objects))) == len(objects))
            """
        ) == ["True", "True", "True", "True"]

    def test_an_unknown_id_raises_key_error(self):
        assert run(
            """
            from pyrogram import raw

            try:
                raw.objects[0xdeadbeef]
            except KeyError:
                print("KeyError")
            """
        ) == ["KeyError"]

    def test_a_class_put_in_the_map_by_hand_still_works(self):
        """all.objects was a live dict of classes before this became lazy."""

        assert run(
            """
            from io import BytesIO
            from pyrogram.raw.all import objects
            from pyrogram.raw.core import TLObject

            class Probe:
                @staticmethod
                def read(b, *args):
                    return "ok"

            objects[0x7E571234] = Probe
            print(TLObject.read(BytesIO((0x7E571234).to_bytes(4, "little"))))
            """
        ) == ["ok"]


def test_the_compiler_emits_the_lazy_form():
    """poe api regenerates these packages, so the shape has to come from there."""

    source = (ROOT / "compiler" / "api" / "compiler.py").read_text(encoding="utf-8")

    assert "def __getattr__(name):" in source
    assert "_names" in source and "_subpackages" in source
    assert "from .{snake(module)} import" not in source, (
        "the compiler writes eager imports again"
    )


# Every generated class must put on the wire exactly what the TL schema says.
#
# A round-trip test only proves a class agrees with itself: a field written in the
# wrong order, at the wrong width, or under the wrong flag bit still reads back
# cleanly when read() repeats write()'s mistake. So these tests decode what each
# class emits using nothing but the .tl definition, and the schema is the judge.
SOURCE = ROOT / "compiler" / "api" / "source"
TL_SOURCES = [SOURCE / "auth_key.tl", SOURCE / "sys_msgs.tl", SOURCE / "main_api.tl"]
COMBINATOR_RE = re.compile(r"^([\w.]+)#([0-9a-f]+)\s(?:.*)=\s([\w<>.]+);$")
ARGS_RE = re.compile(r"[^{](\w+):([\w?!.<>#]+)")
FLAG_RE = re.compile(r"^flags(\d?)\.(\d+)\?(.+)$")
RENAME = {"self": "is_self", "from": "from_peer"}


def camel(name):
    """The generator's own name rule: p_q_inner_data -> PQInnerData."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_"))


def parse_schema():
    out = []

    for source in TL_SOURCES:
        section = "types"

        for line in source.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if line in ("---functions---", "---types---"):
                section = line.strip("-")
                continue

            if not line or line.startswith("//"):
                continue

            match = COMBINATOR_RE.match(line)

            if not match:
                continue

            qualname, constructor_id, _ = match.groups()
            args = [(RENAME.get(name, name), kind)
                    for name, kind in ARGS_RE.findall(line)]

            out.append((section, qualname, int(constructor_id, 16), args))

    return out
SCHEMA = parse_schema()


def python_qualname(section, qualname):
    if "." in qualname:
        namespace, name = qualname.rsplit(".", 1)
        return "{}.{}.{}".format(section, namespace, camel(name))

    return "{}.{}".format(section, camel(qualname))


def lookup(section, qualname):
    module = raw.functions if section == "functions" else raw.types
    parts = qualname.split(".")

    for part in parts[:-1]:
        module = getattr(module, part, None)

        if module is None:
            return None

    return getattr(module, camel(parts[-1]), None)


class Desync(Exception):
    """The bytes stopped lining up with the definition."""


def r_int(b):
    data = b.read(4)

    if len(data) != 4:
        raise Desync("ran out reading int")

    return struct.unpack("<i", data)[0]


def r_long(b):
    data = b.read(8)

    if len(data) != 8:
        raise Desync("ran out reading long")

    return struct.unpack("<q", data)[0]


def r_double(b):
    data = b.read(8)

    if len(data) != 8:
        raise Desync("ran out reading double")

    return struct.unpack("<d", data)[0]


def r_big(b, size):
    data = b.read(size)

    if len(data) != size:
        raise Desync("ran out reading int{}".format(size * 8))

    return int.from_bytes(data, "little")


def r_bytes(b):
    head = b.read(1)

    if not head:
        raise Desync("ran out reading string length")

    length = head[0]
    total = length + 1

    if length > 253:
        length = int.from_bytes(b.read(3), "little")
        total = length + 4

    body = b.read(length)

    if len(body) != length:
        raise Desync("ran out reading string body")

    b.read(-total % 4)

    return body


def r_bool(b):
    value = r_int(b) & 0xFFFFFFFF

    if value == 0x997275B5:
        return True

    if value == 0xBC799737:
        return False

    raise Desync("expected Bool, got {:08x}".format(value))
PRIMITIVES = {
    "int": r_int,
    "long": r_long,
    "double": r_double,
    "int128": lambda b: r_big(b, 16),
    "int256": lambda b: r_big(b, 32),
    "string": lambda b: r_bytes(b).decode("utf-8", "replace"),
    "bytes": r_bytes,
    "Bool": r_bool,
}


def read_typed(b, kind):
    if kind in PRIMITIVES:
        return PRIMITIVES[kind](b)

    if kind == "Object":
        return TLObject.read(b)

    if kind.lower().startswith("vector<"):
        inner = kind[kind.index("<") + 1:-1]
        constructor_id = r_int(b) & 0xFFFFFFFF

        if constructor_id != 0x1CB5C415:
            raise Desync("expected a vector, got {:08x}".format(constructor_id))

        count = r_int(b)

        if not 0 <= count <= 10000:
            raise Desync("implausible vector count {}".format(count))

        return [read_typed(b, inner) for _ in range(count)]

    return TLObject.read(b)


def decode(b, args, constructor_id):
    got = r_int(b) & 0xFFFFFFFF

    if got != constructor_id:
        raise Desync("constructor id {:08x}, schema says {:08x}".format(
            got, constructor_id))

    flags = {}
    values = {}

    for name, kind in args:
        if kind == "#" and name.startswith("flags"):
            flags[name[len("flags"):]] = r_int(b)
            continue

        match = FLAG_RE.match(kind)

        if match:
            group, bit, inner = match.group(1), int(match.group(2)), match.group(3)

            if group not in flags:
                raise Desync("{} reads flags{} before it was declared".format(
                    name, group))

            present = bool(flags[group] & (1 << bit))
            values[name] = present if inner == "true" else (
                read_typed(b, inner) if present else None)
            continue

        if kind.startswith("!"):
            values[name] = TLObject.read(b)
            continue

        values[name] = read_typed(b, kind)

    return values


class Unbuildable(Exception):
    pass
counter = [0]


def fresh():
    counter[0] += 1

    return counter[0] % 1000000 + 7
BUILTINS = {"bytes": bytes, "int": int, "str": str, "bool": bool, "float": float}
VALUES = {
    int: fresh,
    str: lambda: "s{}".format(fresh()),
    bytes: lambda: "b{}".format(fresh()).encode(),
    bool: lambda: True,
    float: lambda: 1.5,
}


def unwrap(annotation):
    if inspect.ismemberdescriptor(annotation) and annotation.__name__ in BUILTINS:
        return "prim", BUILTINS[annotation.__name__]

    if isinstance(annotation, str):
        return "base", annotation

    if isinstance(annotation, typing.ForwardRef):
        return "base", annotation.__forward_arg__

    origin = typing.get_origin(annotation)

    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]

        if len(args) == 1:
            return unwrap(args[0])

    if origin is list:
        return "list", typing.get_args(annotation)[0]

    if annotation in VALUES:
        return "prim", annotation

    if annotation is typing.Any or annotation is TLObject:
        return "any", None

    raise Unbuildable("annotation {!r}".format(annotation))


def params_of(cls):
    return [p for name, p in inspect.signature(cls.__init__).parameters.items()
            if name != "self"]


def base_key(name):
    return name[len("raw.base."):] if name.startswith("raw.base.") else name


def concretes_by_base():
    """base name -> its constructors, read off the generated Union lines."""
    union_re = re.compile(r"^(\w+) = Union\[(.+)\]$", re.M)
    alias_re = re.compile(r"^(\w+) = raw\.types\.([\w.]+)$", re.M)
    out = {}

    import pkgutil

    for module in pkgutil.walk_packages(raw.base.__path__, raw.base.__name__ + "."):
        __import__(module.name)
        source = inspect.getsource(__import__("sys").modules[module.name])
        short = module.name[len("pyrogram.raw.base."):]
        namespace = short.rsplit(".", 1)[0] + "." if "." in short else ""

        for name, body in union_re.findall(source):
            out[namespace + name] = [
                part.strip()[len("raw.types."):] for part in body.split(",")]

        for name, target in alias_re.findall(source):
            out.setdefault(namespace + name, [target])

    return out


def resolve(name):
    module = raw.types
    parts = name.split(".")

    for part in parts[:-1]:
        module = getattr(module, part, None)

        if module is None:
            return None

    return getattr(module, parts[-1], None)
BASES = concretes_by_base()
SIMPLEST = {}
_pending = dict(BASES)
for _ in range(60):
    _progress = False

    for _base in list(_pending):
        _best = None

        for _name in _pending[_base]:
            _cls = resolve(_name)

            if _cls is None:
                continue

            _needs = set()

            for _param in params_of(_cls):
                if _param.default is not inspect.Parameter.empty:
                    continue

                try:
                    _kind, _payload = unwrap(_param.annotation)
                except Unbuildable:
                    _needs.add("?")
                    continue

                if _kind == "base":
                    _needs.add(base_key(_payload))
                elif _kind == "list":
                    try:
                        _k2, _p2 = unwrap(_payload)
                    except Unbuildable:
                        _needs.add("?")
                        continue

                    if _k2 == "base":
                        _needs.add(base_key(_p2))

            if not all(n in SIMPLEST for n in _needs):
                continue

            _score = (len(_needs), len(params_of(_cls)))

            if _best is None or _score < _best[0]:
                _best = (_score, _cls)

        if _best is not None:
            SIMPLEST[_base] = _best[1]
            del _pending[_base]
            _progress = True

    if not _progress:
        break
for _base, _names in _pending.items():
    _found = [resolve(n) for n in _names]
    _found = [c for c in _found if c is not None]

    if _found:
        SIMPLEST[_base] = min(_found, key=lambda c: len(params_of(c)))


def synth(annotation, depth):
    if depth > 12:
        raise Unbuildable("nested too deep")

    kind, payload = unwrap(annotation)

    if kind == "prim":
        return VALUES[payload]()

    if kind == "any":
        return raw.functions.help.GetConfig()

    if kind == "base":
        cls = SIMPLEST.get(base_key(payload))

        if cls is None:
            raise Unbuildable("no constructor for {}".format(payload))

        return build(cls, full=False, depth=depth + 1)

    inner_kind, inner = unwrap(payload)

    if inner_kind == "prim":
        return [VALUES[inner]() for _ in range(2)]

    if inner_kind == "any":
        return [raw.functions.help.GetConfig()]

    cls = SIMPLEST.get(base_key(inner))

    if cls is None:
        raise Unbuildable("no constructor for {}".format(inner))

    return [build(cls, full=False, depth=depth + 1)]


def build(cls, full, depth=0):
    kwargs = {}

    for param in params_of(cls):
        if param.default is not inspect.Parameter.empty and not full:
            continue

        kwargs[param.name] = synth(param.annotation, depth)

    return cls(**kwargs)


def matches(sent, got):
    if isinstance(sent, list):
        return (isinstance(got, list) and len(sent) == len(got)
                and all(matches(a, b) for a, b in zip(sent, got)))

    if isinstance(sent, TLObject):
        return isinstance(got, TLObject) and type(sent) is type(got)

    if isinstance(sent, float):
        return abs(sent - got) < 1e-9

    return sent == got


def test_the_schema_was_read_schema_conformance():
    assert len(SCHEMA) > 2000, "main_api.tl should hold thousands of combinators"


@pytest.mark.parametrize("full", [False, True], ids=["required", "every-field"])
@pytest.mark.parametrize(
    "section,qualname,constructor_id,args",
    SCHEMA,
    ids=[python_qualname(s, q) for s, q, _, _ in SCHEMA],
)
def test_a_class_writes_what_the_schema_declares(
        section, qualname, constructor_id, args, full):
    cls = lookup(section, qualname)

    assert cls is not None, "{} has no generated class".format(qualname)
    assert cls.ID & 0xFFFFFFFF == constructor_id, (
        "{} carries id {:08x}, the schema says {:08x}".format(
            qualname, cls.ID & 0xFFFFFFFF, constructor_id))

    try:
        specimen = build(cls, full=full)
    except Unbuildable as reason:
        pytest.fail("could not build a {}: {}".format(qualname, reason))

    payload = specimen.write()
    stream = BytesIO(payload)
    values = decode(stream, args, constructor_id)

    assert stream.tell() == len(payload), (
        "{} wrote {} bytes the schema does not account for".format(
            qualname, len(payload) - stream.tell()))

    for name, _ in args:
        if name not in values:
            continue

        sent = getattr(specimen, name)
        got = values[name]

        if sent is None and got in (False, None, []):
            continue

        assert matches(sent, got), (
            "{}.{} was set to {!r} but the wire holds {!r}".format(
                qualname, name, sent, got))
BY_NAME = {q: (c, a) for _, q, c, a in SCHEMA}


def test_the_decoder_notices_a_wrong_constructor_id():
    constructor_id, args = BY_NAME["updateDeleteMessages"]
    honest = build(lookup("types", "updateDeleteMessages"), full=False).write()

    with pytest.raises(Desync, match="constructor id"):
        decode(BytesIO(b"\xef\xbe\xad\xde" + honest[4:]), args, constructor_id)


def test_the_decoder_notices_a_field_of_the_wrong_width():
    from pyrogram.raw.core.primitives import Int, Long

    constructor_id, args = BY_NAME["updateDeleteMessages"]
    payload = (Int(constructor_id, False) + b"\x15\xc4\xb5\x1c" + Int(1) + Int(9)
               + Long(77) + Int(88))
    stream = BytesIO(payload)
    decode(stream, args, constructor_id)

    assert stream.tell() != len(payload), "the extra four bytes should be left over"


def test_the_decoder_notices_a_missing_field():
    from pyrogram.raw.core.primitives import Int

    constructor_id, args = BY_NAME["updateDeleteMessages"]
    payload = Int(constructor_id, False) + b"\x15\xc4\xb5\x1c" + Int(1) + Int(9) + Int(77)

    with pytest.raises(Desync, match="ran out"):
        decode(BytesIO(payload), args, constructor_id)


def test_the_decoder_notices_a_value_hung_on_the_wrong_flag_bit():
    from pyrogram.raw.core.primitives import Int, String

    constructor_id, args = BY_NAME["inputMediaPhotoExternal"]

    honest = Int(constructor_id, False) + Int(1 << 0) + String("u") + Int(30)
    stream = BytesIO(honest)
    values = decode(stream, args, constructor_id)

    assert values["ttl_seconds"] == 30
    assert stream.tell() == len(honest)

    moved = Int(constructor_id, False) + Int(1 << 1) + String("u") + Int(30)
    stream = BytesIO(moved)
    decode(stream, args, constructor_id)

    assert stream.tell() != len(moved), "the orphaned value should be left over"


def test_every_generated_class_has_a_schema_entry_and_the_reverse():
    """A class with no definition behind it is a leftover from an older layer."""
    import pkgutil
    import sys as _sys

    generated = set()

    for package, section in ((raw.types, "types"), (raw.functions, "functions")):
        for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            __import__(module.name)

            for value in vars(_sys.modules[module.name]).values():
                if (inspect.isclass(value) and issubclass(value, TLObject)
                        and value is not TLObject and hasattr(value, "ID")
                        and value.__module__ == module.name):
                    generated.add(value.QUALNAME)

    declared = {python_qualname(section, qualname)
                for section, qualname, _, _ in SCHEMA}

    assert not generated - declared, (
        "generated classes with no schema line: {}".format(
            sorted(generated - declared)[:10]))
    assert not declared - generated, (
        "schema lines with no generated class: {}".format(
            sorted(declared - generated)[:10]))


def test_a_vector_of_primitives_always_carries_its_element_type():
    """The invariant `Vector.read` leans on when no element type is given.

    Told nothing about its elements, `Vector.read` treats them as objects,
    which is only right because the generator names the type for every vector
    of numbers or strings. A layer that broke that would decode silently wrong,
    so check it rather than trust it.
    """
    primitives = {"int", "long", "double", "int128", "int256",
                  "string", "bytes", "Bool"}
    untyped = []

    for section, qualname, _, args in SCHEMA:
        cls = lookup(section, qualname)

        if cls is None:
            continue

        for name, kind in args:
            match = FLAG_RE.match(kind)
            inner_of = match.group(3) if match else kind

            if not inner_of.lower().startswith("vector<"):
                continue

            if inner_of[inner_of.index("<") + 1:-1] not in primitives:
                continue

            body = inspect.getsource(cls).split("def read(", 1)[1].split("def write(", 1)[0]
            line = re.search(r"^\s*{} = (.+?)$".format(re.escape(name)), body, re.M)

            if line and not re.search(r"TLObject\.read\(b,\s*\w+\)", line.group(1)):
                untyped.append("{}.{} reads {}".format(qualname, name, line.group(1)))

    assert not untyped, (
        "these vectors of primitives are read with no element type, so "
        "Vector.read would take them for objects: {}".format(untyped[:10]))


# The Bot API 10.3 surface, which arrived with MTProto layer 229.
#
# Every case here is a field or constructor that has one shape in Bot API and
# another in the TL schema, which is the seam a parameter goes missing at.
def _raw_user(user_id, first_name="U"):
    return raw.types.User(
        id=user_id, first_name=first_name, usernames=[], restriction_reason=[]
    )


class TestRichMessageButton:
    """A rich button and a keyboard button are one MTProto union and two Bot API types."""

    def test_it_writes_a_page_button(self):
        button = types.RichMessageButton(text="Go", url="https://example.org")
        written = button.write()

        assert isinstance(written, raw.types.PageButton)
        assert isinstance(written.type, raw.types.InlineButtonTypeUrl)
        assert written.type.url == "https://example.org"

    def test_it_writes_a_text_button(self):
        written = types.RichMessageButton(text="Go", callback_data="d").write_text()

        assert isinstance(written, raw.types.TextButton)
        assert written.type.data == b"d"

    def test_a_login_url_needs_no_resolved_bot(self):
        """A rich block writes synchronously, and layer 229 made the bot optional."""

        written = types.RichMessageButton(
            text="Log in", login_url=types.LoginUrl(url="https://example.org")
        ).write()

        assert isinstance(written.type, raw.types.InputInlineButtonTypeUrlAuth)
        assert written.type.bot is None

    @pytest.mark.parametrize(
        "style,flag",
        [
            (enums.RichButtonStyle.LINK, "link"),
            (enums.RichButtonStyle.PRIMARY, "bg_primary"),
            (enums.RichButtonStyle.DANGER, "bg_danger"),
            (enums.RichButtonStyle.SUCCESS, "bg_success"),
        ],
    )
    def test_every_style_round_trips(self, style, flag):
        written = types.RichMessageButton(text="x", url="u", style=style).write()

        assert getattr(written.style, flag) is True
        assert types.RichMessageButton._parse_style(written.style) == style

    def test_the_default_style_writes_nothing(self):
        assert types.RichMessageButton(text="x", url="u").write().style is None
        assert (
            types.RichMessageButton._parse_style(None) == enums.RichButtonStyle.DEFAULT
        )

    async def test_it_parses_back(self):
        page_button = raw.types.PageButton(
            text=raw.types.TextPlain(text="Copy"),
            type=raw.types.InlineButtonTypeCopy(copy_text="hello"),
            style=raw.types.RichButtonStyle(bg_danger=True),
        )
        parsed = await types.RichMessageButton._parse(Mock(), page_button)

        assert parsed.text == "Copy"
        assert parsed.copy_text.text == "hello"
        assert parsed.style == enums.RichButtonStyle.DANGER

    async def test_a_keyboard_only_member_is_dropped_rather_than_passed_on(self):
        """RichMessageButton has no pay field, and the union it shares does."""

        page_button = raw.types.PageButton(
            text=raw.types.TextPlain(text="Buy"),
            type=raw.types.InlineButtonTypeBuy(),
        )

        parsed = await types.RichMessageButton._parse(Mock(), page_button)

        assert not hasattr(parsed, "pay")


class TestInstantViewBlocks:
    def test_a_button_row_carries_its_alignment(self):
        block = types.InputRichBlockButtons(
            buttons=[types.RichMessageButton(text="a", url="u")],
            align=enums.BlockAlignment.CENTER,
        ).write()

        assert isinstance(block, raw.types.PageBlockButtonRow)
        assert block.align_center is True
        assert block.align_left is None
        assert block.align_right is None

    def test_an_unaligned_row_sets_no_flag(self):
        block = types.InputRichBlockButtons(
            buttons=[types.RichMessageButton(text="a", url="u")]
        ).write()

        assert (block.align_left, block.align_center, block.align_right) == (
            None,
            None,
            None,
        )

    def test_an_expandable_quotation_is_a_collapsed_blockquote(self):
        block = types.InputRichBlockExpandableBlockQuotation(
            blocks=[types.InputRichBlockParagraph(text="hi")]
        ).write()

        assert isinstance(block, raw.types.PageBlockBlockquoteBlocks)
        assert block.collapsed is True
        assert isinstance(block.blocks[0], raw.types.PageBlockParagraph)

    @pytest.mark.parametrize(
        "block",
        [
            lambda: types.InputRichBlockExpandableBlockQuotation(text="hi"),
            lambda: types.InputRichBlockExpandableBlockQuotation("hi"),
        ],
    )
    def test_an_expandable_quotation_still_takes_text(self, block):
        written = block().write()

        assert isinstance(written, raw.types.PageBlockBlockquote)
        assert written.collapsed is True

    def test_a_plain_quotation_is_not_collapsed(self):
        block = types.InputRichBlockBlockQuotation(blocks=[]).write()

        assert getattr(block, "collapsed", None) is None

    def test_a_document_block_writes_its_identifier(self):
        block = types.InputRichBlockDocument(document_id=7, caption="c").write()

        assert isinstance(block, raw.types.PageBlockDocument)
        assert block.document_id == 7

    def test_a_compact_table_sets_the_flag(self):
        block = types.InputRichBlockTable(title="t", rows=[], compact=True).write()

        assert block.compact is True

    async def test_a_collapsed_blockquote_parses_as_expandable(self):
        block = await types.RichBlock._parse(
            Mock(),
            raw.types.PageBlockBlockquote(
                text=raw.types.TextPlain(text="quote"),
                caption=raw.types.TextPlain(text="who"),
                collapsed=True,
            ),
        )

        assert isinstance(block, types.RichBlockExpandableBlockQuotation)
        assert block.blocks[0].text == "quote"

        plain = await types.RichBlock._parse(
            Mock(),
            raw.types.PageBlockBlockquote(
                text=raw.types.TextPlain(text="quote"),
                caption=raw.types.TextPlain(text="who"),
            ),
        )

        assert isinstance(plain, types.RichBlockBlockQuotation)

    @pytest.mark.parametrize(
        ("collapsed", "kind"),
        [(True, types.RichBlockExpandableBlockQuotation), (None, types.RichBlockBlockQuotation)],
    )
    async def test_quoted_blocks_parse_by_their_collapsed_flag(self, collapsed, kind):
        block = await types.RichBlock._parse(
            Mock(),
            raw.types.PageBlockBlockquoteBlocks(
                blocks=[raw.types.PageBlockParagraph(text=raw.types.TextPlain(text="quote"))],
                caption=raw.types.TextPlain(text="who"),
                collapsed=collapsed,
            ),
        )

        assert type(block) is kind
        assert block.blocks[0].text == "quote"

    async def test_a_button_row_parses_with_its_alignment(self):
        block = await types.RichBlock._parse(
            Mock(),
            raw.types.PageBlockButtonRow(
                buttons=[
                    raw.types.PageButton(
                        text=raw.types.TextPlain(text="a"),
                        type=raw.types.InlineButtonTypeUrl(url="u"),
                    )
                ],
                align_right=True,
            ),
        )

        assert isinstance(block, types.RichBlockButtons)
        assert block.align == enums.BlockAlignment.RIGHT
        assert block.buttons[0].url == "u"

    async def test_a_table_parses_its_compact_flag(self):
        block = await types.RichBlock._parse(
            Mock(),
            raw.types.PageBlockTable(
                title=raw.types.TextPlain(text=""), rows=[], compact=True
            ),
        )

        assert block.is_compact is True

    async def test_a_text_button_parses_as_rich_text(self):
        parsed = await types.RichText._parse(
            Mock(),
            raw.types.TextButton(
                text=raw.types.TextPlain(text="press"),
                type=raw.types.InlineButtonTypeCallback(data=b"d"),
            ),
        )

        assert isinstance(parsed, types.RichTextButton)
        assert parsed.button.callback_data == "d"


class TestWelcomeMessages:
    """chatAdminRights.manage_welcome_messages, and the three welcome RPCs."""

    def test_the_admin_right_survives_a_round_trip(self):
        from pyrogram.types.bots_and_keyboards.keyboard_button import _admin_rights

        rights = types.ChatAdministratorRights(can_send_welcome_messages=True)
        raw_rights = _admin_rights(rights)

        assert raw_rights.manage_welcome_messages is True
        assert (
            types.ChatAdministratorRights._parse(raw_rights).can_send_welcome_messages
            is True
        )

    @pytest.mark.parametrize(
        "path",
        [
            "pyrogram/methods/chats/promote_chat_member.py",
            "pyrogram/methods/bots/set_bot_default_privileges.py",
        ],
    )
    def test_every_admin_rights_writer_sends_the_flag(self, path):
        """A writer that forgets it silently demotes the right on every edit."""

        source = (ROOT / path).read_text(encoding="utf-8")

        assert "manage_welcome_messages=privileges.can_send_welcome_messages" in source

    @pytest.mark.parametrize(
        "method,function",
        [
            ("get_welcome_messages", "GetWelcomeMessages"),
            ("delete_welcome_message", "DeleteWelcomeMessage"),
            ("delete_all_welcome_messages", "DeleteAllWelcomeMessages"),
        ],
    )
    def test_each_method_calls_its_own_rpc(self, method, function):
        import pyrogram

        source = inspect.getsource(getattr(pyrogram.Client, method))

        assert f"raw.functions.ephemeral.{function}(" in source

    def test_send_ephemeral_message_threads_every_new_flag(self):
        """The flags are set on both branches, and the rich one is easy to miss."""

        import pyrogram

        source = inspect.getsource(pyrogram.Client.send_ephemeral_message)
        tree = ast.parse(inspect.cleandoc(source))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "SendMessage"
        ]

        assert len(calls) == 2, "the plain and rich branches each build one"

        for call in calls:
            names = {kw.arg for kw in call.keywords}

            assert {"welcome", "anchor", "invert_media", "noforwards"} <= names


class TestMessageGenerationStopped:
    def test_the_dispatcher_routes_every_typing_update(self):
        for update in (
            raw.types.UpdateUserTyping,
            raw.types.UpdateChatUserTyping,
            raw.types.UpdateChannelUserTyping,
        ):
            assert update in Dispatcher.TYPING_UPDATES

    def test_the_draft_sends_the_stop_flags(self):
        import pyrogram

        source = inspect.getsource(pyrogram.Client.send_rich_message_draft)

        assert "can_stop=can_stop" in source
        assert "keep_on_stop=keep_on_stop" in source

    def test_it_parses_a_stop_action(self):
        update = raw.types.UpdateUserTyping(
            user_id=5,
            action=raw.types.SendMessageStopDraftAction(random_id=99),
            top_msg_id=3,
        )
        parsed = types.MessageGenerationStopped._parse(
            Mock(), update, {5: _raw_user(5)}, {}
        )

        assert parsed.draft_id == 99
        assert parsed.chat.id == 5
        assert parsed.message_thread_id == 3

    def test_any_other_typing_action_is_not_one(self):
        """Every SendMessageAction arrives on these updates, and only one has a handler."""

        update = raw.types.UpdateUserTyping(
            user_id=5, action=raw.types.SendMessageTypingAction()
        )

        assert types.MessageGenerationStopped._parse(Mock(), update, {}, {}) is None

    async def test_an_unrelated_action_matches_no_handler(self):
        dispatcher = Dispatcher(Mock(listeners=None))
        parser = dispatcher.update_parsers[raw.types.UpdateUserTyping]

        parsed, handler_type = await parser(
            raw.types.UpdateUserTyping(
                user_id=5, action=raw.types.SendMessageTypingAction()
            ),
            {},
            {},
        )

        assert parsed is None
        assert handler_type is type(None), (
            "a handler type that matches would call check() with None"
        )

        parsed, handler_type = await parser(
            raw.types.UpdateUserTyping(
                user_id=5, action=raw.types.SendMessageStopDraftAction(random_id=1)
            ),
            {5: _raw_user(5)},
            {},
        )

        assert handler_type is MessageGenerationStoppedHandler


class TestMessageDraft:
    """`sendMessageDraft` streams plain text, `sendRichMessageDraft` streams blocks."""

    @staticmethod
    def _client():
        client = pyrogram.Client.__new__(pyrogram.Client)
        client.invoke = AsyncMock(return_value=True)
        client.resolve_peer = AsyncMock(
            return_value=raw.types.InputPeerUser(user_id=7, access_hash=0)
        )
        client.parser = Mock()
        client.parser.parse = AsyncMock(
            side_effect=lambda text, mode: {"message": text, "entities": None}
        )

        return client

    async def test_it_streams_a_text_draft_action(self):
        client = self._client()

        await pyrogram.Client.send_message_draft(
            client, 7, 42, "hello", message_thread_id=3, can_stop=True, keep_on_stop=True
        )

        request = client.invoke.await_args.args[0]

        assert isinstance(request.action, raw.types.SendMessageTextDraftAction)
        assert request.action.random_id == 42
        assert request.action.text.text == "hello"
        assert request.action.can_stop is True
        assert request.action.keep_on_stop is True
        assert request.top_msg_id == 3
        assert request.write()

    async def test_an_empty_draft_carries_no_entities_rather_than_none(self):
        """textWithEntities has no flag on entities, and Vector(None) raises."""

        client = self._client()

        await pyrogram.Client.send_message_draft(client, 7, 42)

        request = client.invoke.await_args.args[0]

        assert request.action.text.text == ""
        assert request.action.text.entities == []
        assert request.write()


class TestGiftsAndCommunities:
    async def test_a_unique_gift_keeps_its_text_and_hidden_name(self):
        action = raw.types.MessageActionStarGiftUnique(
            gift=raw.types.StarGiftUnique(
                id=1,
                gift_id=1,
                title="t",
                slug="s",
                num=1,
                attributes=[],
                availability_issued=1,
                availability_total=1,
                owner_id=raw.types.PeerUser(user_id=2),
            ),
            name_hidden=True,
            message=raw.types.TextWithEntities(text="for you", entities=[]),
        )

        parsed = await types.Gift._parse_action(Mock(), action)

        assert parsed.is_name_hidden is True
        assert parsed.text.text == "for you"

    def test_the_resale_invoice_carries_a_message(self):
        import pyrogram

        source = inspect.getsource(pyrogram.Client.send_resold_gift)

        assert "show_name=show_name" in source
        assert "message=raw.types.TextWithEntities(" in source

    def test_a_community_join_is_its_own_service_type(self):
        action = raw.types.MessageActionChatJoinedViaCommunity(community_id=42)
        parsed = types.CommunityChatJoined._parse(Mock(), action, {})

        assert parsed.community_id == 42
        assert enums.MessageServiceType.COMMUNITY_CHAT_JOINED
SEND_METHODS = (
    "send_message",
    "send_photo",
    "send_audio",
    "send_document",
    "send_video",
    "send_animation",
    "send_voice",
    "send_video_note",
    "send_location",
    "send_venue",
    "send_contact",
    "send_sticker",
    "send_rich_message",
    "send_cached_media",
)


class TestEphemeralMessageParameters:
    """Bot API 10.3 sends an ephemeral message from an ordinary send method.

    MTProto has a separate RPC, so every send method has to route to it. A method
    that accepts the parameter and still calls messages.sendMedia sends the message
    to the whole chat — the opposite of what was asked for, and no error.
    """

    @staticmethod
    def _client():
        client = AsyncMock()
        client.rnd_id = Mock(return_value=1)
        client.link_preview_options = None
        client.parser.parse = AsyncMock(
            return_value={"message": "hi", "entities": None}
        )
        client.resolve_peer = AsyncMock(
            return_value=raw.types.InputPeerUser(user_id=7, access_hash=0)
        )
        client.invoke.return_value = Mock(updates=[], users=[], chats=[])

        return client

    @pytest.mark.parametrize("method", SEND_METHODS)
    def test_every_send_method_accepts_it(self, method):
        parameters = inspect.signature(
            getattr(pyrogram.Client, method)
        ).parameters

        assert "ephemeral_message_parameters" in parameters

    @pytest.mark.parametrize("method", SEND_METHODS)
    def test_every_send_method_documents_it(self, method):
        doc = getattr(pyrogram.Client, method).__doc__ or ""

        assert "ephemeral_message_parameters (" in doc

    @pytest.mark.parametrize("method", SEND_METHODS)
    def test_every_request_is_routed(self, method):
        """A request built and then sent unrouted goes to the whole chat."""

        source = inspect.getsource(getattr(pyrogram.Client, method))
        builds = source.count("raw.functions.messages.Send")
        routed = source.count("as_ephemeral(self, ephemeral_message_parameters,")

        assert builds and builds == routed, (
            f"{method} builds {builds} send request(s) and routes {routed}"
        )

    @pytest.mark.parametrize("method", SEND_METHODS)
    def test_every_method_reads_the_ephemeral_update(self, method):
        """The answer carries UpdateNewEphemeralMessage, so the parse must accept it."""

        source = inspect.getsource(getattr(pyrogram.Client, method))

        assert "raw.types.UpdateNewEphemeralMessage" in source

    async def test_it_routes_to_the_ephemeral_rpc(self):
        client = self._client()

        await pyrogram.Client.send_message(
            client, 1, "hi",
            ephemeral_message_parameters=types.EphemeralMessageParameters(
                receiver_user_id=7,
                callback_query_id="42",
                replace_callback_query_message=True,
            ),
        )

        request = client.invoke.await_args.args[0]

        assert type(request).__module__.endswith("ephemeral.send_message")
        assert request.query_id == 42
        assert request.anchor is True
        assert request.message == "hi"

    async def test_without_it_nothing_changes(self):
        client = self._client()

        await pyrogram.Client.send_message(client, 1, "hi")

        request = client.invoke.await_args.args[0]

        assert type(request).__module__.endswith("messages.send_message")

    async def test_a_field_the_rpc_has_no_place_for_is_logged(self, caplog):
        """Accepted and silently dropped is the failure this repo keeps fixing."""

        client = self._client()

        with caplog.at_level("WARNING"):
            await pyrogram.Client.send_message(
                client, 1, "hi", disable_notification=True,
                ephemeral_message_parameters=types.EphemeralMessageParameters(
                    receiver_user_id=7
                ),
            )

        assert "silent" in caplog.text

    async def test_a_supported_field_is_not_reported_dropped(self, caplog):
        client = self._client()

        with caplog.at_level("WARNING"):
            await pyrogram.Client.send_message(
                client, 1, "hi",
                ephemeral_message_parameters=types.EphemeralMessageParameters(
                    receiver_user_id=7
                ),
            )

        assert not caplog.text

    async def test_the_media_survives_the_translation(self):
        from pyrogram.methods.ephemeral.as_ephemeral import as_ephemeral

        media = raw.types.InputMediaGeoPoint(
            geo_point=raw.types.InputGeoPoint(lat=1.0, long=2.0)
        )
        request = raw.functions.messages.SendMedia(
            peer=raw.types.InputPeerChat(chat_id=1),
            media=media,
            message="cap",
            random_id=5,
            reply_markup=None,
            reply_to=None,
            invert_media=True,
            noforwards=True,
        )
        client = AsyncMock()
        client.resolve_peer = AsyncMock(
            return_value=raw.types.InputPeerUser(user_id=7, access_hash=0)
        )

        translated = await as_ephemeral(
            client, types.EphemeralMessageParameters(receiver_user_id=7), request
        )

        assert translated.media is media
        assert translated.message == "cap"
        assert translated.random_id == 5
        assert translated.invert_media is True
        assert translated.noforwards is True

    async def test_no_parameters_hands_the_request_straight_back(self):
        from pyrogram.methods.ephemeral.as_ephemeral import as_ephemeral

        request = object()

        assert await as_ephemeral(Mock(), None, request) is request


class TestMisplacedDocstrings:
    """A docstring that is not the first statement is not a docstring.

    send_location and send_venue put the legacy reply_parameters block above theirs,
    so help(), Sphinx and the coverage gate's docstring axis all saw nothing — and the
    axis passes silently when there is no docstring to check.
    """

    @pytest.mark.parametrize("method", SEND_METHODS)
    def test_every_send_method_has_a_real_docstring(self, method):
        doc = getattr(pyrogram.Client, method).__doc__

        assert doc, f"{method} has a docstring the interpreter cannot see"
        assert "Parameters:" in doc
        assert "Returns:" in doc


class TestEditEphemeralMessage:
    """ephemeral.editMessage is new in layer 229.

    Before it there was no way to edit an ephemeral message over MTProto at all,
    which is why four Bot API methods had no wzgram counterpart. All four go
    through one RPC and differ only in which of its optional fields they fill.
    """

    METHODS = (
        "edit_ephemeral_message_text",
        "edit_ephemeral_message_caption",
        "edit_ephemeral_message_media",
        "edit_ephemeral_message_reply_markup",
    )

    @pytest.mark.parametrize("method", METHODS)
    def test_each_one_exists(self, method):
        assert hasattr(pyrogram.Client, method)

    def test_they_share_one_invoke(self):
        """Four copies of a request is how one of them ends up missing a field."""

        sources = [
            inspect.getsource(getattr(pyrogram.Client, m)) for m in self.METHODS
        ]
        builds = [s for s in sources if "raw.functions.ephemeral.EditMessage(" in s]

        assert not builds, "the RPC belongs in edit_ephemeral, not in each method"

        for source in sources:
            assert "edit_ephemeral(" in source

    @staticmethod
    def _client(text=""):
        client = AsyncMock()
        client.invoke.return_value = Mock(updates=[], users=[], chats=[])
        client.parser.parse = AsyncMock(
            return_value={"message": text or None, "entities": None}
        )

        return client

    async def test_the_text_form_sends_text(self):
        client = self._client("hello")

        await pyrogram.Client.edit_ephemeral_message_text(
            client, 1, 2, 3, "hello"
        )

        request = client.invoke.await_args.args[0]

        assert isinstance(request, raw.functions.ephemeral.EditMessage)
        assert request.id == 3
        assert request.message == "hello"
        assert request.rich_message is None

    async def test_the_text_form_prefers_a_rich_message(self):
        client = self._client()

        await pyrogram.Client.edit_ephemeral_message_text(
            client, 1, 2, 3, "ignored",
            rich_message=types.InputRichMessage(html="<b>hi</b>")
        )

        request = client.invoke.await_args.args[0]

        assert request.message is None
        assert isinstance(request.rich_message, raw.types.InputRichMessageHTML)

    async def test_the_caption_form_carries_the_flag(self):
        client = self._client("cap")

        await pyrogram.Client.edit_ephemeral_message_caption(
            client, 1, 2, 3, "cap", show_caption_above_media=True
        )

        request = client.invoke.await_args.args[0]

        assert request.message == "cap"
        assert request.invert_media is True

    async def test_the_reply_markup_form_sends_nothing_else(self):
        client = self._client()

        await pyrogram.Client.edit_ephemeral_message_reply_markup(client, 1, 2, 3)

        request = client.invoke.await_args.args[0]

        assert request.message is None
        assert request.media is None
        assert request.rich_message is None
        assert request.reply_markup is None

    async def test_it_reads_the_ephemeral_update(self):
        """The answer carries UpdateEditEphemeralMessage, not UpdateEditMessage."""

        from pyrogram.methods.ephemeral.edit_ephemeral_message import edit_ephemeral

        message = raw.types.EphemeralMessage(
            id=11,
            from_id=raw.types.PeerUser(user_id=1),
            receiver_id=2,
            date=0,
            message="edited",
            out=True,
        )
        client = AsyncMock()
        client.invoke.return_value = Mock(
            updates=[raw.types.UpdateEditEphemeralMessage(message=message)],
            users=[_raw_user(1), _raw_user(2)],
            chats=[],
        )

        parsed = await edit_ephemeral(client, 1, 2, 11, message="edited")

        assert parsed.id == 11
        assert parsed.text == "edited"

    def test_the_media_form_reuses_the_shared_resolver(self):
        """Two hundred lines of upload handling, not two copies of it."""

        from pyrogram.methods.messages.edit_message_media import resolve_input_media

        assert inspect.iscoroutinefunction(resolve_input_media)

        for method in ("edit_message_media", "edit_ephemeral_message_media"):
            source = inspect.getsource(getattr(pyrogram.Client, method))

            assert "resolve_input_media(" in source
            assert "raw.functions.messages.UploadMedia(" not in source


class TestEphemeralBoundMethods:
    """An ephemeral message is edited and deleted through its own RPCs.

    The ordinary bound methods send messages.editMessage, which is the wrong request
    for one, so the shortcut has to name the receiver again — and refuse when there is
    nobody to name.
    """

    SHORTCUTS = (
        "edit_ephemeral_text",
        "edit_ephemeral_caption",
        "edit_ephemeral_media",
        "edit_ephemeral_reply_markup",
        "delete_ephemeral",
        "reply_ephemeral_text",
    )

    @staticmethod
    def _message(ephemeral=True, receiver=True, sender=True):
        return types.Message(
            id=11,
            chat=types.Chat(id=-100, type=enums.ChatType.SUPERGROUP),
            from_user=types.User(id=5) if sender else None,
            receiver_user=types.User(id=7) if receiver else None,
            ephemeral_message_id=11 if ephemeral else None,
            client=AsyncMock(),
        )

    @pytest.mark.parametrize("name", SHORTCUTS)
    def test_each_one_exists(self, name):
        assert hasattr(types.Message, name)

    def test_the_aliases_point_at_the_long_names(self):
        assert types.Message.edit_ephemeral is types.Message.edit_ephemeral_text
        assert types.Message.reply_ephemeral is types.Message.reply_ephemeral_text

    def test_is_ephemeral_follows_the_identifier(self):
        assert self._message().is_ephemeral is True
        assert self._message(ephemeral=False).is_ephemeral is False

    @pytest.mark.parametrize(
        "call",
        [
            lambda m: m.edit_ephemeral_text("x"),
            lambda m: m.edit_ephemeral_caption("x"),
            lambda m: m.edit_ephemeral_media(None),
            lambda m: m.edit_ephemeral_reply_markup(),
            lambda m: m.delete_ephemeral(),
        ],
    )
    async def test_an_ordinary_message_is_refused(self, call):
        """Sending the ephemeral RPC for a normal message edits nothing."""

        with pytest.raises(ValueError, match="not an ephemeral message"):
            await call(self._message(ephemeral=False))

    async def test_a_message_with_no_receiver_is_refused(self):
        with pytest.raises(ValueError, match="no receiver"):
            await self._message(receiver=False).edit_ephemeral_text("x")

    async def test_the_edit_fills_chat_receiver_and_message(self):
        message = self._message()

        await message.edit_ephemeral_text("hello")

        kwargs = message._client.edit_ephemeral_message_text.await_args.kwargs

        assert kwargs["chat_id"] == -100
        assert kwargs["receiver_id"] == 7
        assert kwargs["message_id"] == 11
        assert kwargs["text"] == "hello"

    async def test_the_delete_fills_the_same_three(self):
        message = self._message()

        await message.delete_ephemeral()

        kwargs = message._client.delete_ephemeral_message.await_args.kwargs

        assert (kwargs["chat_id"], kwargs["receiver_id"], kwargs["message_id"]) == (
            -100, 7, 11
        )

    async def test_a_reply_goes_to_the_sender_and_quotes_the_message(self):
        message = self._message(ephemeral=False)

        await message.reply_ephemeral_text("only you")

        kwargs = message._client.send_ephemeral_message.await_args.kwargs

        assert kwargs["chat_id"] == -100
        assert kwargs["receiver_id"] == 5, "the reply goes to whoever sent the message"
        assert kwargs["reply_parameters"].message_id == 11

    async def test_a_reply_can_name_someone_else(self):
        message = self._message(ephemeral=False)

        await message.reply_ephemeral_text("only you", receiver_id=99)

        assert message._client.send_ephemeral_message.await_args.kwargs["receiver_id"] == 99

    async def test_a_reply_with_nobody_to_address_is_refused(self):
        with pytest.raises(ValueError, match="no sender"):
            await self._message(ephemeral=False, sender=False).reply_ephemeral_text("x")


class TestChatWelcomeMessagesFlag:
    def test_a_full_channel_carries_it(self):
        assert "has_welcome_messages" in inspect.getsource(
            types.Chat._parse_full_channel
        )

    def test_a_full_chat_carries_it(self):
        assert "has_welcome_messages" in inspect.getsource(types.Chat._parse_full_chat)

    def test_it_is_a_documented_parameter(self):
        doc = types.Chat.__doc__

        assert "has_welcome_messages (``bool``, *optional*):" in doc


class TestParsedTextIsRefusedOnInput:
    """A parsed RichText has no write(), and it used to be found by serialising one.

    The high-level types describe a message that arrived. Handing one to an input
    block failed with AttributeError from inside the request, several frames away
    from the call that was actually wrong.
    """

    @pytest.mark.parametrize(
        "block",
        [
            lambda text: types.InputRichBlockParagraph(text=text),
            lambda text: types.InputRichBlockPullQuotation(text=text),
            lambda text: types.InputRichBlockExpandableBlockQuotation(text=text),
        ],
    )
    def test_it_raises_where_it_is_written(self, block):
        with pytest.raises(TypeError, match="raw.types.Text"):
            block(types.RichTextBold(text="x")).write()

    def test_a_rich_button_refuses_one_too(self):
        with pytest.raises(TypeError, match="raw.types.Text"):
            types.RichMessageButton(text=types.RichTextBold(text="x"), url="u").write()

    def test_plain_text_and_raw_text_still_pass(self):
        assert types.InputRichBlockParagraph(text="hi").write().text
        assert types.InputRichBlockParagraph(
            text=raw.types.TextBold(text=raw.types.TextPlain(text="hi"))
        ).write().text

    async def test_a_plain_text_button_round_trips(self):
        """TextPlain parses back to str, which is the one shape that survives."""

        page = raw.types.PageButton(
            text=raw.types.TextPlain(text="Go"),
            type=raw.types.InlineButtonTypeUrl(url="u"),
        )
        parsed = await types.RichMessageButton._parse(Mock(), page)

        assert parsed.write().write()


class TestCommunityLookupIsGuarded:
    """chats is keyed by id across every peer kind, so a community id can miss."""

    def test_a_non_community_resolves_to_nothing(self):
        channel = raw.types.Channel(
            id=42, title="T", photo=raw.types.ChatPhotoEmpty(), date=0
        )
        action = raw.types.MessageActionChatJoinedViaCommunity(community_id=42)

        parsed = types.CommunityChatJoined._parse(Mock(), action, {42: channel})

        assert parsed.community_id == 42
        assert parsed.community is None

    def test_a_community_still_resolves(self):
        community = raw.types.Community(
            id=42, title="T", date=0, photo=raw.types.ChatPhotoEmpty()
        )
        action = raw.types.MessageActionChatJoinedViaCommunity(community_id=42)

        parsed = types.CommunityChatJoined._parse(Mock(), action, {42: community})

        assert parsed.community.title == "T"


class TestForceReply:
    async def test_an_inline_markup_carries_it(self):
        markup = types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="x", url="u")]],
            force_reply=True,
        )
        written = await markup.write(AsyncMock())

        assert written.force_reply is True
        assert types.InlineKeyboardMarkup.read(written).force_reply is True

    async def test_a_reply_markup_carries_it(self):
        written = await types.ReplyKeyboardMarkup(
            keyboard=[["a"]], force_reply=True
        ).write(AsyncMock())

        assert written.force_reply is True
        assert types.ReplyKeyboardMarkup.read(written).force_reply is True

    async def test_it_is_absent_rather_than_false_when_unset(self):
        written = await types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="x", url="u")]]
        ).write(AsyncMock())

        assert written.force_reply is None


class TestDisabledButton:
    async def test_it_is_accepted_and_written(self):
        written = await types.InlineKeyboardButton(
            text="x", disabled=types.DisabledButton()
        ).write(AsyncMock())

        assert isinstance(written.type, raw.types.InlineButtonTypeDisabled)

    async def test_it_reads_back_as_the_type(self):
        button = types.InlineKeyboardButton.read(
            raw.types.KeyboardInlineButton(
                text="x", type=raw.types.InlineButtonTypeDisabled()
            )
        )

        assert isinstance(button.disabled, types.DisabledButton)


class TestPartialRichMessage:
    def _raw(self, part):
        return raw.types.RichMessage(
            blocks=[
                raw.types.PageBlockBlockquoteBlocks(
                    blocks=[
                        raw.types.PageBlockParagraph(
                            text=raw.types.TextPlain(text="hello")
                        )
                    ],
                    caption=raw.types.TextPlain(text=""),
                )
            ],
            photos=[],
            documents=[],
            part=part,
        )

    @pytest.mark.parametrize("part,expected", [(True, True), (False, False)])
    async def test_the_part_flag_reaches_the_parsed_message(self, part, expected):
        parsed = await types.RichMessage._parse(Mock(), self._raw(part))

        assert parsed.is_partial is expected, (
            "a rich message too large to travel inline arrives truncated, and a caller "
            "that cannot see it is one has no reason to call get_rich_message"
        )
        assert parsed.blocks[0].blocks[0].text == "hello"

    def test_the_method_that_fetches_the_whole_one_exists(self):
        assert hasattr(pyrogram.Client, "get_rich_message")

        source = inspect.getsource(pyrogram.Client.get_rich_message)

        assert "raw.functions.messages.GetRichMessage" in source
COVERAGE = Coverage()
PACKAGE_SOURCES = [
    (path, path.read_text(encoding="utf-8"))
    for path in sorted((ROOT / "pyrogram").rglob("*.py"))
]


MANIFEST_FINDINGS = COVERAGE.check_manifest()
DOCSTRING_FINDINGS = COVERAGE.check_docstrings()


def entities(kind):
    entry = COVERAGE.manifest.get(kind) or {}

    return sorted(
        set(entry.get("supported") or []) | set(entry.get("pending") or {})
    )


def findings_for(entity):
    return [f for f in MANIFEST_FINDINGS if f.entity.endswith(f"/{entity}")]


def test_the_manifest_records_a_spec_version():
    assert COVERAGE.manifest.get("version") == COVERAGE.spec["version"], (
        "manifest.yaml was surveyed against a different Bot API release than "
        "compiler/botapi/source/botapi.json ships; run `poe botapi-refresh`"
    )


@pytest.mark.parametrize("name", entities("types"))
def test_type_matches_the_manifest(name):
    problems = findings_for(name)

    assert not problems, "\n".join(str(p) for p in problems)


@pytest.mark.parametrize("name", entities("methods"))
def test_method_matches_the_manifest(name):
    problems = findings_for(name)

    assert not problems, "\n".join(str(p) for p in problems)


def test_no_manifest_finding_is_unattributed():
    attributed = {f.entity.split("/", 1)[1] for f in MANIFEST_FINDINGS if "/" in f.entity}
    known = set(entities("types")) | set(entities("methods"))
    orphans = [f for f in MANIFEST_FINDINGS if "/" not in f.entity]

    assert not orphans, "\n".join(str(f) for f in orphans)
    assert attributed <= known, (
        "a finding names an entity absent from the manifest, so no "
        "parametrized case would report it: " + ", ".join(sorted(attributed - known))
    )


@pytest.mark.parametrize(
    "name,detail",
    [(f.entity, f.detail) for f in DOCSTRING_FINDINGS],
    ids=[f.entity for f in DOCSTRING_FINDINGS]
)
def test_docstring_matches_the_signature(name, detail):
    pytest.fail(f"{name}: {detail}")


def test_comma_grouped_parameters_are_understood():
    doc = """
    Parameters:
        old_title, new_title (``str``, *optional*):
            Title before and after.

        solo (``int``):
            One.
    """

    assert documented_params(doc) == {"old_title", "new_title", "solo"}, (
        "several types document a before/after pair on one line; reading only "
        "the first name reports every parameter in the block as undocumented"
    )


def test_the_docstring_axis_actually_reads_docstrings():
    symbol = COVERAGE.types["KeyboardButton"]

    assert documented_params(symbol.doc), (
        "ast.get_docstring dedents by default, which silently stops the "
        "Parameters: block from matching and makes the whole docstring axis "
        "pass without checking anything"
    )
    assert "text" in documented_params(symbol.doc)


def test_unsupported_entries_are_kept_out_of_the_manifest():
    aliases = COVERAGE.aliases.get("botapi") or {}
    declared = set(aliases.get("type_unsupported") or {}) | set(
        aliases.get("method_unsupported") or {}
    )
    tracked = set(entities("types")) | set(entities("methods"))

    assert declared, "aliases.yaml should declare the Bot API surface MTProto lacks"
    assert not declared & tracked, (
        "these are declared unsupported but still surveyed, so the reason "
        "recorded against them does nothing: "
        + ", ".join(sorted(declared & tracked))
    )
ALIAS_TARGETS = [
    (entity, spec_field, target)
    for entity, mapping in (
        ((COVERAGE.aliases.get("botapi") or {}).get("field_rename") or {}).items()
    )
    if entity != "*"
    for spec_field, target in mapping.items()
]


@pytest.mark.parametrize(
    "entity,spec_field,target",
    ALIAS_TARGETS,
    ids=[f"{e}.{f}" for e, f, _ in ALIAS_TARGETS]
)
def test_an_alias_target_is_populated_from_raw_data(entity, spec_field, target):
    """An alias claims wzgram already exposes the field under another name.

    Pointing at a parameter that nothing fills and nothing reads would satisfy
    the coverage check while the value is always None, which is worse than
    leaving the gap recorded.
    """
    symbol = COVERAGE.wzgram_type(entity)

    if symbol is None:
        pytest.skip(f"{entity} does not resolve")

    source = symbol.path.read_text(encoding="utf-8")
    name = re.escape(target)

    # filled from raw data by a _parse, or read back by a write()
    populated = re.search(rf"(?<!self\.)\b{name}\s*=\s*(?!{name}\b)", source)
    read_back = len(re.findall(rf"self\.{name}\b", source)) > 1

    # input types are filled by the caller and read by whoever sends them
    read_elsewhere = any(
        path != symbol.path and re.search(rf"(?<!self)\.{name}\b", text)
        for path, text in PACKAGE_SOURCES
    )

    assert populated or read_back or read_elsewhere, (
        f"{entity}.{spec_field} is aliased to {target}, but nothing fills "
        f"{target} from raw data and nothing ever reads it, so it is always None"
    )


def test_no_exclusion_masks_a_field_that_exists():
    """An exclusion must only ever cover a field wzgram genuinely lacks.

    Presence is checked before the unsupported table, so a field that is present
    counts as satisfied and stays checked. Letting the exclusion win first would
    mean removing Chat.type went unnoticed, since `type` is excluded globally for
    the union members that have no such field.
    """
    aliases = COVERAGE.aliases.get("botapi") or {}
    masked = []

    for table, resolve in (
        ("field_unsupported", COVERAGE.wzgram_type),
        ("method_field_unsupported", COVERAGE.wzgram_method),
    ):
        for entity, fields in (aliases.get(table) or {}).items():
            if entity == "*":
                continue

            symbol = resolve(entity)

            if symbol is None:
                continue

            for field in fields:
                gaps = (
                    COVERAGE.type_gaps(entity)
                    if resolve is COVERAGE.wzgram_type
                    else COVERAGE.method_botapi_gaps(entity)
                )

                if gaps is not None and field not in gaps and field in symbol.params:
                    masked.append(f"{entity}.{field}")

    assert not masked, (
        "these are excluded yet present, so the exclusion is doing the work "
        "instead of the field: " + ", ".join(sorted(masked))
    )


def test_every_exclusion_carries_a_reason():
    aliases = COVERAGE.aliases.get("botapi") or {}
    blank = []

    for table in ("type_unsupported", "method_unsupported"):
        blank += [
            f"{table}.{name}"
            for name, reason in (aliases.get(table) or {}).items()
            if not str(reason).strip()
        ]

    for table in ("field_unsupported", "method_field_unsupported"):
        for entity, fields in (aliases.get(table) or {}).items():
            blank += [
                f"{entity}.{field}"
                for field, reason in fields.items()
                if not str(reason).strip()
            ]

    assert not blank, "excluded without saying why: " + ", ".join(sorted(blank))


def test_no_rename_points_at_itself():
    tables = [
        (COVERAGE.aliases.get("botapi") or {}).get("field_rename") or {},
        (COVERAGE.aliases.get("botapi") or {}).get("method_field_rename") or {},
        (COVERAGE.aliases.get("mtproto") or {}).get("field_rename") or {},
    ]
    pointless = [
        f"{entity}.{source}"
        for table in tables
        for entity, mapping in table.items()
        for source, target in mapping.items()
        if source == target
    ]

    assert not pointless, "renamed to itself: " + ", ".join(sorted(pointless))


def test_the_enum_axis_actually_resolves_enums():
    """A broken reference pattern makes every enum field silently unresolvable.

    The axis then reports full coverage while checking nothing, which is how it
    first passed with a corrupted pattern.
    """
    assert ENUM_REFERENCE_RE.findall("'enums.MessageEntityType'") == ["MessageEntityType"]
    assert ENUM_REFERENCE_RE.findall("ButtonStyle") == ["ButtonStyle"]

    symbol = COVERAGE.wzgram_type("MessageEntity")

    assert symbol.annotations.get("type"), "annotations must be captured from the AST"
    assert "MessageEntityType" in COVERAGE.enums


def test_enumerated_values_are_read_from_the_description():
    field = next(
        f for f in COVERAGE.spec["types"]["MessageEntity"]["fields"]
        if f["name"] == "type"
    )

    assert len(enumerated_values(field)) > 15, (
        "Bot API only spells a field's accepted values in its description, so "
        "failing to read them leaves the enum axis with nothing to check"
    )
ENUM_CASES = [
    (kind, name)
    for kind in ("types", "methods")
    for name in COVERAGE.implemented(kind)
]


@pytest.mark.parametrize(
    "kind,name", ENUM_CASES, ids=[f"{k[:-1]}.{n}" for k, n in ENUM_CASES]
)
def test_enum_members_cover_the_documented_values(kind, name):
    recorded = set(
        ((COVERAGE.manifest[kind].get("pending") or {}).get(name) or {}).get("enums") or []
    )
    gaps = set(COVERAGE.enum_gaps(kind, name) or [])

    assert gaps <= recorded, (
        f"{name} accepts documented values with no enum member: "
        + ", ".join(sorted(gaps - recorded))
    )
