#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER_DIR = ROOT / "generated-tests"
CLASSES_DIR = ROOT / "build" / "classes" / "java" / "main"
OUTPUT_DIR = RUNNER_DIR / "src" / "test" / "java"
REPORT_DIR = RUNNER_DIR / "build" / "reports" / "test-skeletons"
MANIFEST_FILE = REPORT_DIR / "manifest.json"
MANIFEST_VERSION = 1
BATCH_SIZE = 200

PACKAGE_ROOTS = (
    "net/sourceforge/plantuml",
    "com/plantuml",
)

EXCLUDED_PARTS = {
    "gen",
    "h",
    "jcckit",
    "zext",
    "smetana",
}

EXCLUDED_PREFIXES = (
    "org/stathissideris/",
)


def should_include(class_file: Path) -> bool:
    rel = class_file.relative_to(CLASSES_DIR)
    rel_str = rel.as_posix()
    if "$" in class_file.name:
        return False
    if not any(rel_str.startswith(root + "/") for root in PACKAGE_ROOTS):
        return False
    if any(rel_str.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    return True


def class_name_from_file(class_file: Path) -> str:
    return ".".join(class_file.relative_to(CLASSES_DIR).with_suffix("").parts)


def class_signature(class_file: Path):
    stat = class_file.stat()
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def target_for_class_name(class_name: str) -> Path:
    package_path = Path(*class_name.split(".")[:-1])
    simple_name = class_name.rsplit(".", 1)[-1]
    return OUTPUT_DIR / package_path / f"{simple_name}SkeletonTest.java"


def chunked(values, size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def run_javap(class_names) -> str:
    result = subprocess.run(
        ["javap", "-classpath", str(CLASSES_DIR), "-public", *class_names],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def parse_methods(class_name: str, javap_lines):
    simple_name = class_name.rsplit(".", 1)[-1]
    methods = []
    for raw_line in javap_lines:
        line = raw_line.strip()
        if not line.startswith("public "):
            continue
        if "(" not in line or not line.endswith(");"):
            continue
        if line.startswith("public class ") or line.startswith("public interface ") or line.startswith("public enum "):
            continue
        before_paren = line[: line.index("(")].strip()
        method_name = before_paren.split()[-1]
        if method_name == simple_name or method_name == class_name or method_name.endswith("." + simple_name):
            continue
        args = line[line.index("(") + 1 : line.rindex(")")].strip()
        methods.append((method_name, args, line))
    return methods


def parse_javap_output(class_names, javap_output: str):
    requested = set(class_names)
    collected = {}
    current_class = None
    current_lines = []

    def flush_current():
        if current_class is None:
            return
        collected[current_class] = parse_methods(current_class, current_lines)

    for raw_line in javap_output.splitlines():
        stripped = raw_line.strip()
        if "{" in stripped and "(" not in stripped:
            match = re.search(r"\b(class|interface|enum)\s+([A-Za-z0-9_.$]+)", stripped)
            if match is not None:
                class_name = match.group(2)
                flush_current()
                current_class = class_name if class_name in requested else None
                current_lines = []
                continue
        if current_class is not None:
            current_lines.append(raw_line)

    flush_current()
    return {class_name: collected.get(class_name, []) for class_name in class_names}


def sanitize_fragment(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "none"


def test_method_name(method_name: str, args: str, counter: Counter) -> str:
    counter[method_name] += 1
    suffix = sanitize_fragment(args)
    if counter[method_name] == 1:
        return f"{method_name}_skeleton_for_{suffix}"
    return f"{method_name}_overload_{counter[method_name]}_skeleton_for_{suffix}"


def java_test_source(class_name: str, methods) -> str:
    package_name, simple_name = class_name.rsplit(".", 1)
    test_name = f"{simple_name}SkeletonTest"
    lines = []
    lines.append(f"package {package_name};")
    lines.append("")
    lines.append("import org.junit.Ignore;")
    lines.append("import org.junit.Test;")
    lines.append("")
    lines.append("@Ignore(\"Generated skeleton test; fill fixtures and assertions before enabling\")")
    lines.append(f"public class {test_name} {{")
    lines.append("")
    name_counter = Counter()
    for method_name, args, signature in methods:
        generated_name = test_method_name(method_name, args, name_counter)
        lines.append(f"    @Ignore(\"TODO cover public API: {signature}\")")
        lines.append("    @Test")
        lines.append(f"    public void {generated_name}() {{")
        lines.append("    }")
        lines.append("")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def load_manifest():
    if not MANIFEST_FILE.exists():
        return {}
    payload = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if payload.get("manifest_version") != MANIFEST_VERSION:
        return {}
    return payload.get("classes", {})


def write_manifest(classes) -> None:
    MANIFEST_FILE.write_text(
        json.dumps(
            {"manifest_version": MANIFEST_VERSION, "classes": classes},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def remove_target(target: Path) -> None:
    if target.exists():
        target.unlink()
    parent = target.parent
    while parent != OUTPUT_DIR and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def parse_args():
    parser = argparse.ArgumentParser(description="Generate JUnit skeleton tests for public methods.")
    parser.add_argument("--classes-dir", type=Path, default=CLASSES_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    return parser.parse_args()


def main() -> int:
    global CLASSES_DIR
    global OUTPUT_DIR
    global REPORT_DIR
    global MANIFEST_FILE
    global BATCH_SIZE

    args = parse_args()
    CLASSES_DIR = args.classes_dir.resolve()
    OUTPUT_DIR = args.output_dir.resolve()
    REPORT_DIR = args.report_dir.resolve()
    MANIFEST_FILE = REPORT_DIR / "manifest.json"
    BATCH_SIZE = args.batch_size

    if not CLASSES_DIR.exists():
        raise SystemExit(f"Compiled classes directory not found: {CLASSES_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    previous_manifest = load_manifest()
    class_files = sorted(p for p in CLASSES_DIR.rglob("*.class") if should_include(p))
    current_manifest = {}
    current_class_names = set()
    pending = []
    unchanged_classes = 0

    for class_file in class_files:
        class_name = class_name_from_file(class_file)
        current_class_names.add(class_name)
        signature = class_signature(class_file)
        target = target_for_class_name(class_name)
        target_rel = str(target.relative_to(OUTPUT_DIR))
        previous = previous_manifest.get(class_name)
        if (
            previous is not None
            and previous.get("signature") == signature
            and previous.get("target") == target_rel
            and (previous.get("method_count", 0) == 0 or target.exists())
        ):
            current_manifest[class_name] = previous
            unchanged_classes += 1
            continue

        pending.append((class_name, signature, target, target_rel))

    removed_classes = 0
    for class_name, previous in previous_manifest.items():
        if class_name in current_class_names:
            continue
        remove_target(OUTPUT_DIR / previous["target"])
        removed_classes += 1

    refreshed_classes = 0
    for batch in chunked(pending, BATCH_SIZE):
        batch_class_names = [class_name for class_name, _, _, _ in batch]
        parsed = parse_javap_output(batch_class_names, run_javap(batch_class_names))
        for class_name, signature, target, target_rel in batch:
            methods = parsed[class_name]
            if methods:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(java_test_source(class_name, methods), encoding="utf-8")
            else:
                remove_target(target)
            current_manifest[class_name] = {
                "signature": signature,
                "target": target_rel,
                "method_count": len(methods),
            }
            refreshed_classes += 1

    class_count = sum(1 for data in current_manifest.values() if data["method_count"] > 0)
    method_count = sum(data["method_count"] for data in current_manifest.values())
    skipped_without_public_methods = len(class_files) - class_count
    write_manifest(current_manifest)

    summary = REPORT_DIR / "summary.txt"
    summary.write_text(
        "\n".join(
            [
                f"input_classes={len(class_files)}",
                f"generated_test_classes={class_count}",
                f"generated_test_methods={method_count}",
                f"skipped_without_public_methods={skipped_without_public_methods}",
                f"refreshed_classes={refreshed_classes}",
                f"unchanged_classes={unchanged_classes}",
                f"removed_classes={removed_classes}",
                f"output_dir={OUTPUT_DIR}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
