#!/usr/bin/env python3
"""recomp_harness.py -- batch-run the ReXGlue v0.8.0 recompilation loop across a title library.

The point of this harness is *generalizing*: running the whole extract -> codegen
(-> build -> boot) pipeline over many titles turns one-off observations into a
compatibility matrix and a catalog of recurring failure modes -- which is what
actually hardens the toolkit (and tells us what to upstream to ReXGlue).

Tiers (cost grows steeply -- triage is cheap and scales to the whole library):
  1 extract : rar -> STFS package -> default.xex      (seconds, ~1 MB kept)
  2 codegen : rexglue init + codegen, profile imports (seconds, no VS env needed)
  3 build   : cmake configure + build                 (minutes, GBs -- OPT-IN)
  4 boot    : timed launch, capture furthest stage     (flaky, needs display -- OPT-IN)

Each title is isolated, timed and resumable; one title's failure never aborts the
batch. Per-title results land in <out>/results/<id>.json. `report` aggregates them.

Usage:
  python recomp_harness.py run   --library XBLA --max-tier 2 [--limit N] [--titles GLOB]
  python recomp_harness.py run   --titles "Aegis Wing,1942*" --max-tier 4   # opt-in build/boot
  python recomp_harness.py report
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from fnmatch import fnmatch
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent          # the tools/ dir (extract_stfs.py, ...)
EXTRACT_STFS = TOOLS_DIR / "extract_stfs.py"
XEX_INFO = TOOLS_DIR / "xex_info.py"
PARSE_IMPORTS = TOOLS_DIR / "parse_xex_imports.py"

DEFAULTS = {
    "library_root": r"Z:\Roms\XBOX360\COMPLETE",
    "sdk": r"D:\recomp\360\aegiswing\tools\rexglue-sdk",
    "sevenzip": r"C:\Program Files\7-Zip\7z.exe",
    "out": r"D:\recomp\360\_harness",
    "vsdevshell": r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\Launch-VsDevShell.ps1",
    "llvm_bin": r"C:\Program Files\LLVM\bin",
}

# ---------------------------------------------------------------------------- helpers

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, timeout, cwd=None, env=None):
    """Run a command, never raising. Returns (rc, stdout, stderr, seconds)."""
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout,
                           capture_output=True, text=True, errors="replace")
        return p.returncode, p.stdout or "", p.stderr or "", time.time() - t0
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") if isinstance(e.stdout, str) else "", "TIMEOUT", time.time() - t0
    except Exception as e:  # noqa: BLE001 - harness must survive anything
        return -1, "", f"{type(e).__name__}: {e}", time.time() - t0


def title_id(rar: Path) -> str:
    stem = rar.stem
    return re.sub(r"[^a-z0-9]+", "", stem.lower()) or "untitled"


def load_sdk_ordinals(sdk_root: Path):
    """Build {libname: {ordinal:int -> name}} from the SDK's authoritative export_table.inc.

    Makes the cross-title import table show real names (e.g. XUsbcamCreate) instead of
    bare ordinals, including APIs parse_xex_imports.py doesn't know about.
    """
    tables = defaultdict(dict)
    mod_to_lib = {"xboxkrnl": "xboxkrnl.exe", "xam": "xam.xex", "xbdm": "xbdm.xex"}
    pat = re.compile(r"XE_EXPORT\(\s*(\w+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(\w+)")
    for inc in sdk_root.glob("src/kernel/*/export_table.inc"):
        try:
            for m in pat.finditer(inc.read_text(errors="replace")):
                mod, ordh, name = m.group(1), m.group(2), m.group(3)
                lib = mod_to_lib.get(mod.lower())
                if lib:
                    tables[lib][int(ordh, 16)] = name
        except OSError:
            continue
    return tables

# ---------------------------------------------------------------------------- stages

def stage_extract(rar: Path, work: Path, cfg) -> dict:
    r = {"status": "fail"}
    raw = work / "_raw"          # 7z output (purged)
    stfs_out = work / "_stfs"    # extract_stfs output (purged for triage)
    for d in (raw, stfs_out):
        shutil.rmtree(d, ignore_errors=True)
    raw.mkdir(parents=True, exist_ok=True)

    rc, out, err, dur = run([cfg.sevenzip, "x", str(rar), f"-o{raw}", "-y"], timeout=cfg.t_extract)
    r["unrar_s"] = round(dur, 1)
    if rc != 0:
        r["error"] = f"7z rc={rc}: {(err or out).strip()[:200]}"
        return r

    files = [p for p in raw.rglob("*") if p.is_file()]
    if not files:
        r["error"] = "no files in archive"
        return r
    stfs = max(files, key=lambda p: p.stat().st_size)   # STFS CON package = largest file
    r["stfs_file"] = stfs.name
    r["stfs_mb"] = round(stfs.stat().st_size / 1048576, 1)

    stfs_out.mkdir(parents=True, exist_ok=True)
    rc, out, err, dur = run([sys.executable, str(EXTRACT_STFS), str(stfs), str(stfs_out)],
                           timeout=cfg.t_extract)
    r["stfs_s"] = round(dur, 1)
    if rc != 0:
        r["error"] = f"extract_stfs rc={rc}: {(err or out).strip()[-200:]}"
        shutil.rmtree(raw, ignore_errors=True)
        return r

    xexes = [p for p in stfs_out.rglob("*") if p.is_file() and p.name.lower() == "default.xex"]
    if not xexes:
        xexes = [p for p in stfs_out.rglob("*.xex")] + [p for p in stfs_out.rglob("*.XEX")]
    if not xexes:
        r["error"] = "no .xex found in package"
        shutil.rmtree(raw, ignore_errors=True)
        return r

    xex = xexes[0]
    dst = work / "default.xex"
    shutil.copy2(xex, dst)
    assets = [p for p in stfs_out.rglob("*") if p.is_file()]
    r["n_files"] = len(assets)
    ext_hist = Counter(p.suffix.lower() for p in assets if p.suffix)
    r["asset_exts"] = dict(ext_hist.most_common(12))
    r["xex"] = str(dst)
    r["xex_kb"] = round(dst.stat().st_size / 1024, 1)
    r["status"] = "ok"

    if cfg.keep_assets:
        # keep assets where boot expects them
        adir = work / "extracted"
        shutil.rmtree(adir, ignore_errors=True)
        # the game root is the dir that directly contains default.xex
        shutil.copytree(xex.parent, adir)
    shutil.rmtree(raw, ignore_errors=True)
    shutil.rmtree(stfs_out, ignore_errors=True)
    return r


def stage_profile(work: Path, cfg, sdk_ords) -> dict:
    r = {"status": "fail"}
    xex = work / "default.xex"
    if not xex.exists():
        r["error"] = "no xex"
        return r
    rc, out, err, _ = run([sys.executable, str(XEX_INFO), str(xex)], timeout=cfg.t_profile)
    def grab(pat):
        m = re.search(pat, out)
        return m.group(1) if m else None
    r["base"] = grab(r"Base address:\s*(0x[0-9A-Fa-f]+)")
    r["image_size"] = grab(r"Image size:\s*(0x[0-9A-Fa-f]+)")
    r["entry"] = grab(r"Entry point:\s*(0x[0-9A-Fa-f]+)")
    r["compressed"] = "Compressed" in out
    # NOTE: imports are harvested in stage_codegen from ReXGlue's own resolved
    # init.h (authoritative). parse_xex_imports.py is unreliable here (emits
    # impossible ordinals), so we do not use it for the import inventory.
    if r["base"] is not None:
        r["status"] = "ok"
        r["high_base"] = not r["base"].lower().startswith("0x82")
    return r


def _write_function_hints(base_manifest: str, manifest_path: Path, hints):
    """Rewrite the manifest as base text + an [entrypoint.functions] hint block."""
    lines = [base_manifest.rstrip(),
             "",
             "# Auto-added by harness: function-entry hints to resolve UnresolvedCall",
             "[entrypoint.functions]"]
    for addr in sorted(hints):
        lines.append(f"{addr} = {{}}")
    manifest_path.write_text("\n".join(lines) + "\n")


def _harvest_imports(gen_dir: Path):
    """Authoritative import list: every __imp__NAME ReXGlue declared in init.h."""
    names = set()
    for hdr in list(gen_dir.glob("*_init.h")) + list(gen_dir.glob("*_init.cpp")):
        try:
            for m in re.finditer(r"__imp__(\w+)", hdr.read_text(errors="replace")):
                names.add(m.group(1))
        except OSError:
            continue
    return sorted(names)


def stage_codegen(work: Path, cfg) -> dict:
    r = {"status": "fail"}
    rexglue = Path(cfg.sdk) / "out" / "install" / "win-amd64" / "bin" / "rexglue.exe"
    if not rexglue.exists():
        r["error"] = f"rexglue.exe not found at {rexglue}"
        return r
    proj = work / "project"
    shutil.rmtree(proj, ignore_errors=True)

    rc, out, err, dur = run([str(rexglue), "init", "--project-name", "t" + work.name[:24],
                            "--xex-path", "default.xex", "--game-root", ".",
                            "--project-root", str(proj)], timeout=cfg.t_codegen, cwd=str(work))
    r["init_s"] = round(dur, 1)
    if rc != 0:
        r["error"] = f"init rc={rc}: {(err or out).strip()[-200:]}"
        return r

    manifest = next(proj.glob("*_manifest.toml"), None)
    base_manifest = manifest.read_text() if manifest else ""
    gen = proj / "generated" / "default"

    hints = set()              # auto-added function-entry hints (resolve UnresolvedCall)
    total_cg_s = 0.0
    last_blob = ""
    for iteration in range(1, cfg.max_codegen_iters + 1):
        rc, out, err, dur = run([str(rexglue), "--log-level", "info", "codegen"],
                               timeout=cfg.t_codegen, cwd=str(proj))
        total_cg_s += dur
        last_blob = blob = out + "\n" + err
        n_cpp = len(list(gen.glob("*.cpp"))) if gen.exists() else 0
        if rc == 0 and n_cpp > 0:
            r["status"] = "ok"
            break
        # gather UnresolvedCall targets ("0xTARGET from 0xSITE: ...") and add hints
        targets = set(re.findall(r"(0x[0-9A-Fa-f]+) from 0x[0-9A-Fa-f]+:", blob))
        new = {t for t in targets if t not in hints}
        if not new or not manifest:
            break              # no progress possible (non-hintable error) -> give up
        hints |= new
        _write_function_hints(base_manifest, manifest, hints)

    blob = last_blob
    r["codegen_s"] = round(total_cg_s, 1)
    r["codegen_iterations"] = iteration
    r["hints_added"] = len(hints)

    m = re.search(r"Analyze: found (\d+) errors", blob)
    if m:
        r["n_analysis_errors"] = int(m.group(1))
    errs = [{"type": em.group(1), "count": int(em.group(2))}
            for em in re.finditer(r"^\s*(\w+) \((\d+)\):\s*$", blob, re.M)]
    if errs:
        r["analysis_errors"] = errs
    samples = re.findall(r"(0x[0-9A-Fa-f]+ from 0x[0-9A-Fa-f]+:[^\n]+)", blob)
    if samples:
        r["error_samples"] = samples[:5]
    giants = re.findall(r"Function (0x[0-9A-Fa-f]+) is (\d+) bytes, exceeds", blob)
    if giants:
        r["giant_functions"] = [{"addr": a, "bytes": int(b)} for a, b in giants]

    n_cpp = len(list(gen.glob("*.cpp"))) if gen.exists() else 0
    r["n_generated_cpp"] = n_cpp

    if r.get("status") == "ok":
        r["imports"] = _harvest_imports(gen)     # authoritative, from ReXGlue's init.h
        r["n_imports"] = len(r["imports"])
    else:
        r["error"] = f"codegen rc={rc}" + (f"; {errs[0]['type']}" if errs else "")

    if not cfg.keep_generated and gen.exists():
        shutil.rmtree(gen, ignore_errors=True)
    return r


def classify_boot(logtext: str) -> str:
    markers = [
        ("first_frame", r"[Pp]resent|frame 1|Swap"),
        ("guest_code", r"SetInterruptCallback|SetGraphicsInterrupt|module launch|Preparing module"),
        ("shader_storage", r"Initializing shader storage"),
        ("xex_loaded", r"Loading XEX image"),
        ("function_table", r"Function table initialized"),
        ("runtime_init", r"Runtime initialized successfully"),
        ("gpu_init", r"GPU system initialized"),
        ("started", r"starting"),
    ]
    for label, pat in markers:
        if re.search(pat, logtext):
            return label
    return "none"


def stage_build(work: Path, cfg) -> dict:
    r = {"status": "fail"}
    proj = work / "project"
    if not (proj / "CMakeLists.txt").exists():
        r["error"] = "no project (run codegen with --keep-generated)"
        return r
    install = Path(cfg.sdk) / "out" / "install" / "win-amd64"
    # configure + build inside the VS dev environment, LLVM ahead on PATH
    ps = (f'& "{cfg.vsdevshell}" -Arch amd64 -HostArch amd64 -SkipAutomaticLocation | Out-Null; '
          f'$env:PATH = "{cfg.llvm_bin};$env:PATH"; '
          f'Set-Location "{proj}"; '
          f'cmake --preset win-amd64-release "-DCMAKE_PREFIX_PATH={install}"; '
          f'if ($LASTEXITCODE -eq 0) {{ cmake --build out/build/win-amd64-release }}; '
          f'exit $LASTEXITCODE')
    rc, out, err, dur = run(["powershell", "-NoProfile", "-Command", ps], timeout=cfg.t_build)
    blob = out + "\n" + err
    r["build_s"] = round(dur, 1)
    undef = re.findall(r"undefined symbol: [^\n]*?_(\w+)", blob)
    if undef:
        r["undefined_symbols"] = sorted(set(undef))[:30]
    exe = next((proj / "out" / "build" / "win-amd64-release").glob("*.exe"), None) \
        if (proj / "out" / "build" / "win-amd64-release").exists() else None
    if rc == 0 and exe and exe.exists():
        r["status"] = "ok"
        r["exe"] = str(exe)
        r["exe_mb"] = round(exe.stat().st_size / 1048576, 2)
    else:
        r["error"] = f"build rc={rc}" + ("; undefined symbols" if undef else "")
    return r


def stage_boot(work: Path, cfg) -> dict:
    r = {"status": "fail"}
    bdir = work / "project" / "out" / "build" / "win-amd64-release"
    exe = next(bdir.glob("*.exe"), None) if bdir.exists() else None
    assets = work / "extracted"
    if not exe:
        r["error"] = "no exe"
        return r
    if not assets.exists():
        r["error"] = "no assets (run extract with --keep-assets)"
        return r
    logdir = bdir / "logs"
    shutil.rmtree(logdir, ignore_errors=True)
    ps = (f'$p = Start-Process -FilePath "{exe}" -WorkingDirectory "{work / "project"}" '
          f'-ArgumentList "--game_data_root={assets}" -PassThru -WindowStyle Minimized; '
          f'Start-Sleep -Seconds {cfg.boot_seconds}; '
          f'if (-not $p.HasExited) {{ $p.Kill(); "ALIVE" }} else {{ "EXIT $($p.ExitCode)" }}')
    rc, out, err, dur = run(["powershell", "-NoProfile", "-Command", ps],
                           timeout=cfg.boot_seconds + 30)
    r["alive_after_s"] = cfg.boot_seconds if "ALIVE" in out else None
    logf = next(logdir.glob("*.log"), None) if logdir.exists() else None
    if logf:
        text = logf.read_text(errors="replace")
        r["furthest"] = classify_boot(text)
        last_err = [ln for ln in text.splitlines() if "[error]" in ln]
        if last_err:
            r["last_error"] = last_err[-1][-220:]
        r["log_tail"] = "\n".join(text.splitlines()[-12:])
        r["status"] = "ok"   # "ok" = we got telemetry, not necessarily a clean boot
    else:
        r["error"] = "no log produced; " + out.strip()[:120]
    return r

# ---------------------------------------------------------------------------- driver

STAGE_ORDER = ["extract", "profile", "codegen", "build", "boot"]
TIER_OF = {"extract": 1, "profile": 1, "codegen": 2, "build": 3, "boot": 4}


def run_title(rar: Path, cfg, sdk_ords) -> dict:
    tid = title_id(rar)
    work = Path(cfg.out) / "work" / tid
    work.mkdir(parents=True, exist_ok=True)
    res = {"title": rar.stem, "id": tid, "library": rar.parent.name, "rar": str(rar),
           "stages": {}, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "max_tier_reached": 0}

    funcs = {"extract": lambda: stage_extract(rar, work, cfg),
             "profile": lambda: stage_profile(work, cfg, sdk_ords),
             "codegen": lambda: stage_codegen(work, cfg),
             "build": lambda: stage_build(work, cfg),
             "boot": lambda: stage_boot(work, cfg)}

    for stage in STAGE_ORDER:
        if TIER_OF[stage] > cfg.max_tier:
            break
        out = funcs[stage]()
        res["stages"][stage] = out
        if out.get("status") == "ok":
            res["max_tier_reached"] = max(res["max_tier_reached"], TIER_OF[stage])
        else:
            res["blocked_at"] = stage
            break

    if not cfg.keep_xex and (work / "default.xex").exists():
        try:
            (work / "default.xex").unlink()
        except OSError:
            pass
    return res


def cmd_run(cfg):
    lib_dir = Path(cfg.library_root) / cfg.library if cfg.library != "_" else Path(cfg.library_root)
    rars = sorted(lib_dir.glob("*.rar"))
    if cfg.titles:
        pats = [p.strip() for p in cfg.titles.split(",")]
        rars = [r for r in rars if any(fnmatch(r.stem, p) or fnmatch(r.stem, p + "*")
                                       or p.lower() in r.stem.lower() for p in pats)]
    if cfg.limit:
        rars = rars[:cfg.limit]

    results_dir = Path(cfg.out) / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    sdk_ords = load_sdk_ordinals(Path(cfg.sdk))
    log(f"{len(rars)} titles from {lib_dir} | max-tier {cfg.max_tier} | "
        f"ordinal tables: {sum(len(v) for v in sdk_ords.values())} names")

    done = skipped = 0
    for i, rar in enumerate(rars, 1):
        tid = title_id(rar)
        rj = results_dir / f"{tid}.json"
        if rj.exists() and not cfg.force:
            try:
                prev = json.loads(rj.read_text())
                if prev.get("max_tier_reached", 0) >= cfg.max_tier or prev.get("blocked_at"):
                    skipped += 1
                    continue
            except json.JSONDecodeError:
                pass
        log(f"[{i}/{len(rars)}] {rar.stem}")
        res = run_title(rar, cfg, sdk_ords)
        rj.write_text(json.dumps(res, indent=2))
        b = res.get("blocked_at", "-")
        log(f"    -> tier {res['max_tier_reached']}" + (f" (blocked at {b})" if b != "-" else " OK"))
        done += 1
    log(f"done: {done} processed, {skipped} skipped (resumed)")
    cmd_report(cfg)


def cmd_report(cfg):
    results_dir = Path(cfg.out) / "results"
    rows = []
    for rj in sorted(results_dir.glob("*.json")):
        try:
            rows.append(json.loads(rj.read_text()))
        except json.JSONDecodeError:
            continue
    if not rows:
        log("no results yet")
        return

    n = len(rows)
    def stage_ok(name):
        return sum(1 for r in rows if r["stages"].get(name, {}).get("status") == "ok")

    import_counter = Counter()       # how many titles import each function (from codegen init.h)
    err_types = Counter()
    high_base, giants, extract_fail, codegen_fail, build_undef = [], [], [], [], Counter()
    base_dist = Counter()
    hint_stats = []                  # (title, hints_added, iterations) for codegen-passed titles
    for r in rows:
        st = r["stages"]
        prof = st.get("profile", {})
        if prof.get("status") == "ok":
            base_dist[prof.get("base", "?")] += 1
            if prof.get("high_base"):
                high_base.append((r["title"], prof.get("base")))
        if st.get("extract", {}).get("status") != "ok" and "extract" in st:
            extract_fail.append((r["title"], st["extract"].get("error", "?")))
        cg = st.get("codegen", {})
        for e in cg.get("analysis_errors", []) or []:
            err_types[e["type"]] += e.get("count", 1)
        if cg.get("giant_functions"):
            giants.append((r["title"], cg["giant_functions"]))
        if cg.get("status") == "ok":
            for fn in set(cg.get("imports") or []):
                import_counter[fn] += 1
            hint_stats.append((r["title"], cg.get("hints_added", 0), cg.get("codegen_iterations", 1)))
        elif "codegen" in st:
            codegen_fail.append((r["title"], cg.get("error", "?")))
        for s in st.get("build", {}).get("undefined_symbols", []) or []:
            build_undef[s] += 1

    out = []
    A = out.append
    A(f"# Recomp Harness Report\n\n_{n} titles processed | generated {time.strftime('%Y-%m-%d %H:%M')}_\n")
    A("## Pipeline funnel\n")
    A("| Stage | Reached OK | % |\n|---|---:|---:|")
    for s in STAGE_ORDER:
        attempted = sum(1 for r in rows if s in r["stages"])
        ok = stage_ok(s)
        A(f"| {s} | {ok}/{attempted or n} | {round(100*ok/n)}% |")
    A("")

    A("## Image base distribution\n")
    for base, c in base_dist.most_common():
        flag = "  <- non-standard (high-base risk)" if not str(base).lower().startswith("0x82") else ""
        A(f"- `{base}`: {c}{flag}")
    if high_base:
        A(f"\n**High-base titles ({len(high_base)})** (function-table layout risk):")
        for t, b in high_base[:30]:
            A(f"- {t} (`{b}`)")
    A("")

    A("## Codegen analysis-error catalog\n")
    if err_types:
        for et, c in err_types.most_common():
            A(f"- **{et}**: {c} occurrences")
    else:
        A("_none_")
    if codegen_fail:
        A(f"\n**Codegen failures ({len(codegen_fail)}):**")
        for t, e in codegen_fail[:40]:
            A(f"- {t}: {e}")
    A("")

    if hint_stats:
        needed = [h for h in hint_stats if h[1] > 0]
        A("## Auto-resolve (function-hint injection)\n")
        A(f"- Titles that passed codegen: {len(hint_stats)}")
        A(f"- Passed with **0** hints (clean): {sum(1 for h in hint_stats if h[1] == 0)}")
        A(f"- Needed >=1 auto-hint: {len(needed)}")
        if needed:
            mx = max(needed, key=lambda h: h[1])
            A(f"- Max hints for one title: {mx[1]} ({mx[0]})")
            A(f"- Avg hints (of those needing them): {round(sum(h[1] for h in needed)/len(needed), 1)}")
        A("")

    A("## Top kernel imports across titles (stub-prioritization list)\n")
    A("_How many titles import each function -- the most common unimplemented ones are the highest-value stubs to ship._\n")
    A("| Import | # titles |\n|---|---:|")
    for name, c in import_counter.most_common(60):
        A(f"| `{name}` | {c} |")
    A("")

    if build_undef:
        A("## Undefined symbols at link (across built titles)\n")
        A("| Symbol | # titles |\n|---|---:|")
        for s, c in build_undef.most_common(40):
            A(f"| `{s}` | {c} |")
        A("")

    if giants:
        A("## Giant-function warnings (boundary mis-detection)\n")
        for t, gs in giants[:30]:
            A(f"- {t}: " + ", ".join(f"{g['addr']} ({g['bytes']//1024} KB)" for g in gs))
        A("")

    if extract_fail:
        A(f"## Extraction failures ({len(extract_fail)})\n")
        for t, e in extract_fail[:40]:
            A(f"- {t}: {e}")
        A("")

    # boot furthest-stage histogram
    boot_far = Counter(r["stages"].get("boot", {}).get("furthest")
                       for r in rows if r["stages"].get("boot", {}).get("status") == "ok")
    if boot_far:
        A("## Boot: furthest stage reached\n")
        for stage, c in boot_far.most_common():
            A(f"- {stage}: {c}")
        A("")

    report = Path(cfg.out) / "REPORT.md"
    report.write_text("\n".join(out), encoding="utf-8")
    log(f"report -> {report}")


def build_cfg(args):
    class C: pass
    c = C()
    for k, v in vars(args).items():      # set every arg (incl. None) so attrs exist
        setattr(c, k, v)
    for k, v in DEFAULTS.items():        # fill defaults only where missing/None
        if getattr(c, k, None) is None:
            setattr(c, k, v)
    # timeouts (seconds)
    c.t_extract = args.t_extract
    c.t_profile = 60
    c.t_codegen = args.t_codegen
    c.t_build = args.t_build
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="run the pipeline over a library/title set")
    pr.add_argument("--library", default="XBLA", help="subfolder of library_root (XBLA/XBLIG/Games), or _ for root")
    pr.add_argument("--library-root", dest="library_root")
    pr.add_argument("--titles", help="comma-separated name globs/substrings to filter")
    pr.add_argument("--limit", type=int, help="cap number of titles")
    pr.add_argument("--max-tier", dest="max_tier", type=int, default=2, choices=[1, 2, 3, 4],
                    help="1 extract+profile, 2 +codegen (default), 3 +build, 4 +boot")
    pr.add_argument("--force", action="store_true", help="re-run titles already recorded")
    pr.add_argument("--sdk")
    pr.add_argument("--sevenzip")
    pr.add_argument("--out")
    pr.add_argument("--keep-xex", dest="keep_xex", action="store_true")
    pr.add_argument("--keep-generated", dest="keep_generated", action="store_true", help="needed for tier 3")
    pr.add_argument("--keep-assets", dest="keep_assets", action="store_true", help="needed for tier 4")
    pr.add_argument("--boot-seconds", dest="boot_seconds", type=int, default=15)
    pr.add_argument("--max-codegen-iters", dest="max_codegen_iters", type=int, default=8,
                    help="auto-resolve retry passes (inject function hints, re-run codegen)")
    pr.add_argument("--t-extract", dest="t_extract", type=int, default=600)
    pr.add_argument("--t-codegen", dest="t_codegen", type=int, default=300)
    pr.add_argument("--t-build", dest="t_build", type=int, default=2400)

    rp = sub.add_parser("report", help="aggregate results into REPORT.md")
    rp.add_argument("--out")
    rp.add_argument("--sdk")

    args = ap.parse_args()
    # fill defaults for fields the subparser may not define
    for f, d in [("keep_xex", False), ("keep_generated", False), ("keep_assets", False),
                 ("boot_seconds", 15), ("max_tier", 2), ("force", False), ("titles", None),
                 ("limit", None), ("library", "XBLA"), ("t_extract", 600),
                 ("t_codegen", 300), ("t_build", 2400), ("max_codegen_iters", 8)]:
        if not hasattr(args, f):
            setattr(args, f, d)
    cfg = build_cfg(args)
    if args.cmd == "run":
        cmd_run(cfg)
    elif args.cmd == "report":
        cmd_report(cfg)


if __name__ == "__main__":
    main()
